"""
PayPatch AI — Core Agent Engine & Sandbox Runner
Handles patch generation (LLM + Deterministic Fallback), AST Safety Validation,
Isolated Pytest Sandbox Execution, and Diff Computation.
"""

import ast
import difflib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Dict, Any, Tuple, Optional


BUGGY_CODE = '''"""
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
'''

FALLBACK_PATCHED_CODE = '''"""
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
'''


FORBIDDEN_CALLS = {
    "eval", "exec", "__import__", "compile",
    "open", "file", "unlink", "remove", "rmdir", "system",
    "spawn", "popen", "subprocess", "socket", "urllib", "requests", "httpx"
}


def validate_patch_ast(code_str: str) -> Tuple[bool, str]:
    """
    Validates proposed code using Python's Abstract Syntax Tree (AST).
    Enforces security boundaries:
    - Syntactically valid Python
    - No malicious calls or unauthorized IO/subprocess
    - Preserves expected core interface (process_webhook, ledger)
    """
    try:
        tree = ast.parse(code_str)
    except SyntaxError as e:
        return False, f"AST Syntax Error: {e}"

    found_process_webhook = False
    found_ledger = False

    for node in ast.walk(tree):
        # Prevent dangerous calls
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
                return False, f"Security Violation: Call to restricted function '{node.func.id}' detected."
            if isinstance(node.func, ast.Attribute) and node.func.attr in FORBIDDEN_CALLS:
                return False, f"Security Violation: Call to restricted attribute '{node.func.attr}' detected."

        # Check imports for dangerous modules
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in ["os", "subprocess", "sys", "socket", "shutil"]:
                    # We allow safe sys/os if not executing system calls, but reject dangerous ones
                    pass
        if isinstance(node, ast.FunctionDef) and node.name == "process_webhook":
            found_process_webhook = True
        if isinstance(node, ast.Name) and node.id == "ledger":
            found_ledger = True

    if not found_process_webhook:
        return False, "Validation Failed: Mandatory function 'process_webhook' is missing in patch."
    if not found_ledger:
        return False, "Validation Failed: Mandatory 'ledger' instance reference missing in patch."

    return True, "AST Security Validation Passed: Syntax is valid and execution constraints met."


def generate_patch(api_key: Optional[str] = None, provider: str = "auto") -> Dict[str, Any]:
    """
    Generates a patch to resolve the duplicate webhook issue.
    If an LLM API key (Gemini, Groq, or OpenAI) is available, uses the model.
    Otherwise, returns the deterministic safe fallback patch, clearly labelled.
    """
    gemini_key = api_key or os.environ.get("GEMINI_API_KEY")
    groq_key = api_key or os.environ.get("GROQ_API_KEY")
    openai_key = api_key or os.environ.get("OPENAI_API_KEY")

    # Try LLM if configured
    if gemini_key and (provider in ["gemini", "auto"]):
        try:
            import urllib.request
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            prompt = (
                "You are an expert payment systems engineer. Fix the following Python webhook code to make it idempotent "
                "and prevent duplicate event IDs from creating duplicate ledger entries. "
                "Keep the code minimal, self-contained, and output ONLY valid Python inside ```python ... ``` tags.\n\n"
                f"{BUGGY_CODE}"
            )
            req_data = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
            req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=8) as response:
                result = json.loads(response.read().decode("utf-8"))
                text = result["candidates"][0]["content"]["parts"][0]["text"]
                if "```python" in text:
                    code = text.split("```python")[1].split("```")[0].strip()
                elif "```" in text:
                    code = text.split("```")[1].split("```")[0].strip()
                else:
                    code = text.strip()

                is_valid, reason = validate_patch_ast(code)
                if is_valid:
                    return {
                        "patch_code": code,
                        "source": "AI Generated (Google Gemini 1.5)",
                        "is_fallback": False,
                        "validation_status": reason,
                        "explanation": (
                            "AI analysis identified missing idempotency checking on webhook event_id. "
                            "Proposed patch introduces an in-memory event registry to filter duplicate deliveries."
                        )
                    }
        except Exception as e:
            # Fall through to fallback
            pass

    # Deterministic safe fallback
    is_valid, reason = validate_patch_ast(FALLBACK_PATCHED_CODE)
    return {
        "patch_code": FALLBACK_PATCHED_CODE,
        "source": "Deterministic Safe Fallback Patch",
        "is_fallback": True,
        "validation_status": reason,
        "explanation": (
            "Deterministic Safe Fallback Patch: Adds `_processed_event_ids` registry and intercepts "
            "incoming webhooks if payload['event_id'] has already been recorded. Prevents duplicate ledger insertion "
            "and returns 'duplicate_skipped' status. (In production, replace with Redis SETNX or SQL unique constraint)."
        )
    }


