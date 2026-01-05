import requests
import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def send_telegram_message(chat_id: int, text: str):
    """
    Send a message back to a Telegram user.
    """
    url = f"{TELEGRAM_API_URL}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }

    response = requests.post(url, json=payload)
    response.raise_for_status()

def send_telegram_payment_button(chat_id: int, payment_url: str):
    """
    Send a Pay Now button that opens the Paystack payment link.
    """
    url = f"{TELEGRAM_API_URL}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": "💳 Click the button below to complete your payment securely:",
        "reply_markup": {
            "inline_keyboard": [
                [
                    {
                        "text": "✅ Pay Now",
                        "url": payment_url
                    }
                ]
            ]
        }
    }

    response = requests.post(url, json=payload)
    response.raise_for_status()

