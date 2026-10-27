"""
Automated Test Suite for Stripe Test-Mode Integration & Idempotent Webhook Processing
Tests:
1. Valid Stripe signature verification and SQLite persistence.
2. Invalid Stripe signature rejection (returns 400).
3. Duplicate event ID idempotency (second webhook returns 200 duplicate_skipped, table count = 1).
4. Persistence across database reconnects in SQLite.
5. Missing configuration handled gracefully (returns 400).
6. Sanitized event listing without secret exposure.
7. Existing API routes (/api/status, /api/code, /api/reproduce, etc.) continue functioning.
"""

import os
import tempfile
import sqlite3
from unittest.mock import patch, MagicMock
import pytest
from fastapi import HTTPException
import stripe

import server
import stripe_service


@pytest.fixture
def temp_db():
    """Provides a fresh isolated SQLite database for each test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    stripe_service.init_db(db_path)
    old_env = os.environ.get("STRIPE_DB_PATH")
    os.environ["STRIPE_DB_PATH"] = db_path

    yield db_path

    if old_env:
        os.environ["STRIPE_DB_PATH"] = old_env
    else:
        os.environ.pop("STRIPE_DB_PATH", None)

    try:
        os.remove(db_path)
    except OSError:
        pass


def test_checkout_session_missing_key():
    """Verify that creating a session without STRIPE_SECRET_KEY raises HTTP 400 with helpful error."""
    with patch.dict(os.environ, {"STRIPE_SECRET_KEY": ""}):
        with pytest.raises(HTTPException) as exc_info:
            server.create_stripe_checkout()
        assert exc_info.value.status_code == 400
        assert "Stripe is not configured" in exc_info.value.detail


def test_checkout_session_success_mocked():
    """Verify Checkout Session creation with mocked Stripe SDK for fixed INR 50 (5000 paise)."""
    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/c/pay/cs_test_mock123"
    mock_session.id = "cs_test_mock123"

    with patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_mock_dummy_key"}), \
         patch("stripe.checkout.Session.create", return_value=mock_session) as mock_create:

        data = server.create_stripe_checkout(server.StripeCheckoutRequest(
            success_url="http://localhost:5173/?stripe_status=success",
            cancel_url="http://localhost:5173/?stripe_status=cancelled",
        ))

        assert data["checkout_url"] == "https://checkout.stripe.com/c/pay/cs_test_mock123"
        assert data["session_id"] == "cs_test_mock123"
        assert data["amount_cents"] == 5000
        assert data["currency"] == "inr"

        # Verify call arguments
        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        assert kwargs["payment_method_types"] == ["card"]
        assert kwargs["line_items"][0]["price_data"]["unit_amount"] == 5000
        assert kwargs["line_items"][0]["price_data"]["currency"] == "inr"


def test_webhook_invalid_signature():
    """Verify that invalid Stripe signatures are rejected with HTTP 400."""
    with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": "whsec_test_secret"}):
        with patch("stripe.Webhook.construct_event", side_effect=stripe.error.SignatureVerificationError("Sig mismatch", "bad_sig")):
            code, res = stripe_service.process_webhook_payload(
                raw_body=b'{"id": "evt_test_fake"}',
                sig_header="t=123,v1=bad_sig",
                webhook_secret="whsec_test_secret",
            )
            assert code == 400
            assert "Invalid Stripe signature" in res["error"]


def test_webhook_valid_signature_persists_event(temp_db):
    """Verify that a validly signed event is parsed and stored in SQLite."""
    mock_event = {
        "id": "evt_stripe_real_001",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "amount_total": 5000,
                "currency": "inr",
                "customer_details": {"email": "buyer@example.com"},
                "payment_status": "paid"
            }
        }
    }

    with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": "whsec_test_secret"}), \
         patch("stripe.Webhook.construct_event", return_value=mock_event):

        code, res = stripe_service.process_webhook_payload(
            raw_body=b'{"id": "evt_stripe_real_001"}',
            sig_header="t=123,v1=valid_sig",
            webhook_secret="whsec_test_secret",
            db_path=temp_db,
        )
        assert code == 200
        assert res["status"] == "success"
        assert res["event_id"] == "evt_stripe_real_001"

    # Verify event stored in SQLite
    with sqlite3.connect(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT event_id, event_type, amount_cents, currency, status FROM stripe_events WHERE event_id = ?", ("evt_stripe_real_001",))
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "evt_stripe_real_001"
        assert row[1] == "checkout.session.completed"
        assert row[2] == 5000
        assert row[3] == "inr"


def test_webhook_duplicate_event_id_idempotent(temp_db):
    """
    CRITICAL IDEMPOTENCY TEST:
    Verify delivering the same event twice returns HTTP 200 duplicate_skipped
    and SQLite stores exactly ONE record.
    """
    mock_event = {
        "id": "evt_stripe_dup_999",
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "amount": 5000,
                "currency": "inr",
                "receipt_email": "retry@example.com",
                "status": "succeeded"
            }
        }
    }

    with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": "whsec_test_secret"}), \
         patch("stripe.Webhook.construct_event", return_value=mock_event):

        # 1. First delivery
        code1, res1 = stripe_service.process_webhook_payload(
            raw_body=b'{"id": "evt_stripe_dup_999"}',
            sig_header="t=123,v1=valid_sig",
            webhook_secret="whsec_test_secret",
            db_path=temp_db,
        )
        assert code1 == 200
        assert res1["status"] == "success"

        # 2. Duplicate retry delivery
        code2, res2 = stripe_service.process_webhook_payload(
            raw_body=b'{"id": "evt_stripe_dup_999"}',
            sig_header="t=123,v1=valid_sig",
            webhook_secret="whsec_test_secret",
            db_path=temp_db,
        )
        assert code2 == 200
        assert res2["status"] == "duplicate_skipped"
        assert res2["is_duplicate"] is True

    # Verify database has exactly 1 entry
    with sqlite3.connect(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM stripe_events WHERE event_id = ?", ("evt_stripe_dup_999",))
        count = cursor.fetchone()[0]
        assert count == 1, f"Expected 1 record due to unique constraint, got {count}!"


def test_persistence_after_restart(temp_db):
    """Verify that records persist across database reconnects (not in-memory transient)."""
    event = {
        "id": "evt_persist_check",
        "type": "checkout.session.completed",
        "data": {"object": {"amount_total": 5000, "currency": "inr"}}
    }
    stripe_service.save_verified_event(event, db_path=temp_db)

    # Reconnect and list
    events = stripe_service.list_recent_stripe_events(limit=10, db_path=temp_db)
    event_ids = [e["event_id"] for e in events]
    assert "evt_persist_check" in event_ids


def test_list_stripe_events_sanitized(temp_db):
    """Verify GET /api/stripe/events returns sanitized records with no secrets."""
    event = {
        "id": "evt_sanitized_001",
        "type": "payment_intent.succeeded",
        "data": {"object": {"amount": 5000, "currency": "inr", "customer_details": {"email": "user@test.com"}}}
    }
    stripe_service.save_verified_event(event, db_path=temp_db)

    res = server.list_stripe_events()
    events = res["events"]
    assert len(events) >= 1
    target = next((e for e in events if e["event_id"] == "evt_sanitized_001"), None)
    assert target is not None
    assert "secret" not in str(target).lower()


def test_existing_routes_still_work():
    """Verify that all existing endpoints continue working without regression."""
    # 1. /api/status
    res = server.get_status()
    assert "current_state" in res
    assert "has_stripe_key" in res
    assert "has_stripe_webhook_secret" in res

    # 2. /api/code
    code_res = server.get_code()
    assert "code" in code_res

    # 3. /api/reproduce
    sim_res = server.reproduce_bug()
    assert "duplicate_created" in sim_res
