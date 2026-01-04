from app.services.payment import initialize_payment, verify_payment
from app.services.storage import (
    create_customer,
    create_order,
    create_payment,
    mark_order_paid
)



def handle_intent_action(
    intent: str,
    user_data: dict | None = None
) -> dict:
    """
    Decide what action to take based on intent.

    Returns a dict describing the action result.
    """

    # Default: no action, just chat
    result = {
        "action": "continue_chat",
        "data": None
    }

    # -------------------------
    # PURCHASE INTENT
    # -------------------------
    if intent == "purchase_intent":
        result["action"] = "request_payment_details"
        result["data"] = {
            "message": "Please provide your email so I can generate a secure payment link."
        }

    # -------------------------
    # INITIATE PAYMENT
    # -------------------------
    elif intent == "payment_initiation" and user_data:
        email = user_data.get("email")
        amount = user_data.get("amount")  # naira

        if email and amount:
            payment_data = initialize_payment(
                email=email,
                amount=amount * 100  # convert to kobo
            )

            result["action"] = "payment_link_created"
            result["data"] = {
                "payment_url": payment_data["authorization_url"],
                "reference": payment_data["reference"]
            }


    elif intent == "payment_initiation" and user_data:
        email = user_data.get("email")
        amount = user_data.get("amount")
        session_id = user_data.get("session_id")

        customer_id = create_customer(
            session_id=session_id,
            email=email
        )

        order_id = create_order(customer_id, amount)

        payment_data = initialize_payment(
            email=email,
            amount=amount * 100
        )

        create_payment(
            order_id=order_id,
            reference=payment_data["reference"],
            amount=amount * 100,
            status="pending"
        )

        result["action"] = "payment_link_created"
        result["data"] = {
            "payment_url": payment_data["authorization_url"],
            "reference": payment_data["reference"]
        }


    # -------------------------
    # VERIFY PAYMENT
    # -------------------------
    elif intent == "payment_confirmation" and user_data:
        reference = user_data.get("reference")
        order_id = user_data.get("order_id")

        payment_status = verify_payment(reference)

        create_payment(
            order_id=order_id,
            reference=reference,
            amount=payment_status["amount"],
            status=payment_status["status"]
        )

        if payment_status["status"] == "success":
            mark_order_paid(order_id)

        result["action"] = "payment_verified"
        result["data"] = payment_status


    
