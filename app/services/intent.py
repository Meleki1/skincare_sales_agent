from autogen_agentchat.agents import AssistantAgent
from app.prompts.intent_prompt import INTENT_CLASSIFICATION_PROMPT
import os


def detect_intent(user_message: str) -> str:
    """
    Detect the intent of a user message.
    """

    intent_agent = AssistantAgent(
        name="IntentDetector",
        system_message=INTENT_CLASSIFICATION_PROMPT,
        llm_config={
            "config_list": [
                {
                    "model": "gpt-4o-mini",
                    "api_key": os.getenv("OPENAI_API_KEY"),
                }
            ],
            "temperature": 0.0,  # ZERO creativity for classification
        },
    )

    response = intent_agent.generate_reply(
        messages=[{"role": "user", "content": user_message}]
    )

    return response.strip().lower()
