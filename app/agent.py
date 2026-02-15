import os
import re
from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient

from app.prompts.system_prompt import system_message
from app.services.memory import memory
from app.services.intent import detect_intent
from app.services.controller import handle_intent_action

# -----------------------------
# Payment / state controls
# -----------------------------
ACTIVE_PAYMENTS: set[str] = set()           # sessions currently in checkout mode
ACTIVE_PAYMENT_URLS: dict[str, str] = {}    # session_id -> payment_url
SESSION_STATE: dict[str, str] = {}          # session_id -> "COLLECTING" | "AWAITING_CONFIRMATION" | "AWAITING_PAYMENT"


# -----------------------------
# Extraction helpers
# -----------------------------
def extract_email_from_text(text: str) -> str | None:
    """Extract email address from text using regex."""
    email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    match = re.search(email_pattern, text or "")
    return match.group(0) if match else None


def extract_phone_from_text(text: str) -> str | None:
    """Extract phone number from text using regex."""
    # Nigerian phone patterns: +234, 234, 0 followed by 10 digits
    phone_patterns = [
        r"\+?234[789]\d{9}",  # +234 or 234 followed by 10 digits
        r"0[789]\d{9}",       # 0 followed by 10 digits
        r"\b\d{11}\b",        # 11 digits
    ]

    for pattern in phone_patterns:
        match = re.search(pattern, text or "")
        if match:
            return match.group(0)

    return None


def extract_customer_info_from_conversation(session_id: str) -> dict:
    """
    Extract customer information (name, email, phone, address) from conversation history.
    Returns dict with keys: name, email, phone, address (values can be None)
    """
    messages = memory.get_messages(session_id)
    info = {"name": None, "email": None, "phone": None, "address": None}

    for msg in messages:
        content = msg.get("content", "") or ""

        # Email
        if not info["email"]:
            email = extract_email_from_text(content)
            if email:
                info["email"] = email

        # Phone
        if not info["phone"]:
            phone = extract_phone_from_text(content)
            if phone:
                info["phone"] = phone

        # Name (basic patterns)
        if not info["name"]:
            name_patterns = [
                r"(?:my name is|i\'?m|i am|call me|name:)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
                r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)$",  # standalone name
            ]
            for pattern in name_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    potential_name = (match.group(1) or "").strip()
                    if 2 <= len(potential_name) <= 50 and not re.search(r"\d", potential_name):
                        info["name"] = potential_name
                        break

        # Address (keyword-based extraction)
        if not info["address"]:
            address_keywords = ["address", "deliver", "delivery", "location", "live at", "reside"]
            if any(k in content.lower() for k in address_keywords):
                address_patterns = [
                    r"(?:address|deliver to|delivery|location|live at|reside)[:\s]+(.{10,200})",
                ]
                for pattern in address_patterns:
                    match = re.search(pattern, content, re.IGNORECASE)
                    if match:
                        potential_address = (match.group(1) or "").strip()
                        potential_address = re.sub(r"[.,;!?]+$", "", potential_address)
                        if 10 <= len(potential_address) <= 200:
                            info["address"] = potential_address
                            break

    return info


def has_all_customer_info(session_id: str) -> bool:
    """Check if all required customer information is collected."""
    info = extract_customer_info_from_conversation(session_id)
    return all([info["name"], info["email"], info["phone"], info["address"]])


# -----------------------------
# Agent construction
# -----------------------------
def create_sales_agent():
    """Create the AutoGen assistant agent with explicit model client."""
    model_client = OpenAIChatCompletionClient(
        model="gpt-4o-mini",
        api_key=os.getenv("OPENAI_API_KEY"),
    )
    return AssistantAgent(
        name="SkincareSalesAgent",
        model_client=model_client,
        system_message=system_message,
    )


# -----------------------------
# Order summary generation (pre-payment only)
# -----------------------------
async def generate_order_summary(agent, session_id: str, amount: float) -> str:
    """
    Generate an order summary/confirmation message with customer info and price.
    NOTE: This is before payment intent, so AI is allowed.
    """
    info = extract_customer_info_from_conversation(session_id)

    summary_task = (
        "Write a professional order summary for the customer. Include:\n"
        f"- Name: {info['name'] or 'Not provided'}\n"
        f"- Email: {info['email'] or 'Not provided'}\n"
        f"- Phone: {info['phone'] or 'Not provided'}\n"
        f"- Delivery Address: {info['address'] or 'Not provided'}\n"
        f"- Total Amount: ₦{amount:,.0f}\n\n"
        "End with a single question asking them to confirm if everything is correct."
    )

    result = await agent.run(task=summary_task)
    summary_message = result.messages[-1].content
    memory.add_message(session_id, role="assistant", content=summary_message)
    return summary_message


