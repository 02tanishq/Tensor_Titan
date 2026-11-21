"""
Grok (xAI) LLM Integration Module for Ujjwal Rail Assistant.
Provides grounded natural language reasoning and response synthesis.
Adheres strictly to the groundedness requirement: deterministic tool outputs
and retrieved policy chunks are passed as authoritative context to Grok.
"""

import os
import json
import logging
import requests
from typing import Optional, List, Dict, Any
from app.config import config

logger = logging.getLogger("app.llm_client")


def is_grok_available() -> bool:
    """Check if live Grok API is enabled and configured with a valid key."""
    if os.getenv("MOCK_LLM", "false").lower() == "true":
        return False
    key = os.getenv("GROK_API_KEY", "").strip()
    return bool(key and key != "your_grok_api_key_here")


def call_grok(
    messages: List[Dict[str, str]],
    temperature: float = 0.2,
    max_tokens: int = 600,
    timeout: float = 10.0
) -> Optional[str]:
    """
    Executes a chat completion call to xAI's Grok API.
    Returns None on failure to ensure seamless fallback to deterministic templates.
    """
    if not is_grok_available():
        return None

    api_key = os.getenv("GROK_API_KEY", "").strip()
    base_url = os.getenv("GROK_BASE_URL", "https://api.x.ai/v1").rstrip("/")
    model = os.getenv("GROK_MODEL", "grok-2-latest")
    url = f"{base_url}/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return content.strip()
        else:
            logger.warning("Grok API call failed with status %d: %s", resp.status_code, resp.text)
            return None
    except Exception as e:
        logger.warning("Grok API exception: %s. Using deterministic fallback.", e)
        return None


def generate_rules_answer(
    query: str,
    retrieved_chunks: List[Any],
    citations: List[Any],
    lang: str = "en"
) -> Optional[str]:
    """
    Synthesizes a grounded answer to policy/rules questions based strictly on retrieved chunks.
    """
    if not retrieved_chunks:
        return None

    context_lines = []
    for c in retrieved_chunks:
        doc_id = getattr(c, "doc_id", "DOC")
        section = getattr(c, "section", "")
        content = getattr(c, "content", "")
        context_lines.append(f"[{doc_id} - {section}]: {content}")

    context_block = "\n\n".join(context_lines)
    citation_names = ", ".join([f"{getattr(c, 'doc_id', '')} ({getattr(c, 'section', '')})" for c in citations])

    lang_instruction = "Respond in English."
    if lang in ("hi", "hi-en"):
        lang_instruction = "Respond in Hindi / Hinglish as natural for an Indian passenger assistant."

    system_prompt = (
        "You are Ujjwal Rail's official AI Train Travel Assistant.\n"
        "Your task is to answer the passenger's question accurately and helpfully.\n"
        f"Language requirement: {lang_instruction}\n\n"
        "STRICT GROUNDEDNESS RULES:\n"
        "1. Base your answer strictly on the provided official policy excerpts below.\n"
        "2. Do not invent fees, deadlines, or rules not present in the excerpts.\n"
        f"3. Explicitly mention the governing documents ({citation_names}).\n"
        "4. Be concise, polite, and direct (2-3 sentences max)."
    )

    user_prompt = f"Official Railway Documents:\n{context_block}\n\nPassenger Question: {query}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    return call_grok(messages, temperature=0.1, max_tokens=350)


def synthesize_tool_answer(
    query: str,
    tool_name: str,
    tool_output: Dict[str, Any],
    lang: str = "en"
) -> Optional[str]:
    """
    Converts deterministic tool calculation results into a friendly conversational response.
    Never recalculates numbers; strictly presents the tool's output.
    """
    lang_instruction = "Respond in English."
    if lang in ("hi", "hi-en"):
        lang_instruction = "Respond in conversational Hindi or Hinglish."

    system_prompt = (
        "You are Ujjwal Rail's official AI Travel Assistant.\n"
        "A verified deterministic railway database tool has computed the following exact details.\n"
        f"Language requirement: {lang_instruction}\n"
        "CRITICAL ARITHMETIC RULE:\n"
        "You MUST keep all numbers, fares, seat counts, dates, and train numbers EXACTLY as provided.\n"
        "Do NOT perform any calculations or modify numbers."
    )

    user_prompt = (
        f"Passenger Query: {query}\n"
        f"Tool Used: {tool_name}\n"
        f"Verified Tool Output: {json.dumps(tool_output, default=str)}\n\n"
        "Please provide a concise, friendly response presenting these exact details."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    return call_grok(messages, temperature=0.1, max_tokens=250)


def generate_conversational_response(
    query: str,
    passenger_name: str,
    passenger_id: str,
    lang: str = "en"
) -> Optional[str]:
    """
    Generates personalized greetings and identity responses using Grok.
    """
    lang_instruction = "Respond in English."
    if lang in ("hi", "hi-en"):
        lang_instruction = "Respond in Hindi or Hinglish."

    system_prompt = (
        "You are Ujjwal Rail's official AI Travel Assistant.\n"
        f"The user is authenticated as {passenger_name} (Passenger ID: {passenger_id}).\n"
        f"Language: {lang_instruction}\n"
        "Be warm, professional, and state how you can help (train timetable, live seat availability, cancellation refunds, railway guidelines)."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query}
    ]

    return call_grok(messages, temperature=0.3, max_tokens=150)


def generate_clarification_response(
    query: str,
    needed_slot: str,
    lang: str = "en"
) -> Optional[str]:
    """
    Generates polite follow-up questions when required booking or travel parameters are missing.
    """
    lang_instruction = "Ask in English."
    if lang in ("hi", "hi-en"):
        lang_instruction = "Ask in polite Hindi/Hinglish."

    system_prompt = (
        "You are Ujjwal Rail's official AI Travel Assistant.\n"
        f"The passenger's query is missing the {needed_slot}.\n"
        f"{lang_instruction}\n"
        "Ask a polite, single-sentence follow-up question requesting the missing information with a helpful example."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query}
    ]

    return call_grok(messages, temperature=0.2, max_tokens=120)
