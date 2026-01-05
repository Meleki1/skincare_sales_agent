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
    # 1️⃣ Detect intent
    intent = await detect_intent(user_message)

    # 2️⃣ Store user message in memory
    memory.add_message(session_id, role="user", content=user_message)

    # 3️⃣ Build structured user_data for system actions
    user_data = {
        "session_id": session_id
    }

    # Extract email if user sent one
    if "@" in user_message and "." in user_message:
        user_data["email"] = user_message.strip()
        memory.set_value(session_id, "email", user_message.strip())

    # Retrieve stored email if already collected
    stored_email = memory.get_value(session_id, "email")
    if stored_email:
        user_data["email"] = stored_email

    # Set product amount (replace later with dynamic product pricing)
    user_data["amount"] = memory.get_value(session_id, "amount") or 7000
    memory.set_value(session_id, "amount", user_data["amount"])

    # 4️⃣ HARD RULE: payment intent must be handled by system, not AI
    if intent == "payment_initiation":
        action_result = handle_intent_action(intent, user_data)
    else:
        action_result = handle_intent_action(intent)

    # 5️⃣ SYSTEM ACTIONS OVERRIDE AI COMPLETELY
    if action_result["action"] == "payment_link_created":
        # 🔒 Do NOT let AI talk here
        reply = ""

    elif action_result["action"] != "continue_chat":
        reply = action_result["data"].get("message", "")

    else:
        # 6️⃣ Normal AI conversation
        result = await agent.run(task=user_message)
        reply = result.messages[-1].content

    # 7️⃣ Store assistant reply (if any)
    if reply:
        memory.add_message(session_id, role="assistant", content=reply)

    # 8️⃣ Return a strict, frontend-safe response
    return {
        "reply": reply,
        "intent": intent,
        "action": action_result["action"],
        "data": action_result.get("data", {})
    }