# -----------------------------
# Main handler
# -----------------------------
async def handle_user_message(agent, session_id: str, user_message: str) -> dict:
    """
    Contract returned:
    {
      "reply": str,
      "intent": str,
      "action": str,
      "data": dict
    }
    """

    # Ensure state exists
    SESSION_STATE.setdefault(session_id, "COLLECTING")

    # Always store user message
    memory.add_message(session_id, role="user", content=user_message)

    # If we are in payment lock mode, ALWAYS resend payment button (system-driven)
    if session_id in ACTIVE_PAYMENTS:
        payment_url = ACTIVE_PAYMENT_URLS.get(session_id)
        if payment_url:
            return {
                "reply": "",
                "intent": "payment_locked",
                "action": "payment_link_created",
                "data": {"payment_url": payment_url},
            }
        # If somehow locked without URL, keep silent but expose state
        return {
            "reply": "",
            "intent": "payment_locked",
            "action": "payment_locked",
            "data": {},
        }

    # Detect intent (your intent.py now has deterministic overrides)
    intent = await detect_intent(user_message)

    # NOTE: Replace this with your real product pricing logic later
    # Keep it deterministic on backend; do NOT let AI decide prices.
    amount_naira = 27000

    # -----------------------------
    # 1) Purchase intent => if info complete, show summary & await confirmation
    # -----------------------------
    if intent == "purchase_intent":
        if has_all_customer_info(session_id):
            SESSION_STATE[session_id] = "AWAITING_CONFIRMATION"
            summary = await generate_order_summary(agent, session_id, amount_naira)
            return {
                "reply": summary,
                "intent": intent,
                "action": "show_order_summary",
                "data": {"amount": amount_naira},
            }

        # Not enough info yet -> let AI collect details
        result = await agent.run(task=user_message)
        reply = result.messages[-1].content
        memory.add_message(session_id, role="assistant", content=reply)
        return {
            "reply": reply,
            "intent": intent,
            "action": "collect_customer_info",
            "data": {},
        }

    # -----------------------------
    # 2) Order confirmation => move to awaiting payment (but do NOT start payment yet)
    # -----------------------------
    if intent == "order_confirmation":
        # Only accept confirmation if we really are awaiting it
        if SESSION_STATE.get(session_id) == "AWAITING_CONFIRMATION" and has_all_customer_info(session_id):
            SESSION_STATE[session_id] = "AWAITING_PAYMENT"
            reply = "✅ Great — when you're ready, type **pay now** to receive your Pay Now button."
            memory.add_message(session_id, role="assistant", content=reply)
            return {
                "reply": reply,
                "intent": intent,
                "action": "await_payment_command",
                "data": {},
            }

        # Otherwise, just continue conversation
        result = await agent.run(task=user_message)
        reply = result.messages[-1].content
        memory.add_message(session_id, role="assistant", content=reply)
        return {
            "reply": reply,
            "intent": intent,
            "action": "continue_chat",
            "data": {},
        }

    # -----------------------------
    # 3) Payment initiation => ONLY allowed in AWAITING_PAYMENT state
    # -----------------------------
    if intent == "payment_initiation":
        # Gate by state so "proceed" doesn't trigger payment too early
        if SESSION_STATE.get(session_id) != "AWAITING_PAYMENT":
            result = await agent.run(task=user_message)
            reply = result.messages[-1].content
            memory.add_message(session_id, role="assistant", content=reply)
            return {
                "reply": reply,
                "intent": intent,
                "action": "continue_chat",
                "data": {},
            }

        info = extract_customer_info_from_conversation(session_id)

        # Hard gate: we must have email for Paystack init
        if not info.get("email"):
            reply = "Please send your email address so I can generate your Pay Now button."
            memory.add_message(session_id, role="assistant", content=reply)
            return {
                "reply": reply,
                "intent": intent,
                "action": "request_payment_details",
                "data": {},
            }

        # Build user_data for controller
        user_data = {
            "session_id": session_id,
            "amount": amount_naira,
            **info,
        }

        # Lock payment mode first (prevents AI chatter during checkout)
        ACTIVE_PAYMENTS.add(session_id)

        # System action: create payment link (NO AI)
        action_result = handle_intent_action("payment_initiation", user_data)

        # If link created, store it so we can resend button reliably
        if action_result.get("action") == "payment_link_created":
            payment_url = (action_result.get("data") or {}).get("payment_url")
            if payment_url:
                ACTIVE_PAYMENT_URLS[session_id] = payment_url
                return {
                    "reply": "",
                    "intent": intent,
                    "action": "payment_link_created",
                    "data": {"payment_url": payment_url},
                }

        # If controller failed, unlock and ask user to retry (system message)
        ACTIVE_PAYMENTS.discard(session_id)
        reply = "Sorry — I couldn’t create the payment link right now. Please try again in a moment."
        memory.add_message(session_id, role="assistant", content=reply)
        return {
            "reply": reply,
            "intent": intent,
            "action": "payment_link_failed",
            "data": {},
        }

    # -----------------------------
    # Default: normal chat
    # -----------------------------
    result = await agent.run(task=user_message)
    reply = result.messages[-1].content
    memory.add_message(session_id, role="assistant", content=reply)
    return {
        "reply": reply,
        "intent": intent,
        "action": "continue_chat",
        "data": {},
    }
