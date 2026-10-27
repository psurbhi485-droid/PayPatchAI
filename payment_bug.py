"""
PayPatch AI — Payment Webhook Handler (Patched with Idempotency Protection)

IDEMPOTENCY PROTECTION:
Tracks processed event IDs using an idempotency registry.
Duplicate deliveries are safely intercepted and return a duplicate acknowledgment
without re-inserting into the payment ledger.

NOTE: An in-memory set is used here for demonstration purposes.
In production distributed payment architectures (Stripe/Adyen/etc.), use:
- Redis SETNX with atomic TTL
- SQL database UNIQUE constraint on `event_id` with `ON CONFLICT DO NOTHING`
- Distributed idempotency key locking
"""

from typing import Dict, Any, List, Optional
import time
import uuid


class PaymentLedger:
    """Simulated in-memory payment database and transaction ledger."""

    def __init__(self):
        self.entries: List[Dict[str, Any]] = []

    def add_entry(self, event_id: str, order_id: str, amount_cents: int, currency: str, status: str) -> Dict[str, Any]:
        entry = {
            "ledger_id": f"leg_{uuid.uuid4().hex[:8]}",
            "event_id": event_id,
            "order_id": order_id,
            "amount_cents": amount_cents,
            "currency": currency,
            "status": status,
            "timestamp": time.time(),
        }
        self.entries.append(entry)
        return entry

    def get_entries(self) -> List[Dict[str, Any]]:
        return list(self.entries)

    def find_by_event_id(self, event_id: str) -> List[Dict[str, Any]]:
        return [e for e in self.entries if e["event_id"] == event_id]

    def clear(self):
        self.entries.clear()


# Global simulated ledger instance
ledger = PaymentLedger()

# Idempotency registry for event deduplication
# (In-memory demonstration; use persistent store like Redis/Postgres in production)
_processed_event_ids: set[str] = set()


def clear_idempotency_cache():
    """Reset the idempotency cache for testing or maintenance."""
    _processed_event_ids.clear()


def process_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process incoming payment webhook events with idempotency verification.
    """
    event_id = payload.get("event_id")
    order_id = payload.get("order_id")
    amount_cents = payload.get("amount_cents", 0)
    currency = payload.get("currency", "USD")
    event_type = payload.get("event_type", "payment_intent.succeeded")

    if not event_id or not order_id:
        return {
            "status": "error",
            "error": "Missing required fields: event_id and order_id are mandatory",
            "processed": False,
        }

    # IDEMPOTENCY CHECK:
    # If the event_id has already been processed, skip re-execution
    if event_id in _processed_event_ids:
        existing_entries = ledger.find_by_event_id(event_id)
        existing_ledger_id = existing_entries[0]["ledger_id"] if existing_entries else None
        return {
            "status": "duplicate_skipped",
            "message": f"Idempotency Guard: Event {event_id} already processed. Duplicate skipped.",
            "event_id": event_id,
            "order_id": order_id,
            "ledger_id": existing_ledger_id,
            "processed": False,
            "is_duplicate": True,
        }

    # Register event_id before or immediately upon processing
    _processed_event_ids.add(event_id)

    entry = ledger.add_entry(
        event_id=event_id,
        order_id=order_id,
        amount_cents=amount_cents,
        currency=currency,
        status="captured",
    )

    return {
        "status": "success",
        "message": "Payment recorded successfully",
        "event_id": event_id,
        "order_id": order_id,
        "ledger_id": entry["ledger_id"],
        "processed": True,
        "is_duplicate": False,
    }
