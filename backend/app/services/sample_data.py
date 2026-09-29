"""
Onboarding sample data (Step 13, Batch 4).

Lets a brand-new business see a fully populated dashboard -- sales,
expenses, stock, alerts, charts -- before it has entered anything of its
own. Everything inserted here is flagged `is_sample=True` so it can be
removed in one action without touching real data, and it never counts
against the plan's monthly transaction limit (see
app.services.billing.check_max_transactions_this_month).

The data is a small provision store in Naira, generated relative to
today (so it always looks recent) from a fixed random seed (so what you
get is identical every time, which keeps tests and screenshots stable).
Nothing here is loaded automatically -- only the explicit "load sample
data" action calls it.
"""
import random
import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.models.alert import Alert
from app.models.business import Business
from app.models.expense import Expense
from app.models.product_stock import ProductStock
from app.models.team_member import TeamMember
from app.models.transaction import Transaction
from app.services.import_pipeline import compute_fingerprint
from app.services.stock import find_stock_record, record_initial_quantity

SAMPLE_SEED = 20260101
SAMPLE_DAYS = 60

# (name, category, selling price, cost price, sales weight, units per sale,
#  stock on hand, reorder level)
_PRODUCTS = [
    ("Rice (50kg bag)", "Grains", 78000, 68000, 3, (1, 2), 14, 5),
    ("Vegetable oil (5L)", "Groceries", 12500, 10200, 5, (1, 3), 2, 8),  # low stock
    ("Indomie noodles (carton)", "Groceries", 8900, 7600, 6, (1, 4), 25, 10),
    ("Sugar (1kg)", "Groceries", 1800, 1450, 7, (2, 6), 40, 15),
    ("Bottled water (pack)", "Drinks", 2400, 1700, 8, (1, 5), 0, 15),  # out of stock
    ("Peak milk (tin)", "Groceries", 1500, 1200, 6, (2, 8), 60, 20),
    ("Tomato paste (carton)", "Groceries", 9500, 8000, 3, (1, 2), 18, 6),
    ("Garri (25kg bag)", "Grains", 21000, 17500, 4, (1, 3), 22, 8),
]
SAMPLE_PRODUCT_NAMES = [p[0] for p in _PRODUCTS]

_CUSTOMERS = ["Adebayo Stores", "Mama Chidi", "Tunde Ventures", "Ngozi Foods", None, None, None]
_PAYMENT_METHODS = ["Cash", "Transfer", "POS"]
_PAYMENT_WEIGHTS = [5, 3, 2]


def has_sample_data(db: Session, business_id: uuid.UUID) -> bool:
    return any(
        db.query(model.id).filter(model.business_id == business_id, model.is_sample.is_(True)).first() is not None
        for model in (Transaction, Expense, ProductStock)
    )


def _month_offset(today: date, months_back: int) -> tuple[int, int]:
    year, month = today.year, today.month - months_back
    while month <= 0:
        month += 12
        year -= 1
    return year, month


def _sample_transactions(business: Business, today: date) -> list[Transaction]:
    rng = random.Random(SAMPLE_SEED)
    weights = [p[4] for p in _PRODUCTS]
    rows: list[Transaction] = []
    for day_index in range(SAMPLE_DAYS):
        day = today - timedelta(days=SAMPLE_DAYS - 1 - day_index)
        count = rng.randint(2, 4)
        if day.weekday() in (4, 5):  # busier Fridays and Saturdays
            count += 1
        if day_index > 40 and rng.random() < 0.5:  # gentle upward trend
            count += 1
        for _ in range(count):
            name, category, selling, cost, _w, qty_range, _stock, _reorder = rng.choices(_PRODUCTS, weights=weights)[0]
            quantity = Decimal(rng.randint(*qty_range))
            row = {
                "date": day,
                "product": name,
                "quantity": quantity,
                "selling_price": Decimal(selling),
                "cost_price": Decimal(cost),
            }
            rows.append(
                Transaction(
                    id=uuid.uuid4(),
                    business_id=business.id,
                    import_session_id=None,
                    category=category,
                    customer=rng.choice(_CUSTOMERS),
                    payment_method=rng.choices(_PAYMENT_METHODS, weights=_PAYMENT_WEIGHTS)[0],
                    # A different hash input from any real row's ("sample:" prefix)
                    # so a later real import can never be mistaken for a duplicate
                    # of a sample row, or the reverse.
                    fingerprint=compute_fingerprint(f"sample:{business.id}", row),
                    is_sample=True,
                    **row,
                )
            )
    return rows


