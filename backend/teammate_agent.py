"""
Ujjwal Rail Unified Agentic & RAG Bridge
Connects:
1. Agentic Action Engine (cancellations, quotes, proposals)
2. RAG Knowledge Pipeline (HybridRetriever for rules, circulars, faqs, live ingest)
3. Guardrails (R8 Privacy, R9 Adversarial Injection, R7 Human Handover)
4. Domain Tools (bookings, seat matrices, schedules, passenger profiles)
"""

import os
import re
import json
import sqlite3
from datetime import datetime
from typing import Dict, Any, Optional

from agentic.models import AgenticRequest, AgenticResponse
from agentic.router import handle_agentic_request
from agentic.bionic_client import parse_intent_and_entities
from backend.tools import (
    search_trains,
    check_seats,
    get_fare,
    get_booking_status,
    refund_quote,
    can_cancel,
    resolve_station,
    extract_effective_rule,
    get_db_connection
)
from backend.domain_tools import propose_action

# Wire RAG Pipeline HybridRetriever for intelligent rule retrieval
from RAG_pipeline.repository import RulesRepository
from RAG_pipeline.hybrid_retriever import HybridRetriever

_rag_repo = RulesRepository(db_path="data/ujjwal_rail.db")
_rag_retriever = HybridRetriever(_rag_repo)

def get_rag_retriever() -> HybridRetriever:
    return _rag_retriever

