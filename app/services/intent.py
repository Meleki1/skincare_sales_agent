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
- payment_confirmation
- support_request
- general_question

Reply with ONLY the intent label.
"""


def detect_intent(user_message: str) -> str:
    model_client = OpenAIChatCompletionClient(
        model="gpt-4o-mini",
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    intent_agent = AssistantAgent(
        name="IntentDetector",
        model_client=model_client,
        system_message=INTENT_PROMPT,
    )

    response = intent_agent.generate_reply(
        messages=[{"role": "user", "content": user_message}]
    )

    return response.strip().lower()
