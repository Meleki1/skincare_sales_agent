

from fastapi import FastAPI
from pydantic import BaseModel
from app.services.payment import initialize_payment, verify_payment
from app.agent import create_sales_agent, handle_user_message
from app.db.database import init_db
from fastapi import Request, Header, HTTPException
from app.services.webhook import (
    verify_paystack_signature,
    handle_paystack_event
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
def chat(request: ChatRequest):
    result = handle_user_message(
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


@app.post("/webhook/paystack")
async def paystack_webhook(
    request: Request,
    x_paystack_signature: str = Header(None)
):
    payload = await request.body()

    if not verify_paystack_signature(payload, x_paystack_signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    event = json.loads(payload.decode())
    handle_paystack_event(event)

    return {"status": "success"}

@app.get("/health")
def health_check():
    return {"status": "ok"}





