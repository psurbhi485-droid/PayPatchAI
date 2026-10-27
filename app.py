"""
PayPatch AI — AI Coding Agent for Payment Backend Systems
Streamlit Interactive Dashboard (Executive & Developer Review)

Palette Direction:
- Obsidian Black: #111110
- Graphite: #242321
- Champagne Gold: #D6B779
- Warm Ivory: #F5F0E7
- Muted Taupe: #A49A89
- Restrained Green: #10B981
- Restrained Red: #EF4444
"""

import os
import streamlit as st
import agent_engine

st.set_page_config(
    page_title="PayPatch AI — Payment Backend Agent",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling strictly adhering to Obsidian Black & Champagne Gold Palette
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
        background-color: #111110 !important;
        color: #F5F0E7 !important;
    }
    .stApp {
        background-color: #111110 !important;
    }
    header, [data-testid="stHeader"] {
        background: transparent !important;
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #181816 !important;
        border-right: 1px solid rgba(214, 183, 121, 0.15) !important;
    }

    /* Cards */
    .premium-card {
        background: #1B1A18;
        border: 1px solid rgba(214, 183, 121, 0.2);
        border-radius: 12px;
        padding: 24px;
        margin-bottom: 20px;
        box-shadow: 0 8px 30px rgba(0, 0, 0, 0.4);
    }

    .badge-gold {
        background: rgba(214, 183, 121, 0.12);
        border: 1px solid #D6B779;
        color: #D6B779;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 0.5px;
        display: inline-block;
    }
    .badge-red {
        background: rgba(239, 68, 68, 0.15);
        border: 1px solid #EF4444;
        color: #EF4444;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 0.78rem;
        font-weight: 600;
        display: inline-block;
    }
    .badge-green {
        background: rgba(16, 185, 129, 0.15);
        border: 1px solid #10B981;
        color: #10B981;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 0.78rem;
        font-weight: 600;
        display: inline-block;
    }

    /* Primary Buttons */
    div.stButton > button:first-child {
        background: linear-gradient(135deg, #D6B779 0%, #B89655 100%) !important;
        color: #111110 !important;
        font-weight: 600 !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 8px 20px !important;
        transition: all 0.2s ease-in-out !important;
    }
    div.stButton > button:first-child:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 15px rgba(214, 183, 121, 0.3) !important;
    }

    /* Terminal Console */
    .terminal-box {
        background-color: #0B0B0A;
        border: 1px solid rgba(214, 183, 121, 0.2);
        border-radius: 8px;
        padding: 16px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.85rem;
        color: #F5F0E7;
        white-space: pre-wrap;
        overflow-x: auto;
    }

    /* Diff styling */
    .diff-add { color: #10B981; background: rgba(16, 185, 129, 0.1); }
    .diff-del { color: #EF4444; background: rgba(239, 68, 68, 0.1); }
</style>
""", unsafe_allow_html=True)

# Helper to read current file
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
PAYMENT_BUG_PATH = os.path.join(WORKSPACE_DIR, "payment_bug.py")

def get_current_code():
    if os.path.exists(PAYMENT_BUG_PATH):
        with open(PAYMENT_BUG_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return agent_engine.BUGGY_CODE

# Session state initialization
if "patch_result" not in st.session_state:
    st.session_state.patch_result = None
if "test_result" not in st.session_state:
    st.session_state.test_result = None
if "sim_result" not in st.session_state:
    st.session_state.sim_result = None

current_code = get_current_code()
is_current_patched = "_processed_event_ids" in current_code

# Header
st.markdown("""
<div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(214, 183, 121, 0.2); padding-bottom: 16px; margin-bottom: 24px;">
    <div>
        <span class="badge-gold">AUTONOMOUS BACKEND AGENT</span>
        <h1 style="color: #F5F0E7; margin: 8px 0 4px 0; font-size: 2.2rem; font-weight: 700;">PayPatch AI</h1>
        <p style="color: #A49A89; margin: 0; font-size: 0.95rem;">
            Automated Idempotency Defenses & Regression Testing for Payment Backend Gateways
        </p>
    </div>
    <div style="text-align: right;">
        <span style="color: #A49A89; font-size: 0.8rem; display: block;">TARGET TARGET MODULE</span>
        <code style="color: #D6B779; background: #1B1A18; padding: 4px 8px; border-radius: 4px;">payment_bug.py</code>
    </div>
</div>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown("### Agent Settings")
    api_key_input = st.text_input("Gemini / Groq API Key (Optional)", type="password", placeholder="Leave empty for Safe Fallback")
    
    st.markdown("---")
    st.markdown("### System Status")
    if is_current_patched:
        st.markdown('<span class="badge-green">STATUS: PATCHED (IDEMPOTENT)</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="badge-red">STATUS: VULNERABLE (UNPROTECTED)</span>', unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("""
    <div style="font-size: 0.82rem; color: #A49A89; line-height: 1.5;">
        <strong style="color: #D6B779;">Architecture Note:</strong><br/>
        This prototype demonstrates idempotency using an in-memory set. 
        In distributed production architectures (Stripe/Adyen), persistent atomicity is mandatory:
        <ul style="padding-left: 18px; margin-top: 6px;">
            <li>Redis <code>SETNX</code> with TTL</li>
            <li>Postgres <code>UNIQUE(event_id)</code></li>
            <li>Distributed Redlock</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

    if st.button("↺ Revert to Buggy State", use_container_width=True):
        with open(PAYMENT_BUG_PATH, "w", encoding="utf-8") as f:
            f.write(agent_engine.BUGGY_CODE)
        st.session_state.patch_result = None
        st.session_state.test_result = None
        st.session_state.sim_result = None
        st.rerun()

# Workflow Steps Tabs
tab1, tab2, tab3, tab4 = st.tabs(["1. Bug Reproduction", "2. AI Patch & Diff", "3. Isolated Pytest Sandbox", "4. Human Approval Gate"])

# TAB 1: Bug Reproduction
with tab1:
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("#### Vulnerability Scenario: Duplicate Webhook Delivery")
        st.markdown("""
        Payment gateways deliver webhooks with **at-least-once guarantee**. 
        If network timeouts or retry storms occur, event `evt_pay_9981a2` will be sent twice.
        
        Without idempotency deduplication, the backend creates duplicate ledger entries and charges the buyer twice.
        """)
        
        if st.button("▶ Reproduce Bug (Simulate Duplicate Webhook)", key="btn_repro"):
            st.session_state.sim_result = agent_engine.simulate_duplicate_webhook(current_code)
            
        if st.session_state.sim_result:
            sim = st.session_state.sim_result
            if sim.get("duplicate_created"):
                st.markdown("""
                <div class="premium-card" style="border-color: rgba(239, 68, 68, 0.4);">
                    <span class="badge-red">DUPLICATE CHARGE DETECTED</span>
                    <h3 style="color: #EF4444; margin-top: 8px;">Financial Anomaly Confirmed</h3>
                    <p style="color: #F5F0E7;">
                        Delivered event <code>evt_pay_9981a2</code> twice.<br/>
                        <b>Initial Ledger Count:</b> {initial}<br/>
                        <b>Final Ledger Count:</b> {final}<br/>
                        <b>Total Double Charged:</b> ${amount:.2f}
                    </p>
                </div>
                """.format(
                    initial=sim["initial_ledger_count"],
                    final=sim["final_ledger_count"],
                    amount=sim["double_charged_cents"] / 100.0
                ), unsafe_allow_html=True)
            else:
                st.markdown("""
                <div class="premium-card" style="border-color: rgba(16, 185, 129, 0.4);">
                    <span class="badge-green">IDEMPOTENT BEHAVIOR VERIFIED</span>
                    <h3 style="color: #10B981; margin-top: 8px;">Duplicate Safely Intercepted</h3>
                    <p style="color: #F5F0E7;">
                        Delivered event <code>evt_pay_9981a2</code> twice.<br/>
                        Duplicate delivery skipped duplicate ledger insertion.<br/>
                        <b>Total Charged:</b> ${amount:.2f}
                    </p>
                </div>
                """.format(amount=sim["double_charged_cents"] / 100.0), unsafe_allow_html=True)
                
    with col2:
        st.markdown("#### Current Target Code (`payment_bug.py`)")
        st.code(current_code, language="python")

# TAB 2: AI Patch & Diff
with tab2:
    col_patch1, col_patch2 = st.columns([1, 1])
    with col_patch1:
        st.markdown("#### Autonomous Patch Generation")
        st.markdown("Click below to invoke PayPatch AI to analyze AST vulnerabilities and propose an idempotency patch.")
        
        if st.button("⚡ Fix with PayPatch AI", key="btn_fix"):
            with st.spinner("Analyzing AST and synthesizing idempotent patch..."):
                st.session_state.patch_result = agent_engine.generate_patch(
                    api_key=api_key_input if api_key_input else None
                )

        if st.session_state.patch_result:
            res = st.session_state.patch_result
            badge_class = "badge-gold" if not res["is_fallback"] else "badge-gold"
            st.markdown(f'<span class="{badge_class}">{res["source"].upper()}</span>', unsafe_allow_html=True)
            st.markdown(f"**AST Validation:** `{res['validation_status']}`")
            st.markdown(f"**Analysis:** {res['explanation']}")

    with col_patch2:
        if st.session_state.patch_result:
            st.markdown("#### Proposed Code Diff")
            diff_data = agent_engine.compute_code_diff(current_code, st.session_state.patch_result["patch_code"])
            st.markdown(f"Changes: <span style='color: #10B981;'>+{diff_data['additions']}</span> | <span style='color: #EF4444;'>-{diff_data['deletions']}</span>", unsafe_allow_html=True)
            st.code(diff_data["unified_diff"], language="diff")
        else:
            st.info("Click 'Fix with PayPatch AI' to generate the idempotency patch and inspect diff.")

# TAB 3: Isolated Pytest Sandbox
with tab3:
    st.markdown("#### Isolated Pytest Sandbox Execution")
    st.markdown("""
    PayPatch AI **never claims a patch works without running real tests**.
    Candidate code is mounted into an ephemeral sandbox directory and executed with `pytest` under strict timeouts.
    """)
    
    test_col1, test_col2 = st.columns(2)
    with test_col1:
        if st.button("🧪 Run Pytest on Current Code"):
            with st.spinner("Running sandbox pytest on current code..."):
                st.session_state.test_result = agent_engine.run_isolated_pytest(current_code)
                st.session_state.test_target = "Current Code"
    with test_col2:
        if st.session_state.patch_result:
            if st.button("🧪 Run Pytest on Proposed Patch"):
                with st.spinner("Running sandbox pytest on proposed patch..."):
                    st.session_state.test_result = agent_engine.run_isolated_pytest(st.session_state.patch_result["patch_code"])
                    st.session_state.test_target = "Proposed Patch"

    if st.session_state.test_result:
        t_res = st.session_state.test_result
        if t_res["success"]:
            st.markdown(f'<span class="badge-green">PASSED ({t_res["passed_tests"]}/{t_res["total_tests"]} TESTS) — {t_res["duration"]}s</span>', unsafe_allow_html=True)
        else:
            st.markdown(f'<span class="badge-red">FAILED ({t_res["failed_tests"]} FAILURES) — {t_res["duration"]}s</span>', unsafe_allow_html=True)

        st.markdown(f"**Target:** {st.session_state.get('test_target', 'Candidate')}")
        st.markdown("##### Real Terminal Output (Pytest Subprocess):")
        st.markdown(f'<div class="terminal-box">{t_res["stdout"] or t_res["stderr"]}</div>', unsafe_allow_html=True)

# TAB 4: Human Approval Gate
with tab4:
    st.markdown("#### Human-in-the-Loop Approval & Deployment Gate")
    st.markdown("AI agents propose solutions; developers hold final authority. Review and explicitly approve before modifying disk.")
    
    if st.session_state.patch_result:
        patch_code = st.session_state.patch_result["patch_code"]
        chk1 = st.checkbox("I have reviewed the code diff and confirmed idempotency semantics.")
        chk2 = st.checkbox("I have verified that isolated pytest regression tests passed without failures.")
        
        if st.button("✓ Approve & Apply Patch to Local Backend"):
            if not chk1 or not chk2:
                st.error("Approval Blocked: You must confirm both review checkboxes before applying patch.")
            else:
                with open(PAYMENT_BUG_PATH, "w", encoding="utf-8") as f:
                    f.write(patch_code)
                st.success("Patch successfully approved and written to payment_bug.py!")
                st.rerun()
    else:
        st.info("No patch generated yet. Go to Tab 2 to generate a patch first.")
