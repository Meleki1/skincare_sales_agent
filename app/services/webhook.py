"""
Paystack webhook handler.
"""

import hmac
import hashlib
import os
import json
from app.services.storage import mark_order_paid, create_payment

PAYSTACK_WEBHOOK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")


def verify_paystack_signature(payload: bytes, signature: str) -> bool:
    """
    Verify Paystack webhook signature.
    """
    computed_hash = hmac.new(
        PAYSTACK_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha512
    ).hexdigest()

    return hmac.compare_digest(computed_hash, signature)


def handle_paystack_event(event: dict):
    """
    Handle Paystack webhook events.
    Returns order_id if successful, None otherwise.
    """

    event_type = event.get("event")
    data = event.get("data", {})

    if event_type == "charge.success":
        reference = data.get("reference")
        amount = data.get("amount")
        status = data.get("status")

        metadata = data.get("metadata", {})
        order_id = metadata.get("order_id")

        # Try to get order_id from existing payment if not in metadata
        if not order_id:
            from app.services.storage import get_order_id_by_reference
            order_id = get_order_id_by_reference(reference)

        if not order_id:
            print(f"Warning: No order_id found for payment reference {reference}")
            return None

        # Check if payment already exists to avoid duplicates
        from app.services.storage import payment_exists
        if not payment_exists(reference):
            # Save payment
            create_payment(
                order_id=order_id,
                reference=reference,
                amount=amount,
                status=status
            )
        else:
            # Update existing payment status
            from app.services.storage import update_payment_status
            update_payment_status(reference, status)

        if status == "success":
            mark_order_paid(order_id)
        
        return order_id
    
    return None