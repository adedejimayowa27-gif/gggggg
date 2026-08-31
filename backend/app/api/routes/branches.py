"""
Branch routes (Step 10, Batch 10.1, requirement #3).

All standard authenticated, business-owned CRUD -- nothing here is
required by any other part of the app; a business with zero branches
behaves exactly as it always has.
"""
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_owned_branch, get_owned_business, require_business_role
from app.db.session import get_db
from app.models.branch import Branch
from app.models.business import Business
from app.schemas.branch import BranchCreate, BranchOut, BranchUpdate
from app.services.billing import check_max_branches

router = APIRouter(prefix="/businesses/{business_id}/branches", tags=["branches"])


def _clear_other_defaults(db: Session, business_id, exclude_id=None) -> None:
    """At most one branch per business is ever marked default."""
    query = db.query(Branch).filter(Branch.business_id == business_id, Branch.is_default.is_(True))
    if exclude_id is not None:
        query = query.filter(Branch.id != exclude_id)
    query.update({"is_default": False})


@router.post("", response_model=BranchOut, status_code=status.HTTP_201_CREATED)
def create_branch(
    payload: BranchCreate,
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    check_max_branches(db, business)

    branch = Branch(
        id=uuid.uuid4(),
        business_id=business.id,
        name=payload.name,
        address=payload.address,
        is_default=payload.is_default,
    )
    db.add(branch)
    if payload.is_default:
        db.flush()
        _clear_other_defaults(db, business.id, exclude_id=branch.id)
    db.commit()
    db.refresh(branch)
    return BranchOut.model_validate(branch)


@router.get("", response_model=list[BranchOut])
def list_branches(
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    branches = (
        db.query(Branch)
        .filter(Branch.business_id == business.id)
        .order_by(Branch.created_at.asc())
        .all()
    )
    return [BranchOut.model_validate(b) for b in branches]


@router.patch("/{branch_id}", response_model=BranchOut)
def update_branch(
    branch_id: uuid.UUID,
    payload: BranchUpdate,
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    branch = get_owned_branch(branch_id, business, db)
    if payload.name is not None:
        branch.name = payload.name
    if payload.address is not None:
        branch.address = payload.address
    if payload.is_default is not None:
        branch.is_default = payload.is_default
        if payload.is_default:
            _clear_other_defaults(db, business.id, exclude_id=branch.id)
    db.commit()
    db.refresh(branch)
    return BranchOut.model_validate(branch)


@router.delete("/{branch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_branch(
    branch_id: uuid.UUID,
    db: Session = Depends(get_db),
    business: Business = Depends(require_business_role("admin")),
):
    """
    Deleting a branch never deletes its transactions -- branch_id on
    Transaction is ON DELETE SET NULL, so those rows simply become
    unassigned again, exactly like a transaction that was never given a
    branch in the first place.
    """
    branch = get_owned_branch(branch_id, business, db)
    db.delete(branch)
    db.commit()
