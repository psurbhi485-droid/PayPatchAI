"""
PayPatch AI — Payment Webhook Handler (Simulated Backend)

VULNERABILITY DEMONSTRATION:
Payment gateways (Stripe, Adyen, Razorpay, etc.) guarantee at-least-once delivery.
In cases of network timeouts or server retries, the same webhook event ID
may be dispatched multiple times.

BUG DESCRIPTION:
This initial version does NOT verify if an incoming event_id has already been processed.
As a result, delivering the same event twice creates duplicate ledger entries and
causes double fulfillment / double charging.

NOTE: Real payment backends require atomic distributed deduplication (e.g. Redis SETNX,
distributed lock, or SQL UNIQUE constraint on event_id). An in-memory cache is used
here for prototype demonstration.
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


def process_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process incoming payment webhook events.

    BUG: No idempotency check is performed on payload['event_id'].
    Duplicate deliveries will create duplicate ledger records.
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

    # Intentional Bug: Directly appends to ledger without verifying if event_id was already handled!
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
