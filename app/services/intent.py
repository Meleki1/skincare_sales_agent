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
- payment_initiation (when user confirms they want to pay, e.g., "yes", "proceed", "I'll pay", "let's pay")
- payment_confirmation
- support_request
- general_question

Reply with ONLY the intent label.
"""


async def detect_intent(user_message: str) -> str:
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