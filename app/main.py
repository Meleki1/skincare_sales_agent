

import json
from fastapi import FastAPI, Response
from pydantic import BaseModel
from app.services.payment import initialize_payment, verify_payment
from app.agent import create_sales_agent, handle_user_message, generate_payment_confirmation, ACTIVE_PAYMENTS
from app.db.database import init_db
from fastapi import Request, Header, HTTPException
from app.services.telegram import send_telegram_message, send_telegram_payment_button
from app.services.webhook import verify_paystack_signature, handle_paystack_event
from app.services.storage import (
    get_session_id_by_payment_reference, 
    get_session_id_by_order_id,
    mark_order_paid, 
    create_payment
)





sales_agent = create_sales_agent()
init_db()

app = FastAPI(
    title="AI Skincare Sales Agent",
    description="An AI-powered skincare sales assistant using AutoGen",
    version="1.0.0"
)


class ChatRequest(BaseModel):
    session_id: str
    message: str


    
class ChatResponse(BaseModel):
    reply: str
    intent: str
    action: str




@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    result = await handle_user_message(
        agent=sales_agent,
        session_id=request.session_id,
        user_message=request.message
    )

    return ChatResponse(
        reply=result["reply"],
        intent=result["intent"],
        action=result["action"]
    )



class PaymentInitRequest(BaseModel):
    email: str
    amount: int  # amount in naira


class PaymentVerifyRequest(BaseModel):
    reference: str


@app.post("/payment/initiate")
def initiate_payment(request: PaymentInitRequest):
    # Convert naira to kobo
    amount_in_kobo = request.amount * 100

    payment_data = initialize_payment(
        email=request.email,
        amount=amount_in_kobo
    )

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


@app.post("/paystack/webhook")
async def paystack_webhook(request: Request):
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        payload = await request.body()
        signature = request.headers.get("x-paystack-signature")

        if not verify_paystack_signature(payload, signature):
            logger.warning("Invalid Paystack webhook signature")
            return Response(status_code=400)

        event = json.loads(payload)
        logger.info(f"Received Paystack webhook event: {event.get('event')}")

        if event["event"] == "charge.success":
            reference = event["data"]["reference"]
            amount = event["data"].get("amount", 0)  # amount in kobo
            status = event["data"].get("status")
            
            logger.info(f"Processing successful payment: reference={reference}, amount={amount}, status={status}")
            
            # Handle payment event first (save to database)
            # This returns order_id which we can use as fallback
            order_id = handle_paystack_event(event)
            
            # Try to get session_id from payment reference
            session_id = get_session_id_by_payment_reference(reference)
            
            # Fallback: try to get session_id from order_id if payment lookup failed
            if not session_id and order_id:
                logger.info(f"Payment reference lookup failed, trying order_id: {order_id}")
                session_id = get_session_id_by_order_id(order_id)
            
            if session_id:
                logger.info(f"Found session_id: {session_id} for payment {reference}")
                
                # Unlock payment lock
                ACTIVE_PAYMENTS.discard(session_id)
                
                # Generate confirmation message using the chatbot agent
                global sales_agent
                if sales_agent is None:
                    sales_agent = create_sales_agent()
                
                try:
                    confirmation_message = await generate_payment_confirmation(
                        agent=sales_agent,
                        session_id=session_id,
                        amount=amount
                    )
                    
                    logger.info(f"Generated confirmation message for session {session_id}")
                    
                    # Send confirmation via Telegram if it's a Telegram session
                    # (session_id is chat_id for Telegram)
                    try:
                        chat_id = int(session_id)
                        send_telegram_message(chat_id, confirmation_message)
                        logger.info(f"Sent confirmation message to Telegram chat {chat_id}")
                    except (ValueError, TypeError):
                        # Not a Telegram chat_id, might be a different platform
                        # The confirmation is already saved in memory
                        logger.info(f"Session {session_id} is not a Telegram chat_id, confirmation saved to memory")
                except Exception as e:
                    logger.error(f"Error generating confirmation message: {str(e)}", exc_info=True)
            else:
                logger.warning(f"Could not find session_id for payment reference {reference} and order_id {order_id}")

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in webhook payload: {str(e)}")
        return Response(status_code=400)
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        return Response(status_code=500)

    return {"status": "ok"}



@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()

    # Safety check
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

    # Lazy-load agent
    global sales_agent
    if sales_agent is None:
        sales_agent = create_sales_agent()

    # Use existing AI logic
    result = await handle_user_message(
        agent=sales_agent,
        session_id=session_id,
        user_message=text
    )

    reply_text = result["reply"]

    if result["action"] == "payment_link_created":
        payment_url = result["data"]["payment_url"]

        send_telegram_payment_button(
            chat_id=chat_id,
            payment_url=payment_url
        )
    else:
        if result["reply"]:  # ✅ only send if text is not empty
            send_telegram_message(
                chat_id=chat_id,
                text=result["reply"]
            )


    return {"status": "ok"}


@app.get("/health")
def health_check():
    return {"status": "ok"}





