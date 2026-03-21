from typing import List, Dict, Any, Optional, Sequence
import asyncio
import datetime
import re
import uuid
import os
# Change the import to use AssistantAgent for user representations too
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import BaseAgentEvent, BaseChatMessage, TextMessage
from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination
from autogen_agentchat.teams import SelectorGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient

def make_valid_id(name: str) -> str:
    """
    Convert a name to a valid Python identifier.
    
    Args:
        name: The name to convert
        
    Returns:
        A valid Python identifier
    """
    # Replace spaces and special characters with underscores
    valid_id = re.sub(r'\W|^(?=\d)', '_', name)
    return valid_id

def process_group_chat_messages(last_k_messages: List[Dict[str, Any]], participants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Process group chat messages using a SelectorGroupChat framework with an orchestrator agent.
    
    Args:
        last_k_messages: List of recent messages from the group chat, following Firestore format
        participants: List of participants in the group chat with uid, type ('ai' or 'user'), and name
    
    Returns:
        Updated messages list with AI agent responses added, maintaining Firestore format
    """
    # Initialize OpenAI client for all agents
    model_client = OpenAIChatCompletionClient(model="gpt-4o-mini", api_key="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")
    
    # Create a formatted conversation history for system messages
    conversation_history = "\n".join([f"{m['sender']['name']}: {m['content']}" for m in last_k_messages])
    
    # Create the orchestrator agent to decide which AI characters should respond
    orchestrator_agent = AssistantAgent(
        "Orchestrator",
        description="Agent that decides which AI characters should respond to messages in a group chat",
        system_message=f"""
        You are the orchestrator agent for a group chat.
        Your job is to analyze the conversation context and determine which AI characters should respond.
        
        The conversation history so far:
        {conversation_history}
        
        For each message, you need to decide:
        1. If any AI character should respond
        2. Which specific AI character(s) should respond
        3. The order in which they should respond (if multiple)
        
        Consider:
        - The conversation context and topic
        - Each AI character's expertise and personality
        - Who was addressed in the message (if anyone specifically)
        - The tone and intent of the previous messages
        
        Respond with your selection in this format:
        SELECTED: [Character1, Character2, ...]
        or
        SELECTED: None
        """,
        model_client=model_client
    )
    
    # Create AI character agents from the participants list
    ai_agents = []
    ai_agent_ids = []  # Technical IDs used for agents
    ai_agent_display_names = []  # Display names of the agents
    ai_name_to_id_map = {}  # Map from display names to technical IDs
    ai_id_to_name_map = {}  # Map from technical IDs to display names
    
    for participant in participants:
        if participant.get("type") == "ai":
            uid = participant.get("uid")
            display_name = participant.get("name")
            
            # Create a valid Python identifier from the name
            agent_id = make_valid_id(display_name)
            
            # Store the mappings
            ai_name_to_id_map[display_name] = agent_id
            ai_id_to_name_map[agent_id] = display_name
            
            # Create the agent with the valid identifier, including conversation history in system message
            agent = AssistantAgent(
                agent_id,
                description=f"AI character impersonating {display_name}",
                system_message=f"""
                You are {display_name}, an AI character in a group chat.
                
                The conversation history so far:
                {conversation_history}
                
                When selected to respond:
                1. Respond in character as {display_name} with their known personality traits
                2. Be concise and relevant
                3. Respond directly to the previous message or conversation topic
                4. Maintain a conversational tone that feels natural
                5. Do NOT include your name as a prefix in your responses - just respond as the character directly
                """,
                model_client=model_client
            )
            
            ai_agents.append(agent)
            ai_agent_ids.append(agent_id)
            ai_agent_display_names.append(display_name)
    
    # Create reference agents for user participants (using AssistantAgent instead of UserProxyAgent)
    user_agents = []
    user_agent_ids = []
    user_id_to_name_map = {}
    user_name_to_id_map = {}
    
    for participant in participants:
        if participant.get("type") == "user":
            display_name = participant.get("name")
            
            # Create a valid Python identifier
            agent_id = make_valid_id(display_name)
            
            # Store the mappings
            user_name_to_id_map[display_name] = agent_id
            user_id_to_name_map[agent_id] = display_name
            
            # Create a silent placeholder agent (still using AssistantAgent but configured to be silent)
            # This prevents the agent from prompting for input
            user_agent = AssistantAgent(
                agent_id,
                description=f"User in the group chat named {display_name}",
                system_message=f"""
                You represent {display_name}, a user in the group chat.
                You do not generate content - you're just a placeholder for a real user.
                Always stay silent and never respond to any messages.
                """,
                model_client=model_client
            )
            user_agents.append(user_agent)
            user_agent_ids.append(agent_id)
    
    # Define the selector function that allows the orchestrator to choose which AI agents respond
    def selector_func(messages: Sequence[BaseAgentEvent | BaseChatMessage]) -> str | None:
        # If last message is from orchestrator, use its selection
        if messages and messages[-1].source == orchestrator_agent.name:
            content = messages[-1].content
            if isinstance(content, str) and "SELECTED:" in content:
                selection_text = content.split("SELECTED:")[1].strip()
                if selection_text == "None":
                    # No AI should respond
                    return None
                
                # Parse the selected agent display names
                selected_agents = [name.strip() for name in selection_text.strip("[]").split(",")]
                
                # Convert the display names to agent IDs and return the first one that's available
                for display_name in selected_agents:
                    if display_name in ai_name_to_id_map:
                        agent_id = ai_name_to_id_map[display_name]
                        if agent_id in ai_agent_ids:
                            return agent_id
        
        # If there are no messages yet, return the orchestrator
        if not messages:
            return orchestrator_agent.name
        
        # If any AI agent was last to speak, let the orchestrator decide what happens next
        if messages and messages[-1].source in ai_agent_ids:
            return orchestrator_agent.name
        
        # Default to returning the orchestrator
        return orchestrator_agent.name

    # Combine all agents
    all_agents = [orchestrator_agent] + ai_agents + user_agents
    
    # Set up termination conditions - stop after a reasonable number of exchanges
    max_messages_termination = MaxMessageTermination(max_messages=7)  # Reduced from 10 to prevent too many exchanges
    
    # Create the group chat
    group_chat = SelectorGroupChat(
        all_agents,
        model_client=model_client,
        selector_func=selector_func,
        allow_repeated_speaker=True,
        termination_condition=max_messages_termination
    )
    
    # Create maps from display names to agent IDs for all participants
    all_name_to_id_map = {**ai_name_to_id_map, **user_name_to_id_map}
    all_id_to_name_map = {**ai_id_to_name_map, **user_id_to_name_map}
    
    # Use the most recent user message to start the chat
    start_message = None
    for message in reversed(last_k_messages):
        if message.get("sender", {}).get("type") == "user":
            start_message = message
            break
    
    # If no user message found, use the last message
    if not start_message and last_k_messages:
        start_message = last_k_messages[-1]
    
    # Run the group chat to generate responses
    try:
        # Use event loop to run the chat
        loop = asyncio.get_event_loop()
        
        # Create task message from the last user message or a general continuation prompt
        if start_message:
            sender_name = start_message.get("sender", {}).get("name", "Unknown")
            content = start_message.get("content", "")
            task = f"Continue the conversation where {sender_name} said: '{content}'"
        else:
            task = "Continue the conversation based on the history provided in your system messages."
        
        # Run the group chat with only a task parameter, no messages parameter
        result = loop.run_until_complete(group_chat.run(task=task))
        
        # Extract the response messages from the result
        current_time = datetime.datetime.now()
        time_delta = 0
        
        for message in result.messages:
            # Only add messages from AI agents that are not the orchestrator
            if message.source in ai_agent_ids and message.source != orchestrator_agent.name:
                # Convert the agent ID back to the display name
                display_name = all_id_to_name_map[message.source]
                
                # Find the matching participant for this AI agent
                sender_uid = None
                for participant in participants:
                    if participant.get("name") == display_name and participant.get("type") == "ai":
                        sender_uid = participant.get("uid")
                        break
                
                if sender_uid:
                    # Clean the message content to remove name prefixes if present
                    content = message.content
                    if content.lower().startswith(display_name.lower() + ":"):
                        content = content[len(display_name) + 1:].strip()
                    if content.lower().startswith(display_name.lower() + " :"):
                        content = content[len(display_name) + 2:].strip()
                        
                    # Add AI responses to the messages list in the Firestore format
                    time_delta += 1
                    message_timestamp = current_time + datetime.timedelta(seconds=time_delta)
                    
                    last_k_messages.append({
                        "id": message_timestamp.strftime("%Y%m%d%H%M%S"),
                        "sender": {
                            "uid": sender_uid,
                            "type": "ai",
                            "name": display_name
                        },
                        "content": content,
                        "isProcessed": True
                    })
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
    
    # Process messages
    updated_messages = process_group_chat_messages(messages, participants)
    
    # Print updated messages
    print("Updated Messages:")
    for message in updated_messages:
        print(f"{message['sender']['name']}: {message['content']}")