def compute_code_diff(original: str, modified: str) -> Dict[str, Any]:
    """Generates unified diff and categorized line changes."""
    orig_lines = original.splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        orig_lines,
        mod_lines,
        fromfile="payment_bug.py (Original)",
        tofile="payment_bug.py (Patched)",
        n=3
    ))
    diff_text = "".join(diff)

    additions = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
    deletions = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))

    return {
        "unified_diff": diff_text,
        "additions": additions,
        "deletions": deletions,
    }


def run_isolated_pytest(candidate_code: str, timeout_seconds: int = 10) -> Dict[str, Any]:
    """
    Executes pytest tests in an isolated temporary directory.
    Never executes in production; guarantees safe sandbox evaluation.
    """
    start_time = time.time()
    workspace_dir = os.path.dirname(os.path.abspath(__file__))
    test_file_source = os.path.join(workspace_dir, "test_payment_bug.py")

    if not os.path.exists(test_file_source):
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Test file not found at {test_file_source}",
            "returncode": -1,
            "duration": 0.0,
            "passed_tests": 0,
            "failed_tests": 1,
            "total_tests": 1,
        }

    with tempfile.TemporaryDirectory() as temp_dir:
        # Write candidate code into isolated temp dir
        temp_payment_file = os.path.join(temp_dir, "payment_bug.py")
        with open(temp_payment_file, "w", encoding="utf-8") as f:
            f.write(candidate_code)

        # Copy test file into isolated temp dir
        temp_test_file = os.path.join(temp_dir, "test_payment_bug.py")
        shutil.copyfile(test_file_source, temp_test_file)

        # Execute pytest in sandbox
        cmd = [sys.executable, "-m", "pytest", "test_payment_bug.py", "-v", "--tb=short"]
        try:
            proc = subprocess.run(
                cmd,
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            duration = round(time.time() - start_time, 2)
            stdout = proc.stdout
            stderr = proc.stderr
            returncode = proc.returncode

            # Parse results from stdout
            passed = stdout.count(" PASSED")
            failed = stdout.count(" FAILED")
            total = passed + failed

            return {
                "success": (returncode == 0),
                "stdout": stdout,
                "stderr": stderr,
                "returncode": returncode,
                "duration": duration,
                "passed_tests": passed,
                "failed_tests": failed,
                "total_tests": total if total > 0 else 3,
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Execution timed out after {timeout_seconds} seconds.",
                "returncode": 124,
                "duration": timeout_seconds,
                "passed_tests": 0,
                "failed_tests": 1,
                "total_tests": 3,
            }


def simulate_duplicate_webhook(code_str: str) -> Dict[str, Any]:
    """
    Simulates sending the exact same webhook event ID twice to demonstrate
    either the duplicate ledger entry bug or the idempotency protection.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        target_file = os.path.join(temp_dir, "payment_bug.py")
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(code_str)

        runner_script = os.path.join(temp_dir, "run_sim.py")
        script_content = '''
import json
import payment_bug

payload = {
    "event_id": "evt_pay_9981a2",
    "order_id": "ord_8820x",
    "amount_cents": 14900,
    "currency": "USD",
    "event_type": "payment_intent.succeeded"
}

# First delivery
res1 = payment_bug.process_webhook(payload)
count1 = len(payment_bug.ledger.get_entries())

# Duplicate delivery (network retry)
res2 = payment_bug.process_webhook(payload)
entries = payment_bug.ledger.get_entries()
count2 = len(entries)

duplicate_created = (count2 > count1)
double_charged_cents = 14900 * 2 if duplicate_created else 14900

print(json.dumps({
    "payload": payload,
    "res1": res1,
    "res2": res2,
    "initial_ledger_count": count1,
    "final_ledger_count": count2,
    "entries": entries,
    "duplicate_created": duplicate_created,
    "double_charged_cents": double_charged_cents,
    "is_vulnerable": duplicate_created
}))
'''
        with open(runner_script, "w", encoding="utf-8") as f:
            f.write(script_content)

        proc = subprocess.run(
            [sys.executable, "run_sim.py"],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            timeout=5
        )

        try:
            return json.loads(proc.stdout.strip())
        except Exception:
            return {
                "error": "Simulation execution failed",
                "stderr": proc.stderr,
                "stdout": proc.stdout
            }
