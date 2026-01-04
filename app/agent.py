
from autogen_agentchat.agents import AssistantAgent
from app.prompts.system_prompt import system_message
from app.services.memory import memory
from app.services.intent import detect_intent
from app.services.controller import handle_intent_action


def create_sales_agent():
    """
    Create the AutoGen assistant agent.
    AutoGen will automatically use OPENAI_API_KEY from environment.
    """

    agent = AssistantAgent(
        name="SkincareSalesAgent",
        system_message=system_message,
    )

    return agent


def handle_user_message(agent, session_id: str, user_message: str) -> dict:
    """
    Handle user messages with intent detection and action routing.
    """

    # Detect intent
    intent = detect_intent(user_message)

    # Save user message
    memory.add_message(session_id, role="user", content=user_message)

    # Decide system action
    action_result = handle_intent_action(intent)

    # If controller wants a direct system response
    if action_result["action"] != "continue_chat":
        reply = action_result["data"].get("message", "")
    else:
        messages = memory.get_messages(session_id)

        reply = agent.generate_reply(
            messages=messages + [
                {"role": "system", "content": f"Detected intent: {intent}"},
                {"role": "user", "content": user_message},
            ]
        )

    # Save assistant reply
    memory.add_message(session_id, role="assistant", content=reply)

    return {
        "reply": reply,
        "intent": intent,
        "action": action_result["action"],
    }
