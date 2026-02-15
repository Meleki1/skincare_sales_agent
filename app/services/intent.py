import os
from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient


INTENT_PROMPT = """
You are an intent detection agent for a skincare sales assistant.

Classify the user's intent into ONE of the following:
- greeting
- product_inquiry
- pricing
- purchase_intent

- order_confirmation:
  The user confirms the order details are correct (e.g., "yes", "correct", "that's right").
  IMPORTANT: Do NOT use "proceed" for this label.

- payment_initiation:
  The user explicitly wants to pay (e.g., "pay now", "send payment link", "i'll pay", "let's pay", "make payment").
  IMPORTANT: Only use this when the user clearly wants to pay.

- payment_confirmation
- support_request
- general_question

Reply with ONLY the intent label.
"""


def quick_intent_override(text: str) -> str | None:
    """
    Deterministic override for payment-trigger phrases.
    We intentionally DO NOT include "yes" to avoid accidental early payment triggers.
    """
    t = (text or "").strip().lower()

    triggers = {
        "proceed",
        "pay now",
        "i'll pay now",
        "i will pay now",
        "let's pay",
        "lets pay",
        "i'll pay",
        "i will pay",
        "make payment",
        "send payment link",
        "go ahead",
        "continue to payment",
    }

    if t in triggers:
        return "payment_initiation"

    return None


async def detect_intent(user_message: str) -> str:
    # ✅ 1) Try deterministic override first
    override = quick_intent_override(user_message)
    if override:
        return override

    # ✅ 2) Fall back to LLM intent classification
    model_client = OpenAIChatCompletionClient(
        model="gpt-4o-mini",
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    intent_agent = AssistantAgent(
        name="IntentDetector",
        model_client=model_client,
        system_message=INTENT_PROMPT,
    )

    result = await intent_agent.run(task=user_message)
    intent = result.messages[-1].content.strip().lower()

    return intent
