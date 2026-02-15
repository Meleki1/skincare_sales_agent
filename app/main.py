import os
import json
import logging
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel

from app.db.database import init_db

from app.agent import (
    create_sales_agent,
    handle_user_message,
    generate_payment_confirmation,
    ACTIVE_PAYMENTS,
    ACTIVE_PAYMENT_URLS,
    SESSION_STATE,
)

from app.services.payment import initialize_payment, verify_payment
from app.services.telegram import send_telegram_message, send_telegram_payment_button
from app.services.webhook import verify_paystack_signature, handle_paystack_event
from app.services.storage import (
    get_session_id_by_payment_reference,
    get_session_id_by_order_id,
)

# -----------------------------
# App init
# -----------------------------
init_db()

app = FastAPI(
    title="AI Skincare Sales Agent",
    description="An AI-powered skincare sales assistant using AutoGen",
    version="1.0.0",
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Create once (no lazy-load confusion)
sales_agent = create_sales_agent()


# -----------------------------
# Schemas
# -----------------------------
class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    intent: str
    action: str


class PaymentInitRequest(BaseModel):
    email: str
    amount: int  # naira


class PaymentVerifyRequest(BaseModel):
    reference: str


# -----------------------------
# API endpoints (optional)
# -----------------------------
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    result = await handle_user_message(
        agent=sales_agent,
        session_id=request.session_id,
        user_message=request.message,
    )
    return ChatResponse(
        reply=result.get("reply", ""),
        intent=result.get("intent", "unknown"),
        action=result.get("action", "continue_chat"),
    )


@app.post("/payment/initiate")
def initiate_payment(request: PaymentInitRequest):
    amount_in_kobo = request.amount * 100
    payment_data = initialize_payment(email=request.email, amount=amount_in_kobo)
    return {
        "payment_url": payment_data["authorization_url"],
        "reference": payment_data["reference"],
    }


@app.post("/payment/verify")
def verify_payment_endpoint(request: PaymentVerifyRequest):
    payment_status = verify_payment(request.reference)
    return {
        "status": payment_status["status"],
        "amount": payment_status["amount"],
        "reference": payment_status["reference"],
    }


# -----------------------------
# Paystack webhook (payment truth source)
# -----------------------------
@app.post("/paystack/webhook")
async def paystack_webhook(request: Request):
    try:
        payload = await request.body()
        signature = request.headers.get("x-paystack-signature", "")

        if not verify_paystack_signature(payload, signature):
            logger.warning("Invalid Paystack webhook signature")
            return Response(status_code=400)

        event = json.loads(payload)
        event_name = event.get("event")
        logger.info(f"Received Paystack webhook event: {event_name}")

        # Only act on success
        if event_name == "charge.success":
            reference = event["data"]["reference"]
            amount = event["data"].get("amount", 0)  # kobo
            status = event["data"].get("status", "")

            logger.info(
                f"Processing successful payment: reference={reference}, amount={amount}, status={status}"
            )

            # Save to DB etc (your existing logic)
            order_id = handle_paystack_event(event)

            # Resolve session_id (Telegram chat_id stored as session_id string)
            session_id = get_session_id_by_payment_reference(reference)

            if not session_id and order_id:
                logger.info(f"Reference lookup failed, trying order_id: {order_id}")
                session_id = get_session_id_by_order_id(order_id)

            if not session_id:
                logger.warning(
                    f"Could not find session_id for reference={reference} (order_id={order_id})"
                )
                return {"status": "ok"}

            # ✅ Unlock + cleanup state (prevents being stuck)
            ACTIVE_PAYMENTS.discard(session_id)
            ACTIVE_PAYMENT_URLS.pop(session_id, None)
            SESSION_STATE.pop(session_id, None)

            # Generate confirmation text (allowed: this is after payment success)
            confirmation_message = await generate_payment_confirmation(
                agent=sales_agent,
                session_id=session_id,
                amount=amount,
            )

            # Send to Telegram if session_id is a chat_id
            try:
                chat_id = int(session_id)
                send_telegram_message(chat_id, confirmation_message)
                logger.info(f"Sent confirmation message to Telegram chat {chat_id}")
            except (ValueError, TypeError):
                logger.info(
                    f"Session {session_id} is not a Telegram chat_id; confirmation saved in memory."
                )

        return {"status": "ok"}

    except json.JSONDecodeError:
        logger.error("Invalid JSON in Paystack webhook payload", exc_info=True)
        return Response(status_code=400)
    except Exception as e:
        logger.error(f"Error processing Paystack webhook: {str(e)}", exc_info=True)
        return Response(status_code=500)


# -----------------------------
# Telegram webhook (frontend)
# -----------------------------
@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()

    # Ignore non-message updates
    if "message" not in data:
        return {"status": "ignored"}

    message = data["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text")

    # Ignore non-text messages
    if not text:
        send_telegram_message(chat_id, "Please send a text message.")
        return {"status": "ok"}

    session_id = str(chat_id)

    # Run agent logic
    result = await handle_user_message(
        agent=sales_agent,
        session_id=session_id,
        user_message=text,
    )

    action = result.get("action", "continue_chat")
    reply = result.get("reply", "")
    data_payload = result.get("data") or {}

    # ✅ Payment button flow (guarded)
    if action == "payment_link_created":
        payment_url = data_payload.get("payment_url")
        if payment_url:
            send_telegram_payment_button(chat_id=chat_id, payment_url=payment_url)
        else:
            # No URL => don't crash; guide user
            send_telegram_message(
                chat_id=chat_id,
                text="⚠️ I couldn't fetch your payment link yet. Please type **pay now** again.",
            )
        return {"status": "ok"}

    # ✅ Normal message flow (never send empty text)
    if reply:
        send_telegram_message(chat_id=chat_id, text=reply)

    return {"status": "ok"}



@app.get("/health")
def health_check():
    return {"status": "ok"}
