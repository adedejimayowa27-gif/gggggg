"""
Inventory/stock routes (Step 13, Batch 3).

Reading is open to every role. Adding a product to track, restocking,
recording damage/loss, and correcting a count are day-to-day work
("member"). Removing a stock record entirely (e.g. a discontinued
product) needs "admin", matching how deleting a branch or a transaction
does. All writes are audit-logged.

Route order matters: /stock/{stock_id}/adjustments must be declared
before a bare /stock/{stock_id} would otherwise be tried against
"adjustments" as an id -- FastAPI matches path operations in declaration
order, and a bare {stock_id} route earlier would swallow that path.
Actually declaring the more specific (longer) paths first avoids this
regardless of order here since they have an extra segment, but the
convention is kept for consistency with expenses.py's /summary,
/categories.
"""
import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import (
    ensure_branch_belongs_to_business,
    get_current_user,
    get_owned_business,
    get_owned_stock,
    require_business_role,
)
from app.core.exceptions import ValidationError
from app.db.session import get_db
from app.models.business import Business
from app.models.product_stock import ProductStock
from app.models.stock_adjustment import StockAdjustment
from app.models.user import User
from app.schemas.stock import (
    PaginatedStock,
    StockAdjustmentCreate,
    StockAdjustmentOut,
    StockAdjustmentResult,
    StockCreate,
    StockOutWithFlag,
    StockUpdate,
)
from app.services.audit import client_ip, log_action
from app.services.stock import (
    apply_manual_adjustment,
    find_stock_record,
    low_stock_count,
    record_initial_quantity,
    stock_filters,
    to_stock_out_with_flag,
)

router = APIRouter(prefix="/businesses/{business_id}/stock", tags=["stock"])

MAX_PAGE_SIZE = 200
MAX_ADJUSTMENT_HISTORY = 200


