"""
Ujjwal Rail - AI Train Travel Assistant
Single-Page Application with Internal Routing (HCLTech Hackathon)
"""

import streamlit as st
import os
import sys
import json
import sqlite3
from datetime import datetime

# Path setup
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from frontend.api_client import UjjwalRailClient

# ----------------------------------------------------------------------
# Page Configuration & Design System
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="Ujjwal Rail Assistant",
    page_icon="🚆",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Zinc Theme Styling
CUSTOM_CSS = """
<style>
    /* Metric & Card styling */
    .metric-card {
        background-color: #18181b;
        border: 1px solid #27272a;
        border-radius: 8px;
        padding: 1rem 1.25rem;
        margin-bottom: 1rem;
    }
    .ticket-badge {
        display: inline-block;
        padding: 0.25rem 0.6rem;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.8rem;
    }
    .badge-cnf { background-color: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid #22c55e; }
    .badge-rac { background-color: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid #f59e0b; }
    .badge-wl { background-color: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #ef4444; }
    .badge-can { background-color: rgba(113, 113, 122, 0.2); color: #a1a1aa; border: 1px solid #71717a; }
    
    .action-box {
        background: linear-gradient(135deg, rgba(245, 158, 11, 0.08), rgba(239, 68, 68, 0.08));
        border: 1px solid #f59e0b;
        border-radius: 8px;
        padding: 1rem;
        margin-top: 0.75rem;
    }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ----------------------------------------------------------------------
# Helper: Fetch Sample Passengers & Bookings for Quick Testing
# ----------------------------------------------------------------------
@st.cache_data
def get_passengers_list():
    db_path = os.path.join(CURRENT_DIR, "data", "ujjwal_rail.db")
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT passenger_id, name, preferred_language FROM passengers ORDER BY passenger_id ASC")
            rows = [dict(r) for r in c.fetchall()]
            conn.close()
            return rows
        except Exception:
            pass
    return [{"passenger_id": "PASS-001", "name": "Aarav Sharma", "preferred_language": "en"}]

passengers_data = get_passengers_list()
passenger_options = {f"{p['passenger_id']} - {p['name']} ({p['preferred_language']})": p['passenger_id'] for p in passengers_data}

# ----------------------------------------------------------------------
# Internal Routing State Management (Single-Page App)
# ----------------------------------------------------------------------
if "route" not in st.session_state:
    st.session_state.route = st.query_params.get("route", "chat")

if "selected_trace_id" not in st.session_state:
    st.session_state.selected_trace_id = ""

if "selected_booking_id" not in st.session_state:
    st.session_state.selected_booking_id = "UR-10001"

if "messages" not in st.session_state:
    st.session_state.messages = []

def navigate_to(route_name: str, **kwargs):
    st.session_state.route = route_name
    st.query_params["route"] = route_name
    for k, v in kwargs.items():
        st.session_state[k] = v
        st.query_params[k] = v
    st.rerun()

# ----------------------------------------------------------------------
# Sidebar: Global Context (Section 6 Header Contract)
# ----------------------------------------------------------------------
with st.sidebar:
    st.title("🚆 Ujjwal Rail")
    st.caption("AI-Powered Train Travel Assistant")
    
    st.markdown("---")
    st.subheader("⚙️ Backend Connection")
    backend_url = st.text_input("FastAPI Endpoint", value="http://localhost:8000")
    client = UjjwalRailClient(base_url=backend_url)
    
    health = client.check_health()
    if health.get("online"):
        st.success("🟢 API Online (200 OK)")
    else:
        st.error(f"🔴 API Offline ({health.get('error', 'Unreachable')})")
        st.caption("💡 Run `uvicorn backend.server:app --reload` to start the backend.")

    st.markdown("---")
    st.subheader("👤 Caller Identity (X-Passenger-Id)")
    sel_pax_label = st.selectbox(
        "Active Passenger",
        options=list(passenger_options.keys()),
        index=0
    )
    active_passenger_id = passenger_options[sel_pax_label]
    st.info(f"Requests will include header:\n`X-Passenger-Id: {active_passenger_id}`")

    st.markdown("---")
    st.subheader("⏱️ Temporal Simulation (`as_of`)")
    use_custom_time = st.checkbox("Simulate Custom Timestamp", value=False)
    if use_custom_time:
        sim_date = st.date_input("Simulation Date", value=datetime(2026, 11, 21))
        sim_time = st.time_input("Simulation Time", value=datetime.now().time())
        as_of_timestamp = f"{sim_date}T{sim_time.strftime('%H:%M:%S')}+05:30"
        st.caption(f"Testing against date: `{as_of_timestamp}`")
    else:
        as_of_timestamp = datetime.now().isoformat()

    st.markdown("---")
    if st.button("🗑️ Clear Chat History"):
        st.session_state.messages = []
        st.rerun()

# ----------------------------------------------------------------------
# Top Navigation Bar (Internal Router Controller)
# ----------------------------------------------------------------------
ROUTES = {
    "chat": "💬 Assistant Chat & Actions",
    "bookings": "🎫 Booking Inspector",
    "rules": "📜 Rules Ledger & Adjuster",
    "ingest": "📥 Live Ingestion",
    "trace": "🔍 Trace Observability"
}

nav_cols = st.columns([1, 1, 1, 1, 1])
for idx, (route_key, route_label) in enumerate(ROUTES.items()):
    is_active = (st.session_state.route == route_key)
    btn_type = "primary" if is_active else "secondary"
    if nav_cols[idx].button(route_label, key=f"nav_{route_key}", type=btn_type, use_container_width=True):
        navigate_to(route_key)

st.markdown("---")

# ----------------------------------------------------------------------
# ROUTE 1: 💬 Chat & Safe Action Flow
# ----------------------------------------------------------------------
if st.session_state.route == "chat":
    st.subheader("💬 Ujjwal Rail Travel Assistant")
    st.caption("Ask questions about timetables, seat availability, refund calculations, rules, or manage bookings safely.")

    # Quick prompt chips
    st.markdown("**Quick test queries:**")
    quick_cols = st.columns(4)
    if quick_cols[0].button("🎫 Check My Booking (UR-10001)"):
        st.session_state.quick_query = "What is the status of my ticket UR-10001?"
    if quick_cols[1].button("🐕 Pet dog in 2AC?"):
        st.session_state.quick_query = "Can I carry my pet dog in 2AC coach?"
    if quick_cols[2].button("💰 Refund for UR-30419"):
        st.session_state.quick_query = "If I cancel my ticket UR-30419 now, how much refund will I get?"
    if quick_cols[3].button("🚫 Cancel Booking UR-30418"):
        st.session_state.quick_query = "Cancel my ticket UR-30418"

    # Display chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            
            # If response contained citations
            if msg.get("sources"):
                with st.expander("📚 Official Rules & Circulars Cited"):
                    for src in msg["sources"]:
                        st.markdown(f"- **{src.get('doc_id')}**: {src.get('section', '')}")

            # If response proposed a Level 1 action
            if msg.get("pending_action"):
                p_act = msg["pending_action"]
                act_id = p_act.get("action_id")
                st.markdown(f"""
                <div class="action-box">
                    <strong>⚠️ Action Approval Required (Level 1 Safe Action)</strong><br>
                    <span>Action ID: <code>{act_id}</code> | Type: <code>{p_act.get('type')}</code> | Target: <code>{p_act.get('booking_id')}</code></span><br>
                    <small>Expires at: {p_act.get('expires_at')}</small>
                </div>
                """, unsafe_allow_html=True)

                act_cols = st.columns([1, 1, 3])
                if act_cols[0].button("✅ Confirm Action", key=f"conf_{act_id}", type="primary"):
                    conf_res = client.confirm_action(act_id, active_passenger_id)
                    if conf_res.get("success"):
                        st.success(f"Action Confirmed! {conf_res['data'].get('message', '')}")
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": f"✅ {conf_res['data'].get('message', 'Action confirmed successfully.')}"
                        })
                        st.rerun()
                    else:
                        st.error(f"Confirmation failed: {conf_res.get('error')}")

                if act_cols[1].button("❌ Cancel Action", key=f"drop_{act_id}"):
                    drop_res = client.cancel_action(act_id, active_passenger_id)
                    if drop_res.get("success"):
                        st.info("Proposed action dropped. No changes were made.")
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": "❌ Proposed action has been safely cancelled. No changes were made to your booking."
                        })
                        st.rerun()

            # Clickable trace inspector button
            if msg.get("trace_id"):
                trc = msg["trace_id"]
                if st.button(f"🔍 Inspect Trace ({trc})", key=f"trc_btn_{trc}"):
                    navigate_to("trace", selected_trace_id=trc)

    # Input prompt
    input_text = st.chat_input("Type your message in English, Hindi, or Hinglish...")
    if "quick_query" in st.session_state and st.session_state.quick_query:
        input_text = st.session_state.quick_query
        st.session_state.quick_query = None

    if input_text:
        # Append user message
        st.session_state.messages.append({"role": "user", "content": input_text})
        
        # Call Backend
        with st.spinner("Assistant is checking railway tables & rules..."):
            session_id = f"sess_{active_passenger_id}"
            res = client.send_chat(
                passenger_id=active_passenger_id,
                session_id=session_id,
                message=input_text,
                as_of=as_of_timestamp
            )

        if res.get("success"):
            data = res["data"]
            st.session_state.messages.append({
                "role": "assistant",
                "content": data.get("answer", ""),
                "answer_type": data.get("answer_type"),
                "sources": data.get("sources", []),
                "tools": data.get("tools", []),
                "pending_action": data.get("pending_action"),
                "handed_to_human": data.get("handed_to_human"),
                "trace_id": data.get("trace_id")
            })
            st.rerun()
        else:
            st.error(f"Error calling /chat endpoint: {res.get('error')}")

# ----------------------------------------------------------------------
# ROUTE 2: 🎫 Booking Inspector (GET /bookings/{id})
# ----------------------------------------------------------------------
elif st.session_state.route == "bookings":
    st.subheader("🎫 Booking Inspector (`GET /bookings/{id}`)")
    st.caption("Judges and passengers use this endpoint to inspect booking records. Verifies Section 3 R8 privacy rules.")

    col1, col2 = st.columns([3, 1])
    search_b_id = col1.text_input("Enter Booking ID", value=st.session_state.selected_booking_id)
    if col2.button("Fetch Booking", use_container_width=True):
        st.session_state.selected_booking_id = search_b_id

    b_res = client.get_booking(search_b_id, active_passenger_id)
    if b_res.get("success"):
        bk = b_res["data"]
        st.success(f"Verified Ownership: Booking belongs to active passenger `{active_passenger_id}`.")
        
        status_cls = {
            "CONFIRMED": "badge-cnf",
            "RAC": "badge-rac",
            "WL": "badge-wl",
            "CANCELLED": "badge-can"
        }.get(bk["status"], "badge-can")

        st.markdown(f"""
        <div class="metric-card">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <h3>🚆 Booking Reference: {bk['booking_id']}</h3>
                <span class="ticket-badge {status_cls}">{bk['status']}</span>
            </div>
            <p><strong>Train:</strong> {bk['train_no']} ({bk.get('train_name', 'Express')}) | <strong>Class:</strong> {bk['class']}</p>
            <p><strong>Journey:</strong> {bk.get('from_name', bk['from_code'])} ➔ {bk.get('to_name', bk['to_code'])} on <strong>{bk['journey_date']}</strong></p>
            <p><strong>Amount Paid:</strong> ₹{bk['amount_paid']} | <strong>Booked At:</strong> {bk['booked_at']}</p>
        </div>
        """, unsafe_allow_html=True)

        st.subheader("👥 Travellers Allotted")
        travellers = bk.get("travellers", [])
        if travellers:
            st.dataframe(travellers, use_container_width=True)
        else:
            st.info("No traveller details attached.")

        st.markdown("---")
        st.subheader("⚡ Available Safe Actions")
        if bk["status"] not in ("CANCELLED", "OPERATOR_CANCELLED"):
            if st.button("Request Ticket Cancellation (Preview Refund)"):
                navigate_to("chat", quick_query=f"Cancel my ticket {bk['booking_id']}")
        else:
            st.warning("This booking is already cancelled.")

    else:
        st.error(f"Access Denied or Not Found: {b_res.get('error', 'Booking inaccessible.')}")
        st.info("💡 **R8 Privacy Guarantee:** Passengers can only view their own bookings. If this booking belongs to another passenger, a polite refusal is returned without disclosing existence.")

# ----------------------------------------------------------------------
# ROUTE 3: 📜 Rules Ledger & Safe Adjuster (Predefined vs Amended)
# ----------------------------------------------------------------------
elif st.session_state.route == "rules":
    st.subheader("📜 Rules Ledger & Safe Adjustment Engine")
    st.caption("Inspect untouched predefined baseline rules vs active circular amendments, or issue adjustments without touching the base rules.")

    tab_inspect, tab_adjust = st.tabs(["🔍 View Rules & Amendments", "⚖️ Safe Policy Adjuster"])

    with tab_inspect:
        rules_res = client.get_rules(as_of=as_of_timestamp)
        if rules_res.get("success"):
            rules_list = rules_res["data"]
            st.markdown(f"**Found {len(rules_list)} Baseline Rules in `predefined_rules` Table:**")

            col_list, col_detail = st.columns([1, 2])
            with col_list:
                selected_r_id = st.radio(
                    "Select Rule",
                    options=[r["doc_id"] for r in rules_list],
                    format_func=lambda x: f"{x} - {next((r['title'] for r in rules_list if r['doc_id'] == x), x)}"
                )

            with col_detail:
                rule_info = next((r for r in rules_list if r["doc_id"] == selected_r_id), None)
                if rule_info:
                    st.markdown(f"### {rule_info['doc_id']}: {rule_info['title']}")
                    st.caption(f"Category: `{rule_info['category']}` | Citation: `{rule_info['rule_citation']}`")

                    if rule_info.get("is_amended"):
                        st.warning(f"⚠️ **Rule Amended by {rule_info['active_circular_id']}** (Effective: {rule_info['circular_effective_date']})")
                        st.markdown(f"**Circular Title:** {rule_info['circular_title']}")
                        st.info(f"**Amendment Text:**\n{rule_info['amendment_content']}")
                        with st.expander("📄 View Untouched Predefined Base Rule Content"):
                            st.write(rule_info["base_content"])
                    else:
                        st.success("✅ **Original Predefined Rule in Effect (Unchanged)**")
                        st.write(rule_info["base_content"])
        else:
            st.error(f"Failed to fetch rules: {rules_res.get('error')}")

    with tab_adjust:
        st.markdown("### ✍️ Adjust a Policy via Circular (Leaves Predefined Rules Untouched)")
        st.caption("Amend a policy clause or update numerical settings. The original base rule is preserved in `predefined_rules`.")

        with st.form("adjust_rule_form"):
            adj_c_id = st.text_input("New Circular ID", value=f"CIR-2026-{datetime.now().strftime('%m%d')}")
            adj_base_id = st.selectbox(
                "Base Rule to Amend", 
                ["RUL-CAN-01", "RUL-BKG-01", "RUL-TAT-01", "RUL-LUG-01", "RUL-ID-01", "RUL-CON-01", "RUL-BRD-01", "RUL-DIS-01"]
            )
            adj_title = st.text_input("Amendment Title", value="Special Revision Notification")
            adj_eff_date = st.date_input("Effective Date", value=datetime.now())
            adj_content = st.text_area("Amendment Clause Content", value="Cancellation fee for this class is temporarily revised.")
            
            st.markdown("##### Optional Numeric Setting Update")
            num_key = st.selectbox("Setting Parameter to Update", ["None", "cancel_charge_2AC_over_48h", "cancel_charge_3AC_over_48h", "cancel_charge_SL_over_48h", "action_expiry_minutes"])
            num_val = st.number_input("New Value", value=180.0, step=10.0)

            submitted = st.form_submit_button("Publish Policy Amendment", type="primary")
            if submitted:
                settings_dict = {num_key: num_val} if num_key != "None" else None
                adj_res = client.adjust_rule(
                    circular_id=adj_c_id,
                    base_rule_id=adj_base_id,
                    title=adj_title,
                    amendment_content=adj_content,
                    effective_date=adj_eff_date.strftime("%Y-%m-%d"),
                    numeric_settings=settings_dict
                )
                if adj_res.get("success"):
                    st.success(f"Adjustment Published! Base rule `{adj_base_id}` remains 100% untouched.")
                    st.info(f"Circular `{adj_c_id}` is now active in the system and ready for chat testing.")
                else:
                    st.error(f"Adjustment failed: {adj_res.get('error')}")

# ----------------------------------------------------------------------
# ROUTE 4: 📥 Dynamic Knowledge Ingestion (POST /ingest)
# ----------------------------------------------------------------------
elif st.session_state.route == "ingest":
    st.subheader("📥 Live Knowledge Ingestion (`POST /ingest`)")
    st.caption("Judges will test adding a new circular or rule live. Content takes effect immediately without restart (R11).")

    ingest_type = st.selectbox("Document Type", ["circular", "rule", "faq"])

    with st.form("ingest_form"):
        if ingest_type == "circular":
            doc_id = st.text_input("Circular No (e.g. CIR-2026-08)", value="CIR-2026-08")
            title = st.text_input("Title", value="Revision of Special Train Tatkal Fees")
            eff_date = st.date_input("Effective Date", value=datetime.now())
            mod_rule = st.text_input("Modifies Earlier Rule (optional)", value="RUL-TAT-01")
            content = st.text_area("Content", value="Effective immediately, Tatkal charges for AC 3 Tier on Special Trains will be capped at Rs 350.")
            payload = {
                "doc_id": doc_id, "title": title, "effective_date": str(eff_date),
                "modifies_rule": mod_rule, "content": content, "issue_date": str(datetime.now().date())
            }
        elif ingest_type == "rule":
            doc_id = st.text_input("Rule ID (e.g. RUL-NEW-01)", value="RUL-NEW-01")
            title = st.text_input("Rule Title", value="Senior Citizen Special Amenities")
            category = st.text_input("Category", value="Concessions & Amenities")
            content = st.text_area("Content", value="Lower berth quota is strictly prioritized for senior citizens above 60 years.")
            payload = {"doc_id": doc_id, "title": title, "category": category, "content": content}
        else:
            faq_id = st.text_input("FAQ ID (e.g. FAQ-101)", value="FAQ-101")
            question = st.text_input("Question", value="Can I get food on 12124 Midnight Special?")
            answer = st.text_area("Answer", value="Yes, midnight snack service is available until 01:30 AM.")
            lang = st.selectbox("Language", ["en", "hi", "hi-en"])
            payload = {"faq_id": faq_id, "question": question, "answer": answer, "language": lang}

        submitted = st.form_submit_button("Submit to POST /ingest", type="primary")
        if submitted:
            with st.spinner("Ingesting into live knowledge database..."):
                i_res = client.ingest_document(ingest_type, payload)
            if i_res.get("success"):
                st.success(f"Document Ingested! {i_res['data'].get('message', '')}")
                st.info("You can now test this new rule immediately in the **Chat Tab**.")
            else:
                st.error(f"Ingestion failed: {i_res.get('error')}")

# ----------------------------------------------------------------------
# ROUTE 4: 🔍 Trace Observability (GET /trace/{trace_id})
# ----------------------------------------------------------------------
elif st.session_state.route == "trace":
    st.subheader("🔍 Trace & Observability Inspector (`GET /trace/{trace_id}`)")
    st.caption("Replay the full decision trail for any assistant response: documents cited, tools executed, and state changes.")

    trc_input = st.text_input("Trace ID", value=st.session_state.selected_trace_id)
    if st.button("Fetch Trace Record", type="primary"):
        st.session_state.selected_trace_id = trc_input

    if st.session_state.selected_trace_id:
        t_res = client.get_trace(st.session_state.selected_trace_id)
        if t_res.get("success"):
            trc_data = t_res["data"]
            st.success(f"Trace `{st.session_state.selected_trace_id}` loaded successfully.")

            m_col1, m_col2, m_col3 = st.columns(3)
            m_col1.metric("Answer Type", trc_data.get("answer_type", "N/A"))
            m_col2.metric("Passenger", trc_data.get("passenger_id", "N/A"))
            m_col3.metric("Timestamp", trc_data.get("timestamp", "N/A")[:19])

            st.markdown("### 🗣️ User Query")
            st.info(trc_data.get("user_query", ""))

            st.markdown("### 🤖 Assistant Reply")
            st.write(trc_data.get("answer_text") or trc_data.get("answer"))

            st.markdown("### 📚 Documents Cited")
            sources = trc_data.get("sources", [])
            if sources:
                st.json(sources)
            else:
                st.write("None cited.")

            st.markdown("### ⚙️ Deterministic Tools Executed")
            tools = trc_data.get("tools", [])
            if tools:
                st.json(tools)
            else:
                st.write("No external tools required.")

            if trc_data.get("pending_action"):
                st.markdown("### ⚠️ Proposed Action")
                st.json(trc_data["pending_action"])

            if trc_data.get("handed_to_human"):
                st.markdown("### 👥 Handed to Human Summary")
                st.json(trc_data["handed_to_human"])

        else:
            st.error(f"Trace not found: {t_res.get('error')}")