def _sample_expenses(business: Business, today: date) -> list[Expense]:
    rng = random.Random(SAMPLE_SEED + 1)
    rows: list[Expense] = []

    def add(on: date, category: str, amount: int, description: str) -> None:
        if today - timedelta(days=90) <= on <= today:
            rows.append(
                Expense(
                    id=uuid.uuid4(), business_id=business.id, date=on, category=category,
                    amount=Decimal(amount), description=description, is_sample=True,
                )
            )

    for months_back in range(3):
        year, month = _month_offset(today, months_back)
        add(date(year, month, 1), "Rent", 150000, "Shop rent")
        add(date(year, month, 10), "Internet & airtime", 12000, "Data and airtime")
        add(date(year, month, 15), "Electricity & power", 35000, "Power bills and generator diesel")
        add(date(year, month, 28), "Salaries & wages", 120000, "Two shop assistants")

    for offset in range(SAMPLE_DAYS):
        day = today - timedelta(days=offset)
        if day.weekday() == 0:  # a restocking trip every Monday
            add(day, "Transport & fuel", rng.choice([8000, 10000, 12000]), "Restocking trip")
    return rows


def load_sample_data(db: Session, business: Business, user_id: uuid.UUID | None) -> dict:
    """
    Inserts the sample sales, expenses and stock records, all flagged
    is_sample. Refuses if sample data is already loaded (running it twice
    would just double everything). Deliberately bypasses the plan's
    monthly transaction limit -- see the module docstring.
    """
    if has_sample_data(db, business.id):
        raise ValidationError("Sample data is already loaded for this business.", code="sample_data_already_loaded")

    today = date.today()
    transactions = _sample_transactions(business, today)
    expenses = _sample_expenses(business, today)
    db.add_all(transactions)
    db.add_all(expenses)

    stock_records: list[ProductStock] = []
    for name, _category, _selling, cost, _w, _range, stock_qty, reorder in _PRODUCTS:
        if find_stock_record(db, business.id, name, None) is not None:
            continue  # the business already tracks a product by this name -- leave theirs alone
        stock = ProductStock(
            id=uuid.uuid4(), business_id=business.id, product=name,
            quantity_on_hand=Decimal(stock_qty), reorder_level=Decimal(reorder),
            unit_cost=Decimal(cost), is_sample=True,
        )
        db.add(stock)
        stock_records.append(stock)

    # The session disables autoflush, and these adjustment rows reference
    # the stock rows by foreign key -- flush the parents first.
    db.flush()
    for stock in stock_records:
        record_initial_quantity(db, stock, user_id)
    db.commit()

    return {"transactions": len(transactions), "expenses": len(expenses), "stock_records": len(stock_records)}


def remove_sample_data(db: Session, business: Business) -> dict:
    """
    Deletes every is_sample row for the business and tidies the alerts
    that were derived from them. Real data is never touched.

    Alerts: with no real transactions left, every alert for the business
    can only have come from sample data (or data long since removed), so
    they all go. Otherwise only alerts about a product that exists in the
    sample set and NOT in the business's own remaining data are removed
    -- a real product that happens to share a sample product's name keeps
    its alerts.
    """
    transactions_removed = (
        db.query(Transaction)
        .filter(Transaction.business_id == business.id, Transaction.is_sample.is_(True))
        .delete(synchronize_session=False)
    )
    expenses_removed = (
        db.query(Expense)
        .filter(Expense.business_id == business.id, Expense.is_sample.is_(True))
        .delete(synchronize_session=False)
    )
    stock_removed = (
        db.query(ProductStock)
        .filter(ProductStock.business_id == business.id, ProductStock.is_sample.is_(True))
        .delete(synchronize_session=False)
    )

    real_transaction_exists = (
        db.query(Transaction.id).filter(Transaction.business_id == business.id).first() is not None
    )
    if not real_transaction_exists:
        alerts_removed = db.query(Alert).filter(Alert.business_id == business.id).delete(synchronize_session=False)
    else:
        real_names = {
            (name or "").lower()
            for (name,) in db.query(Transaction.product).filter(Transaction.business_id == business.id).distinct()
        } | {
            (name or "").lower()
            for (name,) in db.query(ProductStock.product).filter(ProductStock.business_id == business.id).distinct()
        }
        sample_only = {n.lower() for n in SAMPLE_PRODUCT_NAMES} - real_names
        alerts_removed = 0
        if sample_only:
            alerts_removed = (
                db.query(Alert)
                .filter(Alert.business_id == business.id, func.lower(Alert.affected_product).in_(sample_only))
                .delete(synchronize_session=False)
            )
    db.commit()

    return {
        "transactions": transactions_removed,
        "expenses": expenses_removed,
        "stock_records": stock_removed,
        "alerts": alerts_removed,
    }


def onboarding_status(db: Session, business: Business) -> dict:
    """Which getting-started milestones are done. Sample rows never count
    -- the checklist is about the business's OWN data."""

    def exists(model) -> bool:
        return (
            db.query(model.id).filter(model.business_id == business.id, model.is_sample.is_(False)).first()
            is not None
        )

    invited_someone = (
        db.query(TeamMember.id)
        .filter(
            TeamMember.business_id == business.id,
            TeamMember.role != "owner",
            TeamMember.status.in_(("pending", "active")),
        )
        .first()
        is not None
    )
    return {
        "add_sales": exists(Transaction),
        "record_expense": exists(Expense),
        "track_stock": exists(ProductStock),
        "invite_team": invited_someone,
        "has_sample_data": has_sample_data(db, business.id),
    }