@router.get("", response_model=PaginatedStock)
def list_stock(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=MAX_PAGE_SIZE),
    branch_id: uuid.UUID | None = Query(default=None, description="Restrict to one branch."),
    q: str | None = Query(default=None, min_length=1, max_length=200, description="Search product name."),
    low_stock_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    filters = stock_filters(business.id, branch_id, q, low_stock_only)
    total = db.query(ProductStock).filter(*filters).count()
    items = (
        db.query(ProductStock)
        .filter(*filters)
        .order_by(ProductStock.product)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedStock(
        items=[to_stock_out_with_flag(s) for s in items],
        total=total,
        page=page,
        page_size=page_size,
        low_stock_count=low_stock_count(db, *stock_filters(business.id, branch_id, q)),
    )


@router.post("", response_model=StockOutWithFlag, status_code=status.HTTP_201_CREATED)
def create_stock(
    payload: StockCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    business: Business = Depends(require_business_role("member")),
):
    ensure_branch_belongs_to_business(db, business, payload.branch_id)
    existing = find_stock_record(db, business.id, payload.product, payload.branch_id)
    if existing is not None:
        raise ValidationError(
            "This product is already tracked for this branch -- adjust its existing record instead of "
            "creating a new one.",
            code="already_tracked",
        )

    stock = ProductStock(
        id=uuid.uuid4(), business_id=business.id, branch_id=payload.branch_id,
        product=payload.product, quantity_on_hand=payload.quantity_on_hand, reorder_level=payload.reorder_level,
    )
    db.add(stock)
    record_initial_quantity(db, stock, current_user.id)
    db.commit()
    db.refresh(stock)

    log_action(
        db, "stock.created", business_id=business.id, actor_user_id=current_user.id,
        target_type="product_stock", target_id=str(stock.id),
        details={"product": stock.product, "quantity_on_hand": str(stock.quantity_on_hand)},
        ip_address=client_ip(request),
    )
    return to_stock_out_with_flag(stock)


@router.patch("/{stock_id}", response_model=StockOutWithFlag)
def update_stock(
    stock_id: uuid.UUID,
    payload: StockUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    business: Business = Depends(require_business_role("member")),
):
    """Changes only the fields sent -- reorder_level and/or which branch
    this record belongs to. Quantity is never edited here; use the
    adjustments endpoint below so every quantity change is logged."""
    stock = get_owned_stock(stock_id, business, db)
    changes = {field: getattr(payload, field) for field in payload.model_fields_set}

    if "branch_id" in changes:
        ensure_branch_belongs_to_business(db, business, changes["branch_id"])
        # Moving to a branch (or to shared) that already has its own record
        # for this product would create two records for one product/branch.
        target_branch_id = changes["branch_id"]
        if target_branch_id != stock.branch_id:
            clash = find_stock_record(db, business.id, stock.product, target_branch_id)
            if clash is not None and clash.id != stock.id:
                raise ValidationError(
                    "This product already has a stock record for that branch.", code="already_tracked"
                )

    changed_fields = [f for f, value in changes.items() if getattr(stock, f) != value]
    if not changed_fields:
        return to_stock_out_with_flag(stock)
    for field in changed_fields:
        setattr(stock, field, changes[field])
    db.commit()
    db.refresh(stock)

    log_action(
        db, "stock.updated", business_id=business.id, actor_user_id=current_user.id,
        target_type="product_stock", target_id=str(stock.id),
        details={"product": stock.product, "fields": sorted(changed_fields)},
        ip_address=client_ip(request),
    )
    return to_stock_out_with_flag(stock)


@router.delete("/{stock_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_stock(
    stock_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    business: Business = Depends(require_business_role("admin")),
):
    """Stops tracking this product's stock entirely -- its adjustment
    history goes with it. A sale of this product afterward, even with
    auto-deduction on, simply won't match anything (see
    app.services.stock.auto_deduct_for_transaction)."""
    stock = get_owned_stock(stock_id, business, db)
    details = {"product": stock.product, "quantity_on_hand": str(stock.quantity_on_hand)}
    db.delete(stock)
    db.commit()

    log_action(
        db, "stock.deleted", business_id=business.id, actor_user_id=current_user.id,
        target_type="product_stock", target_id=str(stock_id), details=details, ip_address=client_ip(request),
    )


@router.get("/{stock_id}/adjustments", response_model=list[StockAdjustmentOut])
def list_stock_adjustments(
    stock_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=MAX_ADJUSTMENT_HISTORY),
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    stock = get_owned_stock(stock_id, business, db)
    rows = (
        db.query(StockAdjustment)
        .filter(StockAdjustment.product_stock_id == stock.id)
        .order_by(StockAdjustment.seq.desc())
        .limit(limit)
        .all()
    )
    return [StockAdjustmentOut.model_validate(r) for r in rows]


@router.post("/{stock_id}/adjustments", response_model=StockAdjustmentResult, status_code=status.HTTP_201_CREATED)
def create_stock_adjustment(
    stock_id: uuid.UUID,
    payload: StockAdjustmentCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    business: Business = Depends(require_business_role("member")),
):
    stock = get_owned_stock(stock_id, business, db)
    adjustment = apply_manual_adjustment(
        db, stock, reason=payload.reason, quantity=payload.quantity, note=payload.note, user_id=current_user.id,
    )
    db.commit()
    db.refresh(stock)
    db.refresh(adjustment)

    log_action(
        db, "stock.adjusted", business_id=business.id, actor_user_id=current_user.id,
        target_type="product_stock", target_id=str(stock.id),
        details={
            "product": stock.product, "reason": adjustment.reason,
            "delta": str(adjustment.delta), "resulting_quantity": str(adjustment.resulting_quantity),
        },
        ip_address=client_ip(request),
    )
    return StockAdjustmentResult(stock=to_stock_out_with_flag(stock), adjustment=StockAdjustmentOut.model_validate(adjustment))
