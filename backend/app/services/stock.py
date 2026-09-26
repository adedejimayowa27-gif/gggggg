"""
Inventory/stock helpers (Step 13, Batch 3), shared by the stock routes,
the transaction routes (Step 13, Batch 1), the import pipeline, and the
Google Sheets / Excel syncs, so "does this sale affect a stock record"
has exactly one definition.

quantity_on_hand only ever changes through apply_*_adjustment below --
every change is paired with a StockAdjustment row, so there is always an
audit trail explaining why the number is what it is. Nothing here
commits; callers commit together with whatever else they're doing in the
same request (creating a transaction, confirming an import, ...) so a
stock change is never left half-applied.
"""
import uuid
from decimal import Decimal
from typing import Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.models.business import Business
from app.models.product_stock import ProductStock
from app.models.stock_adjustment import StockAdjustment
from app.models.transaction import Transaction
from app.schemas.stock import StockOut, StockOutWithFlag

# Below this share of the reorder level remaining, a shortage is more
# urgent -- shared with the stock_shortage alert detector so the two
# never disagree about what "badly low" means.
CRITICAL_RATIO = 0.0
HIGH_RATIO = 0.25
MEDIUM_RATIO = 0.5


def to_stock_out_with_flag(stock: ProductStock) -> StockOutWithFlag:
    is_low = stock.reorder_level > 0 and stock.quantity_on_hand <= stock.reorder_level
    return StockOutWithFlag(**StockOut.model_validate(stock).model_dump(), is_low=is_low)


def find_stock_record(
    db: Session, business_id: uuid.UUID, product: str, branch_id: uuid.UUID | None
) -> ProductStock | None:
    """Exact business + branch, case-insensitive product match. Used
    before creating a new record, so "Rice" and "rice" don't split into
    two, and to resolve which record a stock route's product filter or a
    write is talking about."""
    query = db.query(ProductStock).filter(
        ProductStock.business_id == business_id, func.lower(ProductStock.product) == product.strip().lower()
    )
    if branch_id is None:
        query = query.filter(ProductStock.branch_id.is_(None))
    else:
        query = query.filter(ProductStock.branch_id == branch_id)
    return query.first()


def find_stock_for_sale(
    db: Session, business_id: uuid.UUID, product: str, branch_id: uuid.UUID | None
) -> ProductStock | None:
    """
    Which stock record (if any) a sale of `product` at `branch_id`
    should deduct from: that branch's own record if one exists,
    otherwise the shared (no-branch) record. A sale with no branch only
    ever matches the shared record -- it has no location to look up a
    branch-specific one for.
    """
    if branch_id is not None:
        branch_specific = find_stock_record(db, business_id, product, branch_id)
        if branch_specific is not None:
            return branch_specific
    return find_stock_record(db, business_id, product, None)


def _apply_delta(stock: ProductStock, delta: Decimal) -> None:
    stock.quantity_on_hand = stock.quantity_on_hand + delta


def _record_adjustment(
    db: Session,
    stock: ProductStock,
    *,
    reason: str,
    delta: Decimal,
    note: str | None = None,
    related_transaction_id: uuid.UUID | None = None,
    created_by_user_id: uuid.UUID | None = None,
) -> StockAdjustment:
    _apply_delta(stock, delta)
    adjustment = StockAdjustment(
        id=uuid.uuid4(),
        business_id=stock.business_id,
        product_stock_id=stock.id,
        reason=reason,
        delta=delta,
        resulting_quantity=stock.quantity_on_hand,
        note=note,
        related_transaction_id=related_transaction_id,
        created_by_user_id=created_by_user_id,
    )
    db.add(adjustment)
    return adjustment


def record_initial_quantity(db: Session, stock: ProductStock, user_id: uuid.UUID | None) -> StockAdjustment | None:
    """Logs the opening quantity a new stock record was created with, so
    it shows up in history instead of silently starting mid-ledger.
    Skipped for a record that opens at zero -- there's nothing to log.

    Unlike every other adjustment helper, this does NOT call
    _apply_delta: quantity_on_hand is already the opening value (it came
    straight from the create payload), so applying the delta again would
    double it. This only records the matching audit row.
    """
    if stock.quantity_on_hand == 0:
        return None
    adjustment = StockAdjustment(
        id=uuid.uuid4(), business_id=stock.business_id, product_stock_id=stock.id,
        reason="initial", delta=stock.quantity_on_hand, resulting_quantity=stock.quantity_on_hand,
        created_by_user_id=user_id,
    )
    db.add(adjustment)
    return adjustment


def apply_manual_adjustment(
    db: Session,
    stock: ProductStock,
    *,
    reason: str,
    quantity: Decimal,
    note: str | None,
    user_id: uuid.UUID | None,
) -> StockAdjustment:
    """
    A person's own restock / damage / correction entry. `quantity`'s
    meaning depends on `reason` -- see StockAdjustmentCreate's docstring;
    the schema layer already validated it's non-negative/positive as
    appropriate for that reason.
    """
    if reason == "restock":
        delta = quantity
    elif reason == "damage":
        delta = -quantity
    elif reason == "correction":
        delta = quantity - stock.quantity_on_hand
    else:
        raise ValidationError(f"Unsupported adjustment reason: {reason!r}.")
    return _record_adjustment(db, stock, reason=reason, delta=delta, note=note, created_by_user_id=user_id)


