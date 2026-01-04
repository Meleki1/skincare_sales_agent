from autogen_agentchat.agents import AssistantAgent
from app.prompts.system_prompt import system_message
import os
from app.services.memory import ConversationMemory
from app.services.intent import detect_intent
from app.services.controller import handle_intent_action
from autogen_agentchat.agents import config_list_from_json, set_default_llm_config





memory = ConversationMemory()



import os

set_default_llm_config({
    "config_list": [
        {
            "model": "gpt-4o-mini",
            "api_key": os.getenv("OPENAI_API_KEY"),
        }
    ],
    "temperature": 0.4,
})






def create_sales_agent():
    sales_agent = AssistantAgent(
        name="SkincareSalesAgent",
        system_message=system_message,
    )

    return sales_agent





def handle_user_message(agent, session_id: str, user_message: str) -> dict:
    """
    Handle user message with intent-based action control.
    """

    intent = detect_intent(user_message)

    # Store user message
    memory.add_message(session_id, role="user", content=user_message)

    # Ask controller what to do
    action_result = handle_intent_action(intent)

    # -------------------------
    # ACTION-BASED RESPONSES
    # -------------------------
    if action_result["action"] == "request_payment_details":
        reply = action_result["data"]["message"]

    elif action_result["action"] == "payment_link_created":
        reply = (
            "Your payment link is ready:\n"
            f"{action_result['data']['payment_url']}\n\n"
            "Please complete the payment and let me know once done."
        )

    elif action_result["action"] == "payment_verified":
        if action_result["data"]["status"] == "success":
            reply = "✅ Payment confirmed! Your order is being processed."
        else:
            reply = "❌ Payment not successful yet. Please try again or let me assist you."

    else:
        # Normal AI conversation
        messages = memory.get_messages(session_id)

        response = agent.generate_reply(
            messages=messages + [
                {"role": "system", "content": f"Detected user intent: {intent}"},
                {"role": "user", "content": user_message}
            ]
        )

        reply = response

    # Store assistant reply
    memory.add_message(session_id, role="assistant", content=reply)

    return {
        "reply": reply,
        "intent": intent,
        "action": action_result["action"]
    }

