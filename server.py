"""
PayPatch AI — FastAPI Backend Server
Provides API endpoints for Bug Reproduction, AI Patch Generation, AST Validation,
Isolated Pytest Sandbox Execution, Code Diffs, and Developer Approval Workflow.
"""

import os
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import stripe
import agent_engine
import stripe_service

app = FastAPI(
    title="PayPatch AI API",
    description="AI Coding Agent for Payment Backend Systems",
    version="1.0.0"
)

# Enable CORS for React Vite development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
PAYMENT_BUG_PATH = os.path.join(WORKSPACE_DIR, "payment_bug.py")


def read_current_code() -> str:
    if os.path.exists(PAYMENT_BUG_PATH):
        with open(PAYMENT_BUG_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return agent_engine.BUGGY_CODE


class PatchRequest(BaseModel):
    api_key: Optional[str] = None
    provider: Optional[str] = "auto"


class TestRequest(BaseModel):
    code: Optional[str] = None


class DiffRequest(BaseModel):
    original: Optional[str] = None
    modified: str


class ApprovalRequest(BaseModel):
    patch_code: str
    reviewer_name: Optional[str] = "Developer"
    confirmed_idempotency: bool
    verified_tests: bool


@app.get("/api/status")
def get_status():
    current_code = read_current_code()
    is_patched = "_processed_event_ids" in current_code
    return {
        "status": "ready",
        "current_state": "patched" if is_patched else "buggy",
        "has_gemini_key": bool(os.environ.get("GEMINI_API_KEY")),
        "has_groq_key": bool(os.environ.get("GROQ_API_KEY")),
        "has_openai_key": bool(os.environ.get("OPENAI_API_KEY")),
        "has_stripe_key": stripe_service.is_configured(),
        "has_stripe_webhook_secret": bool(os.environ.get("STRIPE_WEBHOOK_SECRET")),
        "local_simulation_enabled": True,
        "has_local_webhook_secret": bool(stripe_service.get_local_webhook_secret()),
    }


@app.get("/api/code")
def get_code():
    code = read_current_code()
    is_patched = "_processed_event_ids" in code
    return {
        "code": code,
        "is_patched": is_patched,
        "filename": "payment_bug.py"
    }


@app.post("/api/reproduce")
def reproduce_bug():
    current_code = read_current_code()
    simulation_result = agent_engine.simulate_duplicate_webhook(current_code)
    return simulation_result


@app.post("/api/generate-patch")
def generate_patch(req: PatchRequest):
    result = agent_engine.generate_patch(api_key=req.api_key, provider=req.provider or "auto")
    return result


@app.post("/api/diff")
def get_diff(req: DiffRequest):
    original = req.original or read_current_code()
    diff_data = agent_engine.compute_code_diff(original, req.modified)
    return diff_data


@app.post("/api/run-tests")
def run_tests(req: TestRequest):
    code_to_test = req.code or read_current_code()
    test_result = agent_engine.run_isolated_pytest(code_to_test)
    return test_result


@app.post("/api/approve-patch")
def approve_patch(req: ApprovalRequest):
    if not req.confirmed_idempotency or not req.verified_tests:
        raise HTTPException(
            status_code=400,
            detail="Human review required: Please confirm idempotency review and test verification checkboxes before approving."
        )

    # Re-validate patch AST before writing to disk
    is_valid, reason = agent_engine.validate_patch_ast(req.patch_code)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"Safety Check Failed: {reason}")

    with open(PAYMENT_BUG_PATH, "w", encoding="utf-8") as f:
        f.write(req.patch_code)

    return {
        "success": True,
        "message": f"Patch successfully approved and applied to payment_bug.py by {req.reviewer_name}.",
        "filename": "payment_bug.py"
    }


@app.post("/api/revert")
def revert_to_buggy():
    with open(PAYMENT_BUG_PATH, "w", encoding="utf-8") as f:
        f.write(agent_engine.BUGGY_CODE)

    return {
        "success": True,
        "message": "payment_bug.py has been reverted to the initial buggy state.",
        "current_state": "buggy"
    }


# =====================================================================
# STRIPE TEST-MODE INTEGRATION & IDEMPOTENT WEBHOOK PROCESSING
# =====================================================================

class StripeCheckoutRequest(BaseModel):
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