def apply_sale_deduction(
    db: Session, stock: ProductStock, quantity: Decimal, transaction_id: uuid.UUID, user_id: uuid.UUID | None
) -> StockAdjustment:
    """
    Automatic deduction for one sale. Allowed to take quantity_on_hand
    negative -- clamping at zero would silently understate how short the
    business actually is, and the stock_shortage alert (and the low-stock
    badge) already treat "at or below reorder level" as the signal, which
    a negative number still satisfies correctly.
    """
    return _record_adjustment(
        db, stock, reason="sale", delta=-quantity, related_transaction_id=transaction_id, created_by_user_id=user_id
    )


def reverse_linked_sale_adjustment(db: Session, transaction_id: uuid.UUID) -> None:
    """
    Undoes a "sale" deduction tied to this transaction, if one is
    currently outstanding -- called whenever a transaction that may have
    already deducted stock is about to be edited (in a way that changes
    what it sold) or deleted. Always runs, independent of the business's
    current auto_deduct_stock_on_sale setting: that setting controls
    whether NEW deductions happen, not whether a stock change already
    made on a transaction's behalf gets cleaned up when that transaction
    goes away -- otherwise turning the setting off would leave stock
    permanently understated by every sale deducted while it was on.

    A transaction can be edited more than once, so it can have several
    "sale"/"sale_reversal" rows in its history (one pair per edit that
    changed product/quantity/branch while auto-deduction was on). Only
    the MOST RECENT one matters: if it's a "sale", that deduction is
    still outstanding and gets reversed, on whichever stock record it was
    actually taken from (which can differ across edits, if the product
    or branch changed) -- using its own recorded delta rather than a sum
    across history avoids trying to net together rows that may belong to
    two different stock records entirely. If the most recent row is
    already a "sale_reversal" (an edit already reversed it and nothing
    was re-deducted, e.g. because auto-deduction was off at the time),
    there's nothing outstanding, so this does nothing -- avoiding a
    double reversal if the same transaction is later edited again.
    """
    latest = (
        db.query(StockAdjustment)
        .filter(
            StockAdjustment.related_transaction_id == transaction_id,
            StockAdjustment.reason.in_(("sale", "sale_reversal")),
        )
        .order_by(StockAdjustment.seq.desc())
        .first()
    )
    if latest is None or latest.reason != "sale":
        return
    stock = db.get(ProductStock, latest.product_stock_id)
    if stock is None:
        return  # the stock record itself was since deleted -- nothing to reverse it on
    _record_adjustment(
        db, stock, reason="sale_reversal", delta=-latest.delta,
        note="The sale this stock was deducted for was edited or deleted.",
        related_transaction_id=transaction_id,
    )


def auto_deduct_for_transaction(
    db: Session, business: Business, transaction: Transaction, user_id: uuid.UUID | None = None
) -> None:
    """Deducts one transaction's quantity from a matching stock record,
    if Business.auto_deduct_stock_on_sale is on and a match exists. A
    sale of a product with no tracked stock record does nothing --
    inventory tracking is opt-in per product, not assumed for every sale."""
    if not business.auto_deduct_stock_on_sale:
        return
    stock = find_stock_for_sale(db, business.id, transaction.product, transaction.branch_id)
    if stock is not None:
        apply_sale_deduction(db, stock, transaction.quantity, transaction.id, user_id)


def auto_deduct_for_new_transactions(db: Session, business: Business, transactions: list[Transaction]) -> None:
    """
    The bulk equivalent of auto_deduct_for_transaction, for a file import
    or a Google Sheets / Excel sync inserting many rows at once. Loads
    every stock record for the business ONCE rather than querying per
    row -- these can insert thousands of transactions in one run.
    """
    if not business.auto_deduct_stock_on_sale or not transactions:
        return
    all_stock = db.query(ProductStock).filter(ProductStock.business_id == business.id).all()
    by_branch_and_product: dict[tuple[uuid.UUID | None, str], ProductStock] = {
        (s.branch_id, s.product.strip().lower()): s for s in all_stock
    }
    shared_by_product: dict[str, ProductStock] = {
        s.product.strip().lower(): s for s in all_stock if s.branch_id is None
    }
    for transaction in transactions:
        key = transaction.product.strip().lower()
        stock = by_branch_and_product.get((transaction.branch_id, key)) or shared_by_product.get(key)
        if stock is not None:
            apply_sale_deduction(db, stock, transaction.quantity, transaction.id, user_id=None)


def _escape_like(text: str) -> str:
    """Make %, _ and \\ in user input match literally inside ILIKE."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def stock_filters(
    business_id: uuid.UUID,
    branch_id: uuid.UUID | None = None,
    q: str | None = None,
    low_stock_only: bool = False,
) -> list:
    filters = [ProductStock.business_id == business_id]
    if branch_id is not None:
        filters.append(ProductStock.branch_id == branch_id)
    if q:
        pattern = f"%{_escape_like(q.strip())}%"
        filters.append(ProductStock.product.ilike(pattern, escape="\\"))
    if low_stock_only:
        filters.append(ProductStock.reorder_level > 0)
        filters.append(ProductStock.quantity_on_hand <= ProductStock.reorder_level)
    return filters


def low_stock_count(db: Session, *filters) -> int:
    """Count of records at or below their reorder level, among `filters`
    -- independent of whether those filters already include the
    low_stock_only condition, so a page can show both "N results" and
    "M of them low" for the same query."""
    return (
        db.query(ProductStock)
        .filter(*filters, ProductStock.reorder_level > 0, ProductStock.quantity_on_hand <= ProductStock.reorder_level)
        .count()
    )
