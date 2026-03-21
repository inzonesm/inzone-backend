from typing import List, Dict, Any, Optional
import datetime
import re
import os
import asyncio
from autogen import register_function
from autogen_agentchat.agents import AssistantAgent, UserProxyAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient
from load_dotenv import load_dotenv

load_dotenv()

async def get_ai_character_response(
    character_name: str, 
    character_uid: str, 
    conversation_history: str,
    question: str,
    model_client: OpenAIChatCompletionClient
) -> str:
    """
    Tool function that generates a response from an AI character based on the conversation history.
    
    Args:
        character_name: The name of the AI character to generate a response from
        character_uid: The UID of the AI character
        conversation_history: The conversation history as a string
        question: The question or prompt to respond to
        model_client: The model client to use for the character agent
    
    Returns:
        A response from the AI character
    """
    # Create a valid ID for the agent
    character_id = re.sub(r'\W|^(?=\d)', '_', character_name)
    
    # Create a character agent specifically for this response
    character_agent = AssistantAgent(
        character_id,
        description=f"AI character impersonating {character_name}",
        system_message=f"""
        You are {character_name}, an AI character in a group chat.
        
        The conversation history so far:
        {conversation_history}
        
        When responding:
        1. Respond in character as {character_name} with their known personality traits
        2. Be concise and relevant
        3. Respond directly to the previous message or conversation topic
        4. Maintain a conversational tone that feels natural
        5. Do NOT include your name as a prefix in your responses - just respond as the character directly
        """,
        model_client=model_client
    )
    
    # Create a user agent to converse with the character
    # Create user agent with proper 0.5.2 parameters
    user_agent = UserProxyAgent(
        name="user",
        llm_config={"config_list": []},  # Required empty config
        human_input_mode="NEVER",
        code_execution_config=False  # Disable code execution
    )

    
    # Get a response using the run method
    response = await user_agent.a_initiate_chat(
        character_agent,
        message=question
    )
    
    # Extract the response content
    messages = user_agent.chat_messages.get(character_agent.name, [])
    response_text = messages[-1]["content"] if messages else ""
    
    # Clean the response to remove name prefixes if present
    if response_text.lower().startswith(character_name.lower() + ":"):
        response_text = response_text[len(character_name) + 1:].strip()
    if response_text.lower().startswith(character_name.lower() + " :"):
        response_text = response_text[len(character_name) + 2:].strip()
        
    return response_text

