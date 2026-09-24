"""
Transaction helpers shared by the routes and every importer (Step 13,
Batch 1 -- manual transaction entry, editing and deleting).

Two jobs:

1. existing_fingerprints(): the single answer to "which of these source
   rows should an importer skip?". Used by the file import and by both the
   Google Sheets and Excel syncs, so all three agree. A row is skipped if a
   transaction with its fingerprint exists OR if it has been tombstoned
   (an imported sale a person deleted or edited in the app -- see
   app.models.transaction_tombstone for why that matters).

2. remember_imported_fingerprint(): called when a person edits or deletes
   a transaction, to leave that tombstone behind.
"""
import uuid
from typing import Iterable

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.transaction import Transaction
from app.models.transaction_tombstone import TransactionTombstone


def existing_fingerprints(db: Session, business_id: uuid.UUID, fingerprints: Iterable[str]) -> set[str]:
    """
    The subset of `fingerprints` an importer must not insert again: already
    stored on a transaction for this business, or tombstoned. One query per
    source, not one per row.
    """
    candidates = list(fingerprints)
    if not candidates:
        return set()

    on_transactions = {
        row[0]
        for row in db.query(Transaction.fingerprint)
        .filter(Transaction.business_id == business_id, Transaction.fingerprint.in_(candidates))
        .all()
    }
    tombstoned = {
        row[0]
        for row in db.query(TransactionTombstone.fingerprint)
        .filter(
            TransactionTombstone.business_id == business_id,
            TransactionTombstone.fingerprint.in_(candidates),
        )
        .all()
    }
    return on_transactions | tombstoned


def remember_imported_fingerprint(db: Session, transaction: Transaction) -> None:
    """
    Tombstone this transaction's *current* fingerprint, if it came from an
    import or sync. Manually entered transactions (no import session) leave
    nothing behind, so the same sale can still be imported later.

    Does not commit -- the caller commits it together with the edit/delete
    so the two can never get out of step. Safe to call twice for the same
    fingerprint (the unique constraint makes the second insert a no-op).
    """
    if transaction.import_session_id is None or not transaction.fingerprint:
        return
    db.execute(
        pg_insert(TransactionTombstone)
        .values(id=uuid.uuid4(), business_id=transaction.business_id, fingerprint=transaction.fingerprint)
        .on_conflict_do_nothing(constraint="uq_transaction_tombstones_business_fingerprint")
    )