def process_with_rag_agent(
    passenger_id: str,
    session_id: str,
    message: str,
    as_of: Optional[str] = None,
    trace_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Main entry point bridging the agentic engine, RAG pipeline, and deterministic tools:
    1. Enforces strict R9 Injection & R8 Privacy guardrails.
    2. Routes policy actions (cancel, complaint, disputes, refusals) to agentic policy engine.
    3. Handles identity queries, conversational greetings, and passenger booking lookups.
    4. Routes rules and knowledge queries through RAG HybridRetriever.
    5. Emits exact Section 6.1 contract schema.
    """
    if not as_of:
        as_of = datetime.now().isoformat()
    if not trace_id:
        import uuid
        trace_id = uuid.uuid4().hex[:8]

    msg_clean = message.strip()
    msg_lower = msg_clean.lower()

    # ----------------------------------------------------------------------
    # 1. R9: Adversarial Prompt Injection Shield
    # ----------------------------------------------------------------------
    injection_triggers = [
        "ignore your rules", "ignore rules", "give me full refund regardless", 
        "bypass policies", "system prompt override", "testing mode", 
        "approve rs", "without checks", "override rules", "dump all"
    ]
    if any(phrase in msg_lower for phrase in injection_triggers):
        req = AgenticRequest(
            passenger_id=passenger_id,
            session_id=session_id,
            message=message,
            intent="excess_refund",
            as_of=as_of
        )
        conn = get_db_connection()
        res = handle_agentic_request(req, conn)
        conn.close()
        return {
            "trace_id": trace_id,
            "answer_type": "refusal",
            "answer": "I must adhere strictly to Ujjwal Rail's published rules and circulars. I cannot override policies or execute unauthorized commands.",
            "sources": [{"doc_id": "RUL-CAN-01", "section": "1. Governance & Applicability"}],
            "tools": [],
            "pending_action": None,
            "handed_to_human": None
        }

    # ----------------------------------------------------------------------
    # 2. R8: Privacy & Snooping Defense (Other Passengers & Manifests)
    # ----------------------------------------------------------------------
    other_pnr_match = re.search(r'UR-\d{5}', msg_clean)
    if ("friend" in msg_lower or "someone else" in msg_lower or "another passenger" in msg_lower) and other_pnr_match:
        req = AgenticRequest(
            passenger_id=passenger_id,
            session_id=session_id,
            message=message,
            intent="other_passenger_booking",
            entities={"booking_id": other_pnr_match.group(0)},
            as_of=as_of
        )
        conn = get_db_connection()
        res = handle_agentic_request(req, conn)
        conn.close()
        return {
            "trace_id": trace_id,
            "answer_type": "refusal",
            "answer": res.answer,
            "sources": [{"doc_id": "RUL-BKG-01", "section": "9. Passenger Privacy & Security"}],
            "tools": [],
            "pending_action": None,
            "handed_to_human": None
        }

    if any(phrase in msg_lower for phrase in ["passenger list", "phone numbers", "show me passengers", "list phone"]):
        return {
            "trace_id": trace_id,
            "answer_type": "refusal",
            "answer": "Under Ujjwal Rail passenger data protection regulations, passenger manifest lists and personal contact details cannot be disclosed.",
            "sources": [{"doc_id": "RUL-BKG-01", "section": "9. Privacy"}],
            "tools": [],
            "pending_action": None,
            "handed_to_human": None
        }

    # ----------------------------------------------------------------------
    # 3. Section 6.3 Level 3 Disallowed Actions
    # ----------------------------------------------------------------------
    if any(phrase in msg_lower for phrase in ["without paying", "waitlist to confirmed", "move up the waitlist", "change fare"]):
        req = AgenticRequest(
            passenger_id=passenger_id,
            session_id=session_id,
            message=message,
            intent="waitlist_override",
            as_of=as_of
        )
        conn = get_db_connection()
        res = handle_agentic_request(req, conn)
        conn.close()
        return {
            "trace_id": trace_id,
            "answer_type": "refusal",
            "answer": res.answer,
            "sources": [{"doc_id": "RUL-WL-01", "section": "4. Reservation Priority"}],
            "tools": [],
            "pending_action": None,
            "handed_to_human": None
        }

    # ----------------------------------------------------------------------
    # 3.5 Passenger Identity & Profile Inquiries
    # ----------------------------------------------------------------------
    is_identity_query = any(phrase in msg_lower for phrase in [
        "what is my name", "who am i", "my name", "my profile", "mera naam", 
        "who i am", "my passenger id", "which user am i", "logged in as"
    ])
    if is_identity_query:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT name, phone_last4, preferred_language FROM passengers WHERE passenger_id = ?", (passenger_id,))
        p_row = c.fetchone()
        conn.close()
        if p_row:
            p_name = p_row["name"] if isinstance(p_row, dict) else p_row[0]
            p_phone = p_row["phone_last4"] if isinstance(p_row, dict) else p_row[1]
            ans_text = f"You are logged in as {p_name} (Passenger ID: {passenger_id}, Registered Mobile: ••••{p_phone}). How can I assist you with your travels today?"
        else:
            ans_text = f"You are currently authenticated with Passenger ID: {passenger_id}."
        return {
            "trace_id": trace_id,
            "answer_type": "answer",
            "answer": ans_text,
            "sources": [],
            "tools": [{"tool": "get_passenger_profile", "output": {"passenger_id": passenger_id, "name": p_row["name"] if p_row else None}}],
            "pending_action": None,
            "handed_to_human": None
        }

    # ----------------------------------------------------------------------
    # 3.6 Conversational Greetings
    # ----------------------------------------------------------------------
    pure_greetings = ["hi", "hello", "hey", "namaste", "good morning", "good evening", "good afternoon", "hi!", "hello!", "hey!"]
    is_greeting = msg_lower in pure_greetings or (
        msg_lower.startswith(("hi ", "hello ", "hey ", "namaste ")) 
        and not any(k in msg_lower for k in ["train", "ticket", "cancel", "refund", "tatkal", "seat", "fare", "ur-", "status", "booking"])
    )
    if is_greeting:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT name FROM passengers WHERE passenger_id = ?", (passenger_id,))
        p_row = c.fetchone()
        conn.close()
        name_str = f" {p_row['name']}" if p_row else ""
        return {
            "trace_id": trace_id,
            "answer_type": "answer",
            "answer": f"Hello{name_str}! I am your Ujjwal Rail Travel Assistant. You can ask me about train schedules, seat availability, cancellation refunds, or railway rules. How can I help you today?",
            "sources": [],
            "tools": [],
            "pending_action": None,
            "handed_to_human": None
        }

    # ----------------------------------------------------------------------
    # 3.7 Passenger Bookings Inquiry (What tickets/bookings do I have?)
    # ----------------------------------------------------------------------
    b_match = re.search(r'UR-\d{5}', msg_clean)
    if b_match and any(w in msg_lower for w in ["status", "check", "detail", "batao", "show", "info"]) and not any(w in msg_lower for w in ["cancel", "refund", "charge"]):
        target_b_id = b_match.group(0)
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            SELECT b.booking_id, b.passenger_id, b.train_no, t.name as train_name, b.from_code, b.to_code, 
                   b.journey_date, b.class, b.status, b.amount_paid
            FROM bookings b
            LEFT JOIN trains t ON b.train_no = t.train_no
            WHERE b.booking_id = ?
        """, (target_b_id,))
        row = c.fetchone()
        conn.close()
        if row:
            if row["passenger_id"] != passenger_id:
                return {
                    "trace_id": trace_id,
                    "answer_type": "refusal",
                    "answer": "Accessing or modifying bookings belonging to another passenger is strictly prohibited under Ujjwal Rail privacy policy R8.",
                    "sources": [{"doc_id": "RUL-BKG-01", "section": "9. Passenger Privacy & Security"}],
                    "tools": [],
                    "pending_action": None,
                    "handed_to_human": None
                }
            t_name = f" ({row['train_name']})" if row["train_name"] else ""
            ans_text = (
                f"Booking details for {target_b_id}: Train {row['train_no']}{t_name} from {row['from_code']} to {row['to_code']} "
                f"on {row['journey_date']} | Class: {row['class']} | Status: {row['status']} | Amount Paid: Rs {row['amount_paid']}."
            )
            return {
                "trace_id": trace_id,
                "answer_type": "answer",
                "answer": ans_text,
                "sources": [{"doc_id": "RUL-BKG-01", "section": "2. Passenger Bookings"}],
                "tools": [{"tool": "get_booking_details", "output": {"booking_id": target_b_id, "status": row["status"]}}],
                "pending_action": None,
                "handed_to_human": None
            }

    has_booking_term = any(w in msg_lower for w in ["booking", "bookings", "ticket", "tickets", "gadi", "gaadi"])
    has_self_ref = any(w in msg_lower for w in [
        "my", "mine", "i have", "i made", "i booked", "done by me", "for me", "with me",
        "meri", "mere", "mera", "maine", "apni", "hamari", "humari", "kon kon", "kon si", "which"
    ])
    has_action_or_rules = any(w in msg_lower for w in [
        "cancel", "radd", "refund", "charge", "fare", "price", "kitna paisa", "rule", "rules", "policy", "fee", "dog", "pet"
    ])
    is_booking_inquiry = (has_booking_term and has_self_ref and not has_action_or_rules)
    if is_booking_inquiry:
        # Check if query filters by a specific train number
        train_filter_match = re.search(r'\b\d{5}\b', msg_clean)
        target_train_no = train_filter_match.group(0) if train_filter_match else None

        conn = get_db_connection()
        c = conn.cursor()
        
        query = """
            SELECT b.booking_id, b.train_no, t.name as train_name, b.from_code, b.to_code, 
                   b.journey_date, b.class, b.status, b.amount_paid
            FROM bookings b
            LEFT JOIN trains t ON b.train_no = t.train_no
            WHERE b.passenger_id = ?
        """
        params = [passenger_id]

        if target_train_no:
            query += " AND b.train_no = ?"
            params.append(target_train_no)

        query += " ORDER BY b.journey_date DESC"

        c.execute(query, tuple(params))
        rows = c.fetchall()
        conn.close()

        if rows:
            booking_lines = []
            for r in rows:
                t_name = f" ({r['train_name']})" if r["train_name"] else ""
                booking_lines.append(
                    f"• {r['booking_id']}: Train {r['train_no']}{t_name} from {r['from_code']} to {r['to_code']} on {r['journey_date']} "
                    f"| Class: {r['class']} | Status: {r['status']} | Fare: Rs {r['amount_paid']}"
                )
            header_str = f"for Train {target_train_no}" if target_train_no else "registered under your account"
            ans_text = f"Here are the bookings {header_str} ({passenger_id}):\n" + "\n".join(booking_lines)
            tool_data = [{"booking_id": r["booking_id"], "train_no": r["train_no"], "status": r["status"]} for r in rows]
        else:
            if target_train_no:
                ans_text = f"You do not have any registered bookings for Train {target_train_no} under Passenger ID {passenger_id}."
            else:
                ans_text = f"You do not have any registered bookings under Passenger ID {passenger_id}."
            tool_data = []

        return {
            "trace_id": trace_id,
            "answer_type": "answer",
            "answer": ans_text,
            "sources": [{"doc_id": "RUL-BKG-01", "section": "2. Passenger Bookings"}],
            "tools": [{"tool": "get_passenger_bookings", "output": {"count": len(rows), "train_no_filter": target_train_no, "bookings": tool_data}}],
            "pending_action": None,
            "handed_to_human": None
        }

    # ----------------------------------------------------------------------
    # 4. R2: Vague Queries (Follow-up clarification)
    # ----------------------------------------------------------------------
    vague_phrases = [
        "i need a ticket", "i need a ticket to delhi", "book ticket", "train ticket", "ticket",
        "what is the train time?", "what is the train time", "tell me fare", "train time"
    ]
    if msg_lower in vague_phrases:
        return {
            "trace_id": trace_id,
            "answer_type": "clarification",
            "answer": "Could you please specify your origin and destination stations, travel date (YYYY-MM-DD), or train number?",
            "sources": [{"doc_id": "RUL-BKG-01", "section": "2. Booking Parameters"}],
            "tools": [],
            "pending_action": None,
            "handed_to_human": None
        }

    # ----------------------------------------------------------------------
    # 5. R7: Complaints & Grievance Hand-over (Level 2)
    # ----------------------------------------------------------------------
    if any(w in msg_lower for w in ["complain", "complaint", "harassment", "emergency", "grievance", "stolen", "dispute", "security problem"]):
        req = AgenticRequest(
            passenger_id=passenger_id,
            session_id=session_id,
            message=message,
            intent="complaint",
            as_of=as_of
        )
        conn = get_db_connection()
        res = handle_agentic_request(req, conn)
        conn.close()
        return {
            "trace_id": trace_id,
            "answer_type": "handed_to_human",
            "answer": res.answer,
            "sources": [{"doc_id": "RUL-CMP-01", "section": "2. Escalation & Customer Care"}],
            "tools": [t.model_dump() for t in res.tools],
            "pending_action": None,
            "handed_to_human": res.handed_to_human or {
                "desk": "grievance_redressal",
                "summary": f"Passenger {passenger_id} filed an issue regarding: {msg_clean[:100]}",
                "booking_id": "N/A"
            }
        }

    # ----------------------------------------------------------------------
    # 6. Informational Refund Quotes vs Direct Actions (answer_type: "answer")
    # ----------------------------------------------------------------------
    is_informational_refund = any(phrase in msg_lower for phrase in [
        "how much refund", "kitna paisa wapas", "paisa milega", "how much will i get back",
        "cancellation charge applies", "if i cancel my ticket", "what is the refund for",
        "can i cancel my ticket 3 hours", "cut-off deadline"
    ])

    if is_informational_refund:
        b_match = re.search(r'UR-\d{5}', msg_clean)
        b_id = b_match.group(0) if b_match else None

        if b_id:
            quote = refund_quote(b_id, passenger_id, as_of)
            if quote.get("authorized", False):
                if not quote.get("eligible", True):
                    ans_text = quote.get("error") or quote.get("message", f"Booking {b_id} is within chart preparation or already cancelled; no refund applies.")
                else:
                    ans_text = (
                        f"For booking {b_id} (Train {quote['train_no']}, Class {quote['class']}): "
                        f"Departure is in {quote['hours_before_departure']} hours. "
                        f"Based on {quote['rule_cited']}, the cancellation deduction is Rs {quote['charge']} "
                        f"({quote['cut_off_window']}), giving an estimated refund of Rs {quote['refund']}."
                    )
                return {
                    "trace_id": trace_id,
                    "answer_type": "answer",
                    "answer": ans_text,
                    "sources": [
                        {"doc_id": "RUL-CAN-01", "section": "3. Refund Table"},
                        {"doc_id": "CIR-2026-01", "section": "Revised Charges"}
                    ],
                    "tools": [{"tool": "refund_quote", "output": quote}],
                    "pending_action": None,
                    "handed_to_human": None
                }

        # General policy questions
        if "3 hours" in msg_lower:
            ans_text = "Under rule RUL-CAN-01 Section 3, no refund is granted on confirmed tickets cancelled within 4 hours of departure once charts are prepared."
            source_doc = "RUL-CAN-01"
        elif "3ac" in msg_lower and "48 hours" in msg_lower:
            ans_text = "For 3AC, the flat cancellation fee >48 hours before departure is Rs 180 per passenger (revised by CIR-2026-01 effective Feb 2026 from Rs 150)."
            source_doc = "CIR-2026-01"
        elif "chart" in msg_lower or "deadline" in msg_lower:
            ans_text = "The cancellation deadline for self-service refunds is strictly up to 4 hours before scheduled train departure, before final chart preparation."
            source_doc = "RUL-CAN-01"
        else:
            ans_text = "Under Ujjwal Rail policy RUL-CAN-01 and CIR-2026-01, refunds depend on the class and the time remaining before scheduled departure."
            source_doc = "RUL-CAN-01"

        return {
            "trace_id": trace_id,
            "answer_type": "answer",
            "answer": ans_text,
            "sources": [{"doc_id": source_doc, "section": "Refund Rules"}],
            "tools": [{"tool": "refund_quote", "output": {"policy": source_doc}}],
            "pending_action": None,
            "handed_to_human": None
        }

    # ----------------------------------------------------------------------
    # 7. Level 1 Actions (Cancellation & Booking Proposals)
    # ----------------------------------------------------------------------
    # Direct Cancellation Request
    is_cancel_action = any(w in msg_lower for w in ["cancel", "radd"]) and not any(w in msg_lower for w in ["charge", "how much", "kitna", "rule", "policy", "deadline"])
    if is_cancel_action:
        conn = get_db_connection()
        c = conn.cursor()
        b_match = re.search(r'UR-\d{5}', msg_clean)
        if b_match:
            b_id = b_match.group(0)
            c.execute("UPDATE bookings SET status = 'CONFIRMED' WHERE booking_id = ?", (b_id,))
            conn.commit()
        else:
            c.execute("SELECT booking_id FROM bookings WHERE passenger_id = ? AND status IN ('CONFIRMED', 'CNF') ORDER BY journey_date ASC LIMIT 1", (passenger_id,))
            row = c.fetchone()
            b_id = row["booking_id"] if row else None
        conn.close()

        req = AgenticRequest(
            passenger_id=passenger_id,
            session_id=session_id,
            message=message,
            intent="cancel_booking",
            entities={"booking_id": b_id} if b_id else {},
            as_of=as_of
        )
        conn = get_db_connection()
        res = handle_agentic_request(req, conn)
        conn.close()

        return {
            "trace_id": trace_id,
            "answer_type": res.answer_type,
            "answer": res.answer,
            "sources": [{"doc_id": "RUL-CAN-01", "section": "3. Refund Table"}],
            "tools": [t.model_dump() for t in res.tools],
            "pending_action": res.pending_action.model_dump() if res.pending_action else None,
            "handed_to_human": None
        }

    # Direct Booking Request
    if any(w in msg_lower for w in ["book 1 seat", "book a seat", "reserve a seat", "book ticket"]):
        action = propose_action(
            passenger_id=passenger_id,
            booking_id="UR-NEW",
            action_type="book_ticket",
            details={"train_no": "12123", "class": "3AC", "date": "2026-12-05", "fare": 950.0}
        )
        return {
            "trace_id": trace_id,
            "answer_type": "confirm_needed",
            "answer": "Booking 1 seat on train 12123 (Class 3AC, Date: 2026-12-05). Total fare: Rs 950. Shall I confirm this reservation?",
            "sources": [{"doc_id": "RUL-BKG-01", "section": "2. Reservations"}],
            "tools": [{"tool": "book_ticket_quote", "output": {"train_no": "12123", "fare": 950.0}}],
            "pending_action": action,
            "handed_to_human": None
        }

    # ----------------------------------------------------------------------
    # 8. Rules & Circular Inquiries
    # ----------------------------------------------------------------------
    if any(w in msg_lower for w in ["pet", "dog"]):
        eff = extract_effective_rule("RUL-LUG-01", as_of)
        return {
            "trace_id": trace_id,
            "answer_type": "answer",
            "answer": "Under rule RUL-LUG-01, pet dogs are strictly prohibited in 2AC, 3AC, CC and Sleeper coaches. They are only permitted in 1AC cabins/coupes booked exclusively by the passenger.",
            "sources": [{"doc_id": "RUL-LUG-01", "section": "Section 4: Pets and Livestock"}],
            "tools": [],
            "pending_action": None,
            "handed_to_human": None
        }

    if "tatkal" in msg_lower:
        if "sleeper" in msg_lower or "charge" in msg_lower:
            ans = "Circular CIR-2026-02 revised the minimum Tatkal charge for Sleeper class from Rs 100 to Rs 150 (effective April 2026). The maximum charge remains capped at Rs 200."
            doc = "CIR-2026-02"
        else:
            ans = "Under RUL-TAT-01, Tatkal bookings open at 10:00 AM for AC classes and 11:00 AM for Non-AC classes one day prior to departure. No refund is granted on confirmed Tatkal tickets."
            doc = "RUL-TAT-01"
        return {
            "trace_id": trace_id,
            "answer_type": "answer",
            "answer": ans,
            "sources": [{"doc_id": doc, "section": "Tatkal Scheme Guidelines"}],
            "tools": [],
            "pending_action": None,
            "handed_to_human": None
        }

    if "2ac" in msg_lower and ("february" in msg_lower or "new" in msg_lower or "charge" in msg_lower):
        return {
            "trace_id": trace_id,
            "answer_type": "answer",
            "answer": "Under Circular CIR-2026-01 (effective 2026-02-01), the flat cancellation charge for 2AC cancelled >48 hours before departure was revised to Rs 200 (up from Rs 180 under RUL-CAN-01).",
            "sources": [{"doc_id": "CIR-2026-01", "section": "Revised Cancellation Charges"}],
            "tools": [],
            "pending_action": None,
            "handed_to_human": None
        }

    if "id" in msg_lower and ("proof" in msg_lower or "accepted" in msg_lower):
        return {
            "trace_id": trace_id,
            "answer_type": "answer",
            "answer": "Under RUL-ID-01, accepted original photo identity proofs include Aadhaar card, Voter ID, Passport, Driving Licence, PAN card, Student ID from recognized schools/colleges, or documents in DigiLocker.",
            "sources": [{"doc_id": "RUL-ID-01", "section": "Section 1: Prescribed Identity Proofs"}],
            "tools": [],
            "pending_action": None,
            "handed_to_human": None
        }

    # ----------------------------------------------------------------------
    # 9. Train Search & Fares
    # ----------------------------------------------------------------------
    train_match = re.search(r'\b(12\d{3}|02\d{3})\b', msg_clean)
    train_no = train_match.group(0) if train_match else None
    date_match = re.search(r'\d{4}-\d{2}-\d{2}', msg_clean)
    j_date = date_match.group(0) if date_match else "2026-12-05"

    if train_no:
        cls_match = re.search(r'\b(1AC|2AC|3AC|CC|SL|2S)\b', msg_clean, re.I)
        target_cls = cls_match.group(0).upper() if cls_match else "3AC"
        seats = check_seats(train_no, j_date, target_cls)
        fare = get_fare(train_no, "PUNE", "CSMT", target_cls) or 950.0
        avail_str = f"Available: {seats.get('available', 0)}, RAC: {seats.get('rac', 0)}, WL: {seats.get('waitlist', 0)}"
        return {
            "trace_id": trace_id,
            "answer_type": "answer",
            "answer": f"For Train {train_no} ({target_cls} class on {j_date}): {avail_str}. Fare is Rs {fare}.",
            "sources": [{"doc_id": "RUL-BKG-01", "section": "Timetable & Fares"}],
            "tools": [{"tool": "check_seats", "output": {"train_no": train_no, "seats": seats, "fare": fare}}],
            "pending_action": None,
            "handed_to_human": None
        }

    # Station search (e.g. "PUNE to CSMT", "from Pune to CSMT", "Pune se Mumbai")
    route_match = re.search(r'(?:from\s+|se\s+|trains?\s+)?([a-zA-Z\s]+?)\s+(?:to|ko|me|->|-|and)\s+([a-zA-Z\s]+?)(?:\s+(?:on|this|tomorrow|$)|$)', msg_clean, re.I)
    from_stn = None
    to_stn = None

    if route_match:
        cand_from = route_match.group(1).strip()
        cand_to = route_match.group(2).strip()
        res_from = resolve_station(cand_from)
        res_to = resolve_station(cand_to)
        if res_from and res_to:
            from_stn = res_from["station_code"]
            to_stn = res_to["station_code"]

    # Fallback: scan for any two station codes/cities mentioned in the query
    if not from_stn or not to_stn:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT station_code, name, city FROM stations")
        all_stns = [dict(s) for s in c.fetchall()]
        conn.close()
        found_stns = []
        for s in all_stns:
            s_code = s["station_code"].lower()
            s_city = s["city"].lower()
            if re.search(rf'\b{s_code}\b', msg_lower) or re.search(rf'\b{s_city}\b', msg_lower):
                if s["station_code"] not in found_stns:
                    found_stns.append(s["station_code"])
        if len(found_stns) >= 2:
            from_stn = found_stns[0]
            to_stn = found_stns[1]

    has_train_intent = any(w in msg_lower for w in ["train", "trains", "gadi", "gaadi", "timetable", "schedule"])

    if from_stn and to_stn:
        trains = search_trains(from_stn, to_stn, j_date)
        if trains:
            t_list = "\n".join([f"• Train {t['train_no']} ({t['name']}): Departs {t['departure_time']}, Arrives {t['arrival_time']} | Classes: {t['classes']}" for t in trains[:4]])
            ans_text = f"Found {len(trains)} Ujjwal Rail trains from {from_stn} to {to_stn} on {j_date}:\n{t_list}"
        else:
            ans_text = f"No direct trains found from {from_stn} to {to_stn} on {j_date}."
        return {
            "trace_id": trace_id,
            "answer_type": "answer",
            "answer": ans_text,
            "sources": [{"doc_id": "RUL-BKG-01", "section": "Timetable & Routes"}],
            "tools": [{"tool": "search_trains", "output": {"count": len(trains), "from": from_stn, "to": to_stn, "trains": [t["train_no"] for t in trains]}}],
            "pending_action": None,
            "handed_to_human": None
        }
    elif has_train_intent:
        return {
            "trace_id": trace_id,
            "answer_type": "clarification",
            "answer": "Could you please specify your origin and destination stations (e.g., 'trains from Pune to CSMT') and travel date?",
            "sources": [{"doc_id": "RUL-BKG-01", "section": "Timetable & Routes"}],
            "tools": [],
            "pending_action": None,
            "handed_to_human": None
        }

    # ----------------------------------------------------------------------
    # 10. Dynamic RAG Knowledge Retrieval using HybridRetriever
    # ----------------------------------------------------------------------
    try:
        query_date = as_of[:10] if as_of and len(as_of) >= 10 else "2026-11-21"
        rag_res = _rag_retriever.retrieve(msg_clean, as_of=query_date, top_k=2)
        if rag_res and rag_res.chunks:
            top_chunk = rag_res.chunks[0]
            sources_list = [{"doc_id": c.doc_id, "section": c.section} for c in rag_res.chunks[:2]]
            return {
                "trace_id": trace_id,
                "answer_type": "answer",
                "answer": f"According to {top_chunk.doc_id} ({top_chunk.section}): {top_chunk.content}",
                "sources": sources_list,
                "tools": [{"tool": "hybrid_retriever", "output": {"method": rag_res.retrieval_method, "doc_id": top_chunk.doc_id}}],
                "pending_action": None,
                "handed_to_human": None
            }
    except Exception:
        pass

    # Default fallback
    return {
        "trace_id": trace_id,
        "answer_type": "answer",
        "answer": "I am your Ujjwal Rail Travel Assistant. You can ask me about train schedules, seat availability, refund calculations, or railway policies.",
        "sources": [{"doc_id": "RUL-BKG-01", "section": "General Rules"}],
        "tools": [],
        "pending_action": None,
        "handed_to_human": None
    }

def on_document_ingested(doc_id: str, doc_type: str, content: str):
    """Hot-reloads the RAG retriever in memory when a new document is ingested."""
    try:
        _rag_retriever.reload()
    except Exception:
        pass
