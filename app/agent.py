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


def extract_phone_from_text(text: str) -> str | None:
    """Extract phone number from text using regex."""
    # Nigerian phone patterns: +234, 234, 0 followed by 10 digits
    phone_patterns = [
        r'\+?234[789]\d{9}',  # +234 or 234 followed by 10 digits
        r'0[789]\d{9}',  # 0 followed by 10 digits
        r'\b\d{11}\b',  # 11 digits
    ]
    
    for pattern in phone_patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    
    return None


def extract_customer_info_from_conversation(session_id: str) -> dict:
    """
    Extract customer information (name, email, phone, address) from conversation history.
    Returns dict with keys: name, email, phone, address (values can be None)
    """
    messages = memory.get_messages(session_id)
    info = {
        "name": None,
        "email": None,
        "phone": None,
        "address": None
    }
    
    # Search through all messages
    for msg in messages:
        content = msg.get("content", "")
        
        # Extract email
        if not info["email"]:
            email = extract_email_from_text(content)
            if email:
                info["email"] = email
        
        # Extract phone
        if not info["phone"]:
            phone = extract_phone_from_text(content)
            if phone:
                info["phone"] = phone
        
        # Try to extract name (look for patterns like "my name is", "I'm", etc.)
        if not info["name"]:
            name_patterns = [
                r'(?:my name is|i\'?m|i am|call me|name:)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
                r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)$',  # Standalone name
            ]
            for pattern in name_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    potential_name = match.group(1).strip()
                    # Basic validation: name should be 2-50 chars and not contain numbers
                    if 2 <= len(potential_name) <= 50 and not re.search(r'\d', potential_name):
                        info["name"] = potential_name
                        break
        
        # Try to extract address (look for keywords like "address", "deliver to", etc.)
        if not info["address"]:
            address_keywords = ["address", "deliver", "delivery", "location", "live at", "reside"]
            if any(keyword in content.lower() for keyword in address_keywords):
                # Try to extract text after address keywords
                address_patterns = [
                    r'(?:address|deliver to|delivery|location|live at|reside)[:\s]+(.{10,200})',
                ]
                for pattern in address_patterns:
                    match = re.search(pattern, content, re.IGNORECASE)
                    if match:
                        potential_address = match.group(1).strip()
                        # Remove trailing punctuation and validate length
                        potential_address = re.sub(r'[.,;!?]+$', '', potential_address)
                        if 10 <= len(potential_address) <= 200:
                            info["address"] = potential_address
                            break
    
    return info


def has_all_customer_info(session_id: str) -> bool:
    """Check if all required customer information is collected."""
    info = extract_customer_info_from_conversation(session_id)
    return all([info["name"], info["email"], info["phone"], info["address"]])


async def generate_order_summary(agent, session_id: str, amount: float) -> str:
    """
    Generate an order summary/confirmation message with customer info and price.
    """
    info = extract_customer_info_from_conversation(session_id)
    
    summary_task = (
        f"Generate a professional order confirmation message for the customer. "
        f"Customer details:\n"
        f"- Name: {info['name'] or 'Not provided'}\n"
        f"- Email: {info['email'] or 'Not provided'}\n"
        f"- Phone: {info['phone'] or 'Not provided'}\n"
        f"- Delivery Address: {info['address'] or 'Not provided'}\n"
        f"- Total Amount: ₦{amount:,.0f}\n\n"
        f"Format the message to:\n"
        f"1. Thank them for their order\n"
        f"2. Display all their information clearly\n"
        f"3. Show the total amount prominently\n"
        f"4. Ask them to confirm if everything is correct before proceeding with payment\n"
        f"5. Keep it warm and professional (3-4 sentences)"
    )
    
    result = await agent.run(task=summary_task)
    summary_message = result.messages[-1].content
    
    # Add the summary to memory
    memory.add_message(session_id, role="assistant", content=summary_message)
    
    return summary_message



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

    # Check if user is confirming order details
    if intent == "order_confirmation":
        # Check if all customer info is collected
        if has_all_customer_info(session_id):
            # Check if summary was already shown (look for order summary in recent messages)
            messages = memory.get_messages(session_id)
            summary_shown = False
            for msg in reversed(messages[:-1]):  # Exclude current user message
                if msg.get("role") == "assistant":
                    content = msg.get("content", "").lower()
                    if any(keyword in content for keyword in ["order summary", "total amount", "delivery address"]):
                        summary_shown = True
                        break
            
            if summary_shown:
                # Summary already shown, user is confirming - proceed to payment
                info = extract_customer_info_from_conversation(session_id)
                user_data.update(info)
                ACTIVE_PAYMENTS.add(session_id)
                
                action_result = handle_intent_action("payment_initiation", user_data)
                
                return {
                    "reply": "",
                    "intent": "payment_initiation",
                    "action": action_result["action"],
                    "data": action_result.get("data", {})
                }
            else:
                # Summary not shown yet - generate and show it
                info = extract_customer_info_from_conversation(session_id)
                user_data.update(info)
                
                summary = await generate_order_summary(agent, session_id, user_data["amount"])
                
                return {
                    "reply": summary,
                    "intent": "order_confirmation",
                    "action": "show_order_summary",
                    "data": {
                        "customer_info": info,
                        "amount": user_data["amount"]
                    }
                }
        else:
            # Not all info collected yet, let AI continue collecting
            result = await agent.run(task=user_message)
            reply = result.messages[-1].content
            memory.add_message(session_id, role="assistant", content=reply)
            
            return {
                "reply": reply,
                "intent": intent,
                "action": "collect_customer_info",
                "data": {}
            }

    # If payment intent detected after order confirmation → LOCK PAYMENT MODE
    if intent == "payment_initiation":
        # Check if all customer info is collected
        if has_all_customer_info(session_id):
            info = extract_customer_info_from_conversation(session_id)
            user_data.update(info)
            ACTIVE_PAYMENTS.add(session_id)
            
            action_result = handle_intent_action(intent, user_data)
            
            return {
                "reply": "",
                "intent": intent,
                "action": action_result["action"],
                "data": action_result.get("data", {})
            }
        else:
            # Missing info - let AI ask for it
            result = await agent.run(task=user_message)
            reply = result.messages[-1].content
            memory.add_message(session_id, role="assistant", content=reply)
            
            return {
                "reply": reply,
                "intent": intent,
                "action": "collect_customer_info",
                "data": {}
            }

    # Check if purchase intent and all info is collected - show order summary
    if intent == "purchase_intent":
        if has_all_customer_info(session_id):
            info = extract_customer_info_from_conversation(session_id)
            user_data.update(info)
            
            # Generate and show order summary
            summary = await generate_order_summary(agent, session_id, user_data["amount"])
            
            return {
                "reply": summary,
                "intent": "purchase_intent",
                "action": "show_order_summary",
                "data": {
                    "customer_info": info,
                    "amount": user_data["amount"]
                }
            }
        else:
            # Not all info collected - let AI continue collecting
            result = await agent.run(task=user_message)
            reply = result.messages[-1].content
            memory.add_message(session_id, role="assistant", content=reply)
            
            return {
                "reply": reply,
                "intent": intent,
                "action": "collect_customer_info",
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



