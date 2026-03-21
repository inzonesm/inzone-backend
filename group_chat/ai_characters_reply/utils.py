import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ai_characters')

def setup_environment():
    """
    Set up environment variables and configuration
    Returns True if setup was successful, False otherwise
    """
    required_vars = ['OPENAI_API_KEY']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.info("Please create a .env file with the required variables")
        return False
        
    logger.info("Environment setup completed successfully")
    return True

def extract_conversation_context(messages: List[Dict[str, Any]], max_messages: int = 5) -> str:
    """
    Extract the conversation context from a list of messages
    
    Args:
        messages: List of message objects
        max_messages: Maximum number of messages to include
    
    Returns:
        A formatted string with the conversation context
    """
    # Get the last N messages
    recent_messages = messages[-max_messages:] if len(messages) > max_messages else messages
    
    # Format each message
    formatted_messages = []
    for msg in recent_messages:
        sender_name = msg.get("sender", {}).get("name", "Unknown")
        sender_type = msg.get("sender", {}).get("type", "unknown")
        content = msg.get("content", "")
        timestamp = msg.get("id", "")[:14]  # Extract timestamp part from ID if available
        
        # Try to convert timestamp to readable format
        try:
            date_obj = datetime.strptime(timestamp, "%Y%m%d%H%M%S")
            time_str = date_obj.strftime("%H:%M:%S")
        except:
            time_str = ""
            
        # Format message with sender type indicator
        formatted_messages.append(f"[{time_str}] {sender_name} ({sender_type}): {content}")
    
    return "\n".join(formatted_messages)

def create_character_prompt(character_name: str, character_type: str = None) -> str:
    """
    Create a prompt for an AI character based on their name and type
    
    Args:
        character_name: The name of the AI character
        character_type: Optional type/category of the character
        
    Returns:
        A system prompt for the character
    """
    base_prompt = f"""You are {character_name}. Respond authentically as {character_name} would, maintaining your unique personality, knowledge, speech patterns, and mannerisms.
    
Keep responses conversational, engaging, and appropriate for a group chat setting.
    
If you're directly addressed or if the conversation is relevant to your expertise or background, respond naturally.
Otherwise, you can choose to simply observe without responding if that's more appropriate.
"""
    
    # Add character-specific guidance based on name or type
    if "Messi" in character_name:
        base_prompt += """
As Lionel Messi, you are humble, soft-spoken but confident. You prefer to let your skills do the talking.
Use occasional Spanish phrases like "gracias" or "vamos". When discussing football, you're passionate but modest about your own achievements.
You might refer to your experiences at FC Barcelona, PSG, and Inter Miami, as well as with Argentina's national team.
"""
    elif "Potter" in character_name or "Hermione" in character_name:
        base_prompt += """
As a character from the Harry Potter universe, you're familiar with the wizarding world, spells, and magical concepts.
You might use phrases like "Merlin's beard" or reference magical concepts naturally.
"""
    elif character_type == "sports":
        base_prompt += """
As a sports figure, you're knowledgeable about your sport and competitive achievements.
You might discuss training, competition experiences, and your approach to athletics.
"""
    elif character_type == "entertainment":
        base_prompt += """
As an entertainment figure, you're familiar with your works, projects, and public persona.
You might reference your work, experiences, and creative process.
"""
        
    return base_prompt

def log_agent_activity(group_chat_id: str, activity_type: str, details: Dict[str, Any]) -> None:
    """
    Log agent activity for monitoring and debugging
    
    Args:
        group_chat_id: The ID of the group chat
        activity_type: Type of activity (e.g., "response_generation", "error")
        details: Additional details about the activity
    """
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "group_chat_id": group_chat_id,
        "activity_type": activity_type,
        "details": details
    }
    
    logger.info(f"Agent activity: {json.dumps(log_entry)}")
    
    # Could also write to a database or file for persistent logging
    
def get_character_persona(character_name: str) -> Dict[str, Any]:
    """
    Get persona information for a character based on their name
    
    Args:
        character_name: The name of the character
        
    Returns:
        A dictionary with persona information
    """
    # This could be enhanced to pull from a database or external source
    personas = {
        "Lionel Messi": {
            "background": "Argentine professional footballer, widely regarded as one of the greatest players of all time",
            "traits": ["humble", "reserved", "focused", "competitive", "family-oriented"],
            "style": "Speaks softly with occasional Spanish phrases, modest about achievements",
            "knowledge": ["football tactics", "FC Barcelona", "PSG", "Inter Miami", "Argentina national team", "World Cup"]
        },
        "Taylor Swift": {
            "background": "American singer-songwriter known for narrative songs about her personal life",
            "traits": ["creative", "articulate", "thoughtful", "business-savvy", "cat-lover"],
            "style": "Speaks warmly and thoughtfully, often references music, songwriting or her fans (Swifties)",
            "knowledge": ["music industry", "songwriting", "her albums and songs", "cats"]
        },
        "Harry Potter": {
            "background": "Wizard who survived the Killing Curse as a baby, attended Hogwarts",
            "traits": ["brave", "loyal", "sometimes impulsive", "modest", "determined"],
            "style": "Casual, straightforward speech with wizarding expressions",
            "knowledge": ["magic spells", "Hogwarts", "quidditch", "defense against the dark arts"]
        },
        "Hermione Granger": {
            "background": "Exceptionally intelligent witch, Hogwarts student, friend of Harry Potter",
            "traits": ["brilliant", "logical", "detail-oriented", "principled", "studious"],
            "style": "Articulate, often educational, occasionally impatient with illogical thinking",
            "knowledge": ["magical theory", "Hogwarts", "magical creatures", "history of magic", "academic subjects"]
        }
    }
    
    # Return default persona if character not found
    return personas.get(character_name, {
        "background": f"AI version of {character_name}",
        "traits": ["friendly", "conversational"],
        "style": "Natural, conversational",
        "knowledge": ["general topics"]
    })