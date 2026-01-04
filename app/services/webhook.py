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
    """

    event_type = event.get("event")
    data = event.get("data", {})

    if event_type == "charge.success":
        reference = data.get("reference")
        amount = data.get("amount")
        status = data.get("status")

        metadata = data.get("metadata", {})
        order_id = metadata.get("order_id")

        # Save payment
        create_payment(
            order_id=order_id,
            reference=reference,
            amount=amount,
            status=status
        )

        if status == "success":
            mark_order_paid(order_id)
