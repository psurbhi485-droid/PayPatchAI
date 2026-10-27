"""
PayPatch AI — Automated Regression Test Suite
Target: payment_bug.py webhook idempotency handling.

TEST SPECIFICATION:
1. test_first_webhook_event_processed_successfully: Verifies initial payment processing.
2. test_duplicate_webhook_event_does_not_duplicate_ledger: Verifies idempotency on duplicate event_id.
   - FAILS on original buggy code (creates 2 ledger entries).
   - PASSES on patched code (detects duplicate and skips extra ledger entry).
3. test_different_webhook_events_processed_successfully: Verifies distinct events are both recorded.
"""

import pytest
import payment_bug


@pytest.fixture(autouse=True)
def reset_ledger_state():
    """Ensure a clean ledger and idempotency state before each test run."""
    payment_bug.ledger.clear()
    # If the patched version defines an idempotency registry, clear it as well
    if hasattr(payment_bug, "_processed_event_ids"):
        payment_bug._processed_event_ids.clear()
    elif hasattr(payment_bug, "clear_idempotency_cache"):
        payment_bug.clear_idempotency_cache()
    yield
    payment_bug.ledger.clear()
    if hasattr(payment_bug, "_processed_event_ids"):
        payment_bug._processed_event_ids.clear()
    elif hasattr(payment_bug, "clear_idempotency_cache"):
        payment_bug.clear_idempotency_cache()


def test_first_webhook_event_processed_successfully():
    """Verify that a valid first-time webhook event records in the ledger."""
    payload = {
        "event_id": "evt_test_001",
        "order_id": "ord_1001",
        "amount_cents": 4900,
        "currency": "USD",
        "event_type": "payment_intent.succeeded",
    }
    response = payment_bug.process_webhook(payload)

    assert response["status"] == "success", f"Expected success, got {response}"
    assert response["processed"] is True

    entries = payment_bug.ledger.get_entries()
    assert len(entries) == 1, f"Expected 1 ledger entry, found {len(entries)}"
    assert entries[0]["event_id"] == "evt_test_001"
    assert entries[0]["order_id"] == "ord_1001"
    assert entries[0]["amount_cents"] == 4900


def test_duplicate_webhook_event_does_not_duplicate_ledger():
    """
    CRITICAL IDEMPOTENCY TEST:
    Verifies that delivering the same webhook event ID twice does NOT create
    a duplicate ledger entry or cause double fulfillment.
    """
    payload = {
        "event_id": "evt_test_dup_001",
        "order_id": "ord_1002",
        "amount_cents": 9900,
        "currency": "USD",
        "event_type": "payment_intent.succeeded",
    }

    # 1. First delivery
    first_res = payment_bug.process_webhook(payload)
    assert first_res["status"] == "success"
    assert len(payment_bug.ledger.get_entries()) == 1

    # 2. Duplicate delivery (simulated retry/network delay)
    second_res = payment_bug.process_webhook(payload)

    entries = payment_bug.ledger.get_entries()
    assert len(entries) == 1, (
        f"CRITICAL FAILURE: Duplicate webhook event_id '{payload['event_id']}' "
        f"caused duplicate ledger entry! Expected 1 entry, found {len(entries)}. "
        "Double charging / double fulfillment occurred."
    )
    assert second_res.get("is_duplicate") is True or second_res.get("status") in [
        "duplicate_skipped",
        "idempotent_duplicate",
        "success",
    ]


def test_different_webhook_events_processed_successfully():
    """Verify that distinct events are both processed correctly without cross-interference."""
    payload_a = {
        "event_id": "evt_diff_001",
        "order_id": "ord_2001",
        "amount_cents": 1500,
        "currency": "USD",
    }
    payload_b = {
        "event_id": "evt_diff_002",
        "order_id": "ord_2002",
        "amount_cents": 2500,
        "currency": "USD",
    }

    res_a = payment_bug.process_webhook(payload_a)
    res_b = payment_bug.process_webhook(payload_b)

    assert res_a["processed"] is True
    assert res_b["processed"] is True

    entries = payment_bug.ledger.get_entries()
    assert len(entries) == 2, f"Expected 2 distinct ledger entries, found {len(entries)}"
    event_ids = {e["event_id"] for e in entries}
    assert "evt_diff_001" in event_ids
    assert "evt_diff_002" in event_ids
