import os
import requests
import uuid


PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_BASE_URL = "https://api.paystack.co"


def initialize_payment(email: str, amount: int, order_id: str = None) -> dict:
    """
    Initialize a Paystack payment.
    amount: amount in kobo (₦1000 = 100000)
    order_id: optional order ID to include in metadata
    """

    reference = str(uuid.uuid4())

    url = f"{PAYSTACK_BASE_URL}/transaction/initialize"
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "email": email,
        "amount": amount,
        "reference": reference,
    }
    
    if order_id:
        payload["metadata"] = {
            "order_id": order_id
        }

    

    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()

    return response.json()["data"]


def verify_payment(reference: str) -> dict:
    """
    Verify a Paystack payment using the transaction reference.
    """

    url = f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}"
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()

    return response.json()["data"]

