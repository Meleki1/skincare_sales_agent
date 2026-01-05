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
    intent = await detect_intent(user_message)

    memory.add_message(session_id, role="user", content=user_message)

    action_result = handle_intent_action(intent)

    # System-driven action
    if action_result["action"] != "continue_chat":
        reply = action_result["data"].get(
            "message",
            "Please proceed."
        )
    else:
        # Agent already has system prompt; just run it
        result = await agent.run(task=user_message)
        reply = result.messages[-1].content

    memory.add_message(session_id, role="assistant", content=reply)

    return {
        "reply": reply,
        "intent": intent,
        "action": action_result["action"],
    }
