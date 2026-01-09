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
    MUST always return a dict with 'action' and 'data'.
    """

    # ✅ DEFAULT SAFE RESPONSE
    result = {
        "action": "continue_chat",
        "data": {}
    }

    # -------------------------
    # PURCHASE INTENT
    # -------------------------
    if intent == "purchase_intent":
        return {
            "action": "request_payment_details",
            "data": {
                "message": "Please provide your email so I can generate a secure payment link."
            }
        }

    # -------------------------
    # INITIATE PAYMENT
    # -------------------------
    if intent == "payment_initiation" and user_data:
        email = user_data.get("email")
        name = user_data.get("name")
        phone = user_data.get("phone")
        amount = user_data.get("amount")
        session_id = user_data.get("session_id")

        if not email or not amount or not session_id:
            return result  # fallback safely

        # Create customer with all collected information
        address = user_data.get("address")
        customer_id = create_customer(
            session_id=session_id,
            email=email,
            name=name,
            phone=phone,
            address=address
        )

        order_id = create_order(customer_id, amount)

        payment_data = initialize_payment(
            email=email,
            amount=amount * 100,  # convert to kobo
            order_id=str(order_id)
        )

        create_payment(
            order_id=order_id,
            reference=payment_data["reference"],
            amount=amount * 100,
            status="pending"
        )

        return {
            "action": "payment_link_created",
            "data": {
                "payment_url": payment_data["authorization_url"],
                "reference": payment_data["reference"],
                "order_id": order_id
            }
        }

    # -------------------------
    # VERIFY PAYMENT
    # -------------------------
    if intent == "payment_confirmation" and user_data:
        reference = user_data.get("reference")
        order_id = user_data.get("order_id")

        if not reference or not order_id:
            return result

        payment_status = verify_payment(reference)

        create_payment(
            order_id=order_id,
            reference=reference,
            amount=payment_status["amount"],
            status=payment_status["status"]
        )

        if payment_status["status"] == "success":
            mark_order_paid(order_id)

        return {
            "action": "payment_verified",
            "data": payment_status
        }

    # ✅ FINAL FALLBACK
    return result