@app.post("/api/stripe/create-checkout-session")
def create_stripe_checkout(req: Optional[StripeCheckoutRequest] = None):
    """
    Creates a Stripe Checkout Session in test mode with a fixed demo amount of INR 50 (5000 paise).
    """
    try:
        success_url = req.success_url if req else None
        cancel_url = req.cancel_url if req else None
        session_data = stripe_service.create_checkout_session(
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return session_data
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create Stripe Checkout session: {str(e)}"
        )


@app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    """
    Processes incoming Stripe webhooks:
    1. Verifies the cryptographic signature against STRIPE_WEBHOOK_SECRET using raw bytes.
    2. Rejects invalid signatures with HTTP 400.
    3. Persists verified events in SQLite with unique event_id constraint.
    4. Safely deduplicates retries (returns HTTP 2xx duplicate_skipped).
    5. Returns retryable HTTP 500 if persistence fails.
    """
    raw_body = await request.body()
    sig_header = request.headers.get("stripe-signature")

    status_code, result = stripe_service.process_webhook_payload(raw_body, sig_header)
    if status_code >= 400:
        raise HTTPException(
            status_code=status_code,
            detail=result.get("error", "Webhook processing error")
        )
    return result


@app.get("/api/stripe/events")
def list_stripe_events():
    """
    Lists recent verified Stripe events from SQLite.
    Never exposes secrets, authorization tokens, or sensitive card details.
    """
    events = stripe_service.list_recent_stripe_events()
    return {"events": events}


# =====================================================================
# LOCAL SIMULATION MODE (Zero Stripe Credentials Required)
# =====================================================================

class DispatchSimulatedRequest(BaseModel):
    event_id: Optional[str] = None
    amount_cents: Optional[int] = 5000
    currency: Optional[str] = "inr"
    customer_email: Optional[str] = "local.dev@example.com"
    event_type: Optional[str] = "checkout.session.completed"


@app.post("/api/simulated/create-session")
def create_simulated_session():
    """
    Creates a simulated checkout session locally without contacting Stripe servers.
    Clearly labelled LOCAL SIMULATION.
    """
    return stripe_service.create_simulated_checkout_session()


@app.post("/api/simulated/webhook")
async def simulated_webhook(request: Request):
    """
    Local simulation webhook receiver:
    1. Verifies HMAC-SHA256 signature using LOCAL_WEBHOOK_SECRET and constant-time comparison.
    2. Never uses LOCAL_WEBHOOK_SECRET for real Stripe events.
    3. Rejects invalid signatures with HTTP 400.
    4. Persists in SQLite enforcing unique event_id constraint.
    5. Returns HTTP 200 duplicate_skipped on retries without duplicating records.
    """
    raw_body = await request.body()
    sig_header = request.headers.get("x-paypatch-signature") or request.headers.get("stripe-signature")

    status_code, result = stripe_service.process_simulated_webhook(raw_body, sig_header)
    if status_code >= 400:
        raise HTTPException(
            status_code=status_code,
            detail=result.get("error", "Local simulation webhook processing error")
        )
    return result


@app.post("/api/simulated/dispatch-event")
def dispatch_simulated_event(req: Optional[DispatchSimulatedRequest] = None):
    """
    Developer helper to construct, sign, and dispatch a simulated webhook event.
    Enables testing first delivery vs duplicate delivery with 1 click directly in the dashboard.
    """
    import uuid
    import json

    params = req or DispatchSimulatedRequest()
    event_id = params.event_id or f"evt_sim_{uuid.uuid4().hex[:10]}"

    payload = {
        "id": event_id,
        "type": params.event_type or "checkout.session.completed",
        "data": {
            "object": {
                "id": f"cs_sim_{event_id}",
                "amount_total": params.amount_cents or 5000,
                "currency": params.currency or "inr",
                "customer_details": {"email": params.customer_email or "local.dev@example.com"},
                "payment_status": "paid",
            }
        },
        "source": "local_simulation",
        "is_simulated": True,
    }

    raw_body = json.dumps(payload).encode("utf-8")
    sig_header = stripe_service.compute_local_signature(raw_body)

    status_code, result = stripe_service.process_simulated_webhook(raw_body, sig_header)
    if status_code >= 400:
        raise HTTPException(status_code=status_code, detail=result.get("error"))

    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
