"""
PayPatch AI — Stripe Integration & Idempotent Persistence Service
Handles:
1. Stripe Checkout Session creation in test mode, raw signature verification, and SQLite persistence.
2. LOCAL SIMULATION mode with HMAC-SHA256 constant-time signature verification for local testing
   while Stripe India account approval is pending.
Enforces unique event_id constraints in SQLite so duplicate deliveries are safely deduplicated.
"""

import os
import sqlite3
import json
import logging
import hmac
import hashlib
import time
from typing import Dict, Any, List, Tuple, Optional
from dotenv import load_dotenv
import stripe

# Load environment variables
load_dotenv()

logger = logging.getLogger("paypatch.stripe")

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(WORKSPACE_DIR, "stripe_events.db")
DEFAULT_LOCAL_WEBHOOK_SECRET = "whsec_local_sim_dev_secret_key"


def get_db_path(custom_path: Optional[str] = None) -> str:
    return custom_path or os.environ.get("STRIPE_DB_PATH", DEFAULT_DB_PATH)


def init_db(db_path: Optional[str] = None):
    """Initialize SQLite database with strict unique constraint on event_id and source tracking."""
    path = get_db_path(db_path)
    with sqlite3.connect(path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stripe_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                currency TEXT NOT NULL,
                customer_email TEXT,
                status TEXT NOT NULL,
                source TEXT DEFAULT 'stripe_test',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Ensure 'source' column exists if upgrading older database
        cursor.execute("PRAGMA table_info(stripe_events)")
        columns = [info[1] for info in cursor.fetchall()]
        if "source" not in columns:
            cursor.execute("ALTER TABLE stripe_events ADD COLUMN source TEXT DEFAULT 'stripe_test'")
        conn.commit()


def is_configured() -> bool:
    """Check if Stripe secret key is configured."""
    return bool(os.environ.get("STRIPE_SECRET_KEY"))


def get_local_webhook_secret() -> str:
    """Get the local webhook signing secret (used ONLY for local simulation, never for Stripe)."""
    return os.environ.get("LOCAL_WEBHOOK_SECRET", DEFAULT_LOCAL_WEBHOOK_SECRET)


# =====================================================================
# LOCAL SIMULATION CRYPTOGRAPHY (HMAC-SHA256 Constant-Time Verification)
# =====================================================================

def compute_local_signature(
    raw_body: bytes,
    secret: Optional[str] = None,
    timestamp: Optional[int] = None,
) -> str:
    """
    Computes an HMAC-SHA256 signature for local webhook testing.
    Format matches standard webhook signing headers: t={timestamp},v1={hex_signature}.
    """
    signing_secret = secret or get_local_webhook_secret()
    t = timestamp if timestamp is not None else int(time.time())
    signed_payload = f"{t}.".encode("utf-8") + raw_body
    sig = hmac.new(
        signing_secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    return f"t={t},v1={sig}"


def verify_local_signature(
    raw_body: bytes,
    sig_header: Optional[str],
    secret: Optional[str] = None,
    tolerance_seconds: int = 300,
) -> bool:
    """
    Verifies local simulation webhook signature using constant-time comparison (hmac.compare_digest).
    Rejects malformed headers, expired timestamps, or invalid digests.
    """
    if not sig_header:
        return False

    signing_secret = secret or get_local_webhook_secret()

    # Parse t={timestamp},v1={hash}
    timestamp_val: Optional[int] = None
    signatures: List[str] = []

    for item in sig_header.split(","):
        parts = item.strip().split("=", 1)
        if len(parts) == 2:
            key, val = parts[0].strip(), parts[1].strip()
            if key == "t":
                try:
                    timestamp_val = int(val)
                except ValueError:
                    return False
            elif key == "v1":
                signatures.append(val)

    if timestamp_val is None or not signatures:
        return False

    # Optional timestamp tolerance check (prevent replay attacks if specified)
    if tolerance_seconds > 0:
        now = int(time.time())
        if abs(now - timestamp_val) > tolerance_seconds:
            logger.warning("Local simulation webhook timestamp expired: %s vs %s", timestamp_val, now)
            return False

    signed_payload = f"{timestamp_val}.".encode("utf-8") + raw_body
    expected_sig = hmac.new(
        signing_secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    # Constant-time comparison to prevent timing side-channel attacks
    for sig in signatures:
        if hmac.compare_digest(expected_sig, sig):
            return True

    return False


# =====================================================================
# REAL STRIPE SDK CHECKOUT & WEBHOOK (TEST MODE)
# =====================================================================

def create_checkout_session(
    success_url: Optional[str] = None,
    cancel_url: Optional[str] = None,
    secret_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates a Stripe Checkout Session in test mode with a fixed demo amount of INR 50 (5000 paise).
    """
    key = secret_key or os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        raise ValueError("Stripe is not configured. Please set STRIPE_SECRET_KEY in your backend .env file.")

    stripe.api_key = key

    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:5173")
    final_success_url = success_url or f"{frontend_url}/?stripe_status=success&session_id={{CHECKOUT_SESSION_ID}}"
    final_cancel_url = cancel_url or f"{frontend_url}/?stripe_status=cancelled"

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[
            {
                "price_data": {
                    "currency": "inr",
                    "product_data": {
                        "name": "PayPatch AI — Test Payment (50 INR)",
                        "description": "Idempotent payment test transaction for PayPatch AI agent review",
                    },
                    "unit_amount": 5000,  # 5000 paise = 50 INR
                },
                "quantity": 1,
            }
        ],
        mode="payment",
        success_url=final_success_url,
        cancel_url=final_cancel_url,
    )

    return {
        "checkout_url": session.url,
        "session_id": session.id,
        "amount_cents": 5000,
        "currency": "inr",
    }


def verify_and_construct_event(
    raw_body: bytes,
    sig_header: Optional[str],
    webhook_secret: Optional[str] = None,
) -> Any:
    """
    Verifies Stripe signature using exact raw bytes and STRIPE_WEBHOOK_SECRET.
    Never uses LOCAL_WEBHOOK_SECRET for real Stripe webhooks.
    """
    secret = webhook_secret or os.environ.get("STRIPE_WEBHOOK_SECRET")
    if not secret:
        raise ValueError("Stripe webhook secret is not configured. Set STRIPE_WEBHOOK_SECRET in .env.")

    if not sig_header:
        raise ValueError("Missing stripe-signature header in webhook request.")

    # Must pass exact raw request body bytes
    event = stripe.Webhook.construct_event(
        payload=raw_body,
        sig_header=sig_header,
        secret=secret,
    )
    return event


def save_verified_event(
    event: Dict[str, Any],
    db_path: Optional[str] = None,
    source: str = "stripe_test",
) -> Tuple[bool, str]:
    """
    Persists verified event ID in SQLite with unique constraint.
    Transactional operation ensures atomic insertion.
    Returns:
      (True, "created") if newly inserted
      (True, "duplicate_skipped") if duplicate event_id already exists (idempotent 2xx)
    Raises Exception on database error (leads to retryable 5xx).
    """
    path = get_db_path(db_path)
    init_db(path)

    event_id = event.get("id")
    event_type = event.get("type", "unknown")

    if not event_id:
        raise ValueError("Invalid event payload: missing 'id'")

    # Extract payment metadata safely
    data_obj = event.get("data", {}).get("object", {})
    amount_cents = data_obj.get("amount_total") or data_obj.get("amount") or 5000
    currency = data_obj.get("currency", "inr")
    customer_email = data_obj.get("customer_details", {}).get("email") or data_obj.get("receipt_email") or ""
    status = data_obj.get("payment_status") or data_obj.get("status") or "captured"

    with sqlite3.connect(path) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute(
                """
                INSERT INTO stripe_events (
                    event_id, event_type, amount_cents, currency, customer_email, status, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, event_type, amount_cents, currency, customer_email, status, source),
            )
            conn.commit()
            return True, "created"
        except sqlite3.IntegrityError:
            conn.rollback()
            # Duplicate delivery caught by PRIMARY KEY constraint
            return True, "duplicate_skipped"
        except Exception:
            conn.rollback()
            raise


def list_recent_stripe_events(
    limit: int = 15,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Returns recent verified events from SQLite.
    Never exposes secrets, authorization tokens, or sensitive card numbers.
    Clearly distinguishes local simulation from real Stripe events.
    """
    path = get_db_path(db_path)
    init_db(path)

    with sqlite3.connect(path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT event_id, event_type, amount_cents, currency, customer_email, status, source, created_at
            FROM stripe_events
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        return [
            {
                "event_id": r[0],
                "event_type": r[1],
                "amount_cents": r[2],
                "currency": r[3],
                "customer_email": r[4],
                "status": r[5],
                "source": r[6] if len(r) > 6 and r[6] else "stripe_test",
                "is_simulated": (r[6] == "local_simulation") if len(r) > 6 else False,
                "created_at": r[7] if len(r) > 7 else r[6],
            }
            for r in rows
        ]


def process_webhook_payload(
    raw_body: bytes,
    sig_header: Optional[str],
    webhook_secret: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Tuple[int, Dict[str, Any]]:
    """
    Real Stripe webhook verification and SQLite persistence pipeline.
    Uses official Stripe SDK and STRIPE_WEBHOOK_SECRET.
    Returns (status_code, data_dict).
    """
    try:
        event = verify_and_construct_event(raw_body, sig_header, webhook_secret=webhook_secret)
    except ValueError as e:
        return 400, {"error": f"Invalid payload or missing signature: {str(e)}", "is_simulated": False}
    except stripe.error.SignatureVerificationError:
        return 400, {"error": "Invalid Stripe signature.", "is_simulated": False}
    except Exception as e:
        return 400, {"error": f"Signature verification failed: {str(e)}", "is_simulated": False}

    try:
        event_dict = (
            event.to_dict_recursive()
            if hasattr(event, "to_dict_recursive")
            else dict(event)
        )
        _, action = save_verified_event(event_dict, db_path=db_path, source="stripe_test")

        if action == "duplicate_skipped":
            return 200, {
                "status": "duplicate_skipped",
                "event_id": event_dict.get("id"),
                "source": "stripe_test",
                "is_simulated": False,
                "message": "Duplicate event delivery safely deduplicated by SQLite unique constraint.",
                "is_duplicate": True,
            }

        return 200, {
            "status": "success",
            "event_id": event_dict.get("id"),
            "source": "stripe_test",
            "is_simulated": False,
            "message": "Stripe webhook verified and persisted in SQLite.",
            "is_duplicate": False,
        }
    except Exception as e:
        return 500, {"error": f"Database persistence failure: {str(e)}", "is_simulated": False}


# =====================================================================
# LOCAL SIMULATION PIPELINE (Zero Stripe Account Dependency)
# =====================================================================

def create_simulated_checkout_session(
    amount_cents: int = 5000,
    currency: str = "inr",
) -> Dict[str, Any]:
    """
    Creates a simulated checkout session locally without contacting Stripe servers.
    Returns a local redirect URL that triggers the local simulation return page.
    """
    import uuid
    sim_session_id = f"sim_cs_{uuid.uuid4().hex[:12]}"
    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:5173")
    simulated_url = f"{frontend_url}/?simulated_checkout=success&session_id={sim_session_id}&amount=50"

    return {
        "checkout_url": simulated_url,
        "session_id": sim_session_id,
        "amount_cents": amount_cents,
        "currency": currency,
        "source": "local_simulation",
        "is_simulated": True,
        "mode": "LOCAL SIMULATION (Offline Dev)",
    }


def process_simulated_webhook(
    raw_body: bytes,
    sig_header: Optional[str],
    local_secret: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Tuple[int, Dict[str, Any]]:
    """
    Local simulation webhook verification and SQLite persistence pipeline.
    1. Verifies HMAC-SHA256 signature using constant-time comparison (hmac.compare_digest).
    2. Enforces unique event_id constraint in SQLite.
    3. Safely deduplicates retries (returns HTTP 200 duplicate_skipped).
    4. Transactionally records without duplicating ledger or DB entries.
    5. Returns retryable HTTP 500 on database failure.
    """
    # 1. Verify signature with constant-time comparison
    is_valid = verify_local_signature(raw_body, sig_header, secret=local_secret)
    if not is_valid:
        return 400, {
            "error": "Invalid local simulation signature. Signature mismatch or expired timestamp.",
            "source": "local_simulation",
            "is_simulated": True,
        }

    # 2. Parse payload
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        return 400, {
            "error": f"Malformed JSON in simulated payload: {str(e)}",
            "source": "local_simulation",
            "is_simulated": True,
        }

    event_id = payload.get("id")
    if not event_id:
        return 400, {
            "error": "Missing mandatory 'id' field in simulated event payload.",
            "source": "local_simulation",
            "is_simulated": True,
        }

    # 3. Transactionally persist in SQLite
    try:
        _, action = save_verified_event(payload, db_path=db_path, source="local_simulation")

        if action == "duplicate_skipped":
            return 200, {
                "status": "duplicate_skipped",
                "event_id": event_id,
                "source": "local_simulation",
                "is_simulated": True,
                "is_duplicate": True,
                "message": "Duplicate simulated webhook event safely deduplicated by SQLite constraint.",
            }

        return 200, {
            "status": "success",
            "event_id": event_id,
            "source": "local_simulation",
            "is_simulated": True,
            "is_duplicate": False,
            "message": "Local simulated webhook verified and persisted in SQLite.",
        }
    except Exception as e:
        return 500, {
            "error": f"Database persistence failure: {str(e)}",
            "source": "local_simulation",
            "is_simulated": True,
        }
