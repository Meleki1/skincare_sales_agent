import os
from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
from app.prompts.system_prompt import system_message
from app.services.memory import memory
from app.services.intent import detect_intent
from app.services.controller import handle_intent_action


def create_sales_agent():
    """
    Create the AutoGen assistant agent with explicit model client.
    """

    model_client = OpenAIChatCompletionClient(
        model="gpt-4o-mini",
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    agent = AssistantAgent(
        name="SkincareSalesAgent",
        model_client=model_client,
        system_message=system_message,
    )

    return agent


async def handle_user_message(agent, session_id: str, user_message: str) -> dict:
    # 🔒 HARD STOP: if payment already started, AI is muted
    if session_id in ACTIVE_PAYMENTS:
        return {
            "reply": "",
            "intent": "payment_locked",
            "action": "payment_link_created",
            "data": {}
        }

    intent = await detect_intent(user_message)

    memory.add_message(session_id, role="user", content=user_message)

    user_data = {
        "session_id": session_id,
        "amount": 27000  # example – set once per product
    }

    # If payment intent detected → LOCK PAYMENT MODE
    if intent == "payment_initiation":
        ACTIVE_PAYMENTS.add(session_id)

        action_result = handle_intent_action(intent, user_data)

        return {
            "reply": "",
            "intent": intent,
            "action": action_result["action"],
            "data": action_result.get("data", {})
        }

    # Normal chat ONLY if not payment
    result = await agent.run(task=user_message)
    reply = result.messages[-1].content

    memory.add_message(session_id, role="assistant", content=reply)

    return {
        "reply": reply,
        "intent": intent,
        "action": "continue_chat",
        "data": {}
    }



