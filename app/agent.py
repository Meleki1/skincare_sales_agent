import os
import re
from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
from app.prompts.system_prompt import system_message
from app.services.memory import memory
from app.services.intent import detect_intent
from app.services.controller import handle_intent_action


ACTIVE_PAYMENTS = set()


def extract_email_from_text(text: str) -> str | None:
    """Extract email address from text using regex."""
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    match = re.search(email_pattern, text)
    return match.group(0) if match else None


def extract_email_from_conversation(session_id: str) -> str | None:
    """Extract email from conversation history."""
    messages = memory.get_messages(session_id)
    
    # Search through all messages for email
    for msg in messages:
        email = extract_email_from_text(msg.get("content", ""))
        if email:
            return email
    
    return None



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


async def generate_payment_confirmation(agent, session_id: str, amount: float = None) -> str:
    """
    Generate a payment confirmation message using the chatbot agent.
    """
    # Convert amount from kobo to naira if provided
    amount_text = ""
    if amount:
        amount_naira = amount / 100
        amount_text = f" of ₦{amount_naira:,.0f}"
    
    confirmation_task = (
        f"The customer's payment{amount_text} has been successfully confirmed. "
        "Generate a warm, professional confirmation message that: "
        "1. Confirms the payment was successful "
        "2. Thanks them for their purchase "
        "3. Mentions that their order is being processed "
        "4. Keeps it concise and friendly (2-3 sentences max)"
    )
    
    result = await agent.run(task=confirmation_task)
    confirmation_message = result.messages[-1].content
    
    # Add the confirmation to memory
    memory.add_message(session_id, role="assistant", content=confirmation_message)
    
    return confirmation_message


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

    # Check if user is providing email after payment request
    # Look at the last assistant message to see if it asked for email
    messages = memory.get_messages(session_id)
    email_provided = extract_email_from_text(user_message)
    
    if email_provided and len(messages) >= 2:
        # Check if last assistant message was asking for email
        last_assistant_msg = None
        for msg in reversed(messages[:-1]):  # Exclude current user message
            if msg.get("role") == "assistant":
                last_assistant_msg = msg.get("content", "").lower()
                break
        
        # If assistant asked for email and user provided it, trigger payment
        if last_assistant_msg and ("email" in last_assistant_msg or "payment" in last_assistant_msg):
            user_data["email"] = email_provided
            ACTIVE_PAYMENTS.add(session_id)
            
            action_result = handle_intent_action("payment_initiation", user_data)
            
            return {
                "reply": "",
                "intent": "payment_initiation",
                "action": action_result["action"],
                "data": action_result.get("data", {})
            }

    # If payment intent detected → LOCK PAYMENT MODE
    if intent == "payment_initiation":
        # Try to extract email from current message or conversation history
        email = extract_email_from_text(user_message) or extract_email_from_conversation(session_id)
        
        if email:
            user_data["email"] = email
            ACTIVE_PAYMENTS.add(session_id)
            
            action_result = handle_intent_action(intent, user_data)
            
            return {
                "reply": "",
                "intent": intent,
                "action": action_result["action"],
                "data": action_result.get("data", {})
            }
        else:
            # Email not found - ask for it via AI
            result = await agent.run(task="The user wants to proceed with payment but hasn't provided their email. Politely ask them for their email address so you can generate a secure payment link.")
            reply = result.messages[-1].content
            
            memory.add_message(session_id, role="assistant", content=reply)
            
            return {
                "reply": reply,
                "intent": intent,
                "action": "request_email",
                "data": {}
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