async def process_group_chat_messages(
    last_k_messages: List[Dict[str, Any]], 
    participants: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Process group chat messages using a single-agent approach with tools.
    
    Args:
        last_k_messages: List of recent messages from the group chat, following Firestore format
        participants: List of participants in the group chat with uid, type ('ai' or 'user'), and name
    
    Returns:
        Updated messages list with AI character responses added, maintaining Firestore format
    """
    # Initialize OpenAI client
    api_key = os.environ.get("OPENAI_API_KEY", "")
    
    try:
        # Create the model client with proper async handling
        model_client = OpenAIChatCompletionClient(model="gpt-4o-mini")
        
        # Create a formatted conversation history for the orchestrator
        conversation_history = "\n".join([f"{m['sender']['name']}: {m['content']}" for m in last_k_messages])
        
        # Extract AI participants
        ai_participants = [p for p in participants if p.get("type") == "ai"]
        
        # Create a comma-separated list of AI character names for the orchestrator
        ai_names = ", ".join([p.get("name") for p in ai_participants])
        
        # Create the orchestrator agent that will decide which AI characters should respond
        orchestrator = AssistantAgent(
            "Orchestrator",
            description="Agent that decides which AI characters should respond to messages in a group chat",
            system_message=f"""
            You are the orchestrator for a group chat.
            Your job is to analyze the conversation context and determine which AI characters should respond.
            
            The conversation history so far:
            {conversation_history}
            
            Available AI characters: {ai_names}
            
            For each message, you need to decide:
            1. If any AI character should respond
            2. Which specific AI character(s) should respond
            3. The order in which they should respond (if multiple)
            
            Consider:
            - The conversation context and topic
            - Each AI character's expertise and personality
            - Who was addressed in the message (if anyone specifically)
            - The tone and intent of the previous messages
            
            Use the get_ai_character_response function to generate responses from AI characters.
            """,
            model_client=model_client
        )
        
        # Create a user proxy agent to interact with the orchestrator
        user_proxy = UserProxyAgent(
            name="user",  # Use named parameter
            llm_config={"config_list": []},  # Required in newer versions
            code_execution_config=False  # Disable code execution
        )
        
        # Register the get_ai_character_response function
        # Set up function registry and register the character response function
        # registry = FunctionRegistry()
        
        # Define the function with appropriate parameters
        # @registry.register(name="get_ai_character_response")
        # async def get_character_response(character_name: str, character_uid: str, 
        #                                 conversation_history: str, question: str) -> str:
        #     """Get a response from an AI character based on the conversation history"""
        #     return await get_ai_character_response(
        #         character_name, character_uid, conversation_history, question, model_client
        #     )
        
        # # Register the function with the agents
        # registry.register_to_llm(orchestrator)
        # registry.register_to_agent(user_proxy)
        
        register_function(
            get_ai_character_response,
            caller=orchestrator,
            executor=user_proxy,
            name="get_ai_character_response",
            description="Generate AI character response using conversation history"
        )
        # Set the orchestrator as the user proxy's conversation partner      
        # Use the most recent user message to start the interaction
        start_message = None
        for message in reversed(last_k_messages):
            if message.get("sender", {}).get("type") == "user":
                start_message = message
                break
        
        # If no user message found, use the last message
        if not start_message and last_k_messages:
            start_message = last_k_messages[-1]
        
        if not start_message:
            # No messages to process
            return last_k_messages
        
        # Create the task for the orchestrator
        sender_name = start_message.get("sender", {}).get("name", "Unknown")
        content = start_message.get("content", "")
        task = f"""
        Analyze the conversation where {sender_name} said: '{content}'
        
        First, decide which AI character(s) should respond to this message. For each character that should respond:
        
        1. Use the get_ai_character_response function to generate a response
        2. Provide the character's name, UID, conversation history, and the last message as parameters
        
        If multiple characters should respond, call the function multiple times in the order they should respond.
        If no character should respond, explain why.
        
        Available AI characters in this chat:
        {", ".join([f"{p['name']} (UID: {p['uid']})" for p in ai_participants])}
        """
        
        # Run the conversation
        result = await user_proxy.a_initiate_chat(
            orchestrator,
            message=task
        )
        
        # Parse the conversation history to find tool call results
        current_time = datetime.datetime.now()
        time_delta = 0
        
        # Look for tool results in the chat history
        chat_messages = user_proxy.chat_messages.get(orchestrator.name, [])
        
        for message in chat_messages:
            if "function_call" in message:
                function_call = message.get("function_call", {})
                if function_call.get("name") == "get_ai_character_response":
                    # Extract the function arguments
                    import json
                    args = json.loads(function_call.get("arguments", "{}"))
                    character_name = args.get("character_name")
                    character_uid = args.get("character_uid")
                    
                    # Find the corresponding result
                    for idx, msg in enumerate(chat_messages[chat_messages.index(message):]):
                        if "content" in msg and isinstance(msg["content"], str) and character_name in msg["content"]:
                            # Found the response
                            response_parts = msg["content"].split("```")
                            for part in response_parts:
                                if character_name in part and ":" in part:
                                    response_content = part.split(":", 1)[1].strip()
                                    
                                    # Add the response to the messages list
                                    time_delta += 1
                                    message_timestamp = current_time + datetime.timedelta(seconds=time_delta)
                                    
                                    last_k_messages.append({
                                        "id": message_timestamp.strftime("%Y%m%d%H%M%S"),
                                        "sender": {
                                            "uid": character_uid,
                                            "type": "ai",
                                            "name": character_name
                                        },
                                        "content": response_content,
                                        "isProcessed": True
                                    })
                                    break
                            break
                    
    except Exception as e:
        # In case of error, add a system message explaining the issue
        current_time = datetime.datetime.now()
        last_k_messages.append({
            "id": current_time.strftime("%Y%m%d%H%M%S"),
            "sender": {
                "uid": "system",
                "type": "system",
                "name": "System"
            },
            "content": f"Error processing messages: {str(e)}",
            "isProcessed": True
        })
    finally:
        # Ensure model client is properly closed
        if 'model_client' in locals():
            await model_client.close()
    
    return last_k_messages


# Example usage:
if __name__ == "__main__":
    # Sample messages and participants in Firestore format
    current_time = datetime.datetime.now()
    
    messages = [
        {
            "id": current_time.strftime("%Y%m%d%H%M%S"),
            "sender": {"uid": "user123", "type": "user", "name": "aryan527"},
            "content": "What's it like on a Hollywood movie set? I've always been curious!",
            "isProcessed": True
        }
    ]
    
    participants = [
        {"uid": "user123", "type": "user", "name": "aryan527"},
        {"uid": "ai_emma", "type": "ai", "name": "Emma Watson"},
        {"uid": "ai_zendaya", "type": "ai", "name": "Zendaya"},
        {"uid": "ai_sydney", "type": "ai", "name": "Sydney Sweeney"}
    ]
    
    # Process messages using asyncio
    async def run():
        updated_messages = await process_group_chat_messages(messages, participants)
        # Print updated messages
        print("Updated Messages:")
        for message in updated_messages:
            print(f"{message['sender']['name']}: {message['content']}")
    
    # Run the async function
    asyncio.run(run())
