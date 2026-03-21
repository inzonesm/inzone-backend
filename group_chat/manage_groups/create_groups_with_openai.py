import firebase_admin
from firebase_admin import credentials, firestore
import datetime
from datetime import timedelta
import time
import random
import os
import json
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Firebase
try:
    # If already initialized, use the existing app
    db = firestore.client()
except ValueError:
    # Otherwise initialize Firebase
    cred = credentials.Certificate("/Users/aryan/Inzone/agent_dashboard/key.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()

# Initialize OpenAI client
openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def fetch_popular_characters(limit=50):
    """
    Fetch popular characters from Firestore.
    
    Args:
        limit (int): Maximum number of characters to fetch
        
    Returns:
        List of character documents with their IDs
    """
    characters_ref = db.collection("popularCharacters")
    characters = characters_ref.limit(limit).get()
    
    result = []
    for character in characters:
        character_data = character.to_dict()
        character_data["uid"] = character.id
        result.append(character_data)
    
    print(f"Fetched {len(result)} popular characters")
    return result

def fetch_existing_group_chats(limit=40):
    """
    Fetch existing group chats to avoid creating similar ones.
    
    Args:
        limit (int): Maximum number of group chats to fetch
        
    Returns:
        List of group chat documents
    """
    group_chats_ref = db.collection("groupChats")
    group_chats = group_chats_ref.limit(limit).get()
    
    result = []
    for chat in group_chats:
        chat_data = chat.to_dict()
        chat_data["id"] = chat.id
        result.append(chat_data)
    
    print(f"Fetched {len(result)} existing group chats")
    return result

def group_chat_exists(name):
    """
    Check if a group chat with the given name already exists.
    
    Args:
        name (str): Name of the group chat
        
    Returns:
        bool: True if exists, False otherwise
    """
    group_chats_ref = db.collection("groupChats")
    query = group_chats_ref.where("name", "==", name).limit(1)
    results = query.get()
    
    return len(results) > 0

def categorize_characters_with_openai(characters, existing_group_chats):
    """
    Use OpenAI to categorize characters into interesting group chat combinations.
    
    Args:
        characters (list): List of character documents
        existing_group_chats (list): List of existing group chat documents
        
    Returns:
        List of group chat recommendations with participants and themes
    """
    if not characters:
        return []
        
    # Extract relevant character information
    character_info = []
    for char in characters:
        if not all(key in char for key in ["name", "personality"]):
            continue
            
        info = {
            "uid": char["uid"],
            "name": char["name"],
            "personality": char.get("personality", ""),
            "profile_picture_url": char.get("profile_picture_url", "")
        }
        character_info.append(info)
    
    # Extract names of existing group chats to avoid duplication
    existing_chat_names = [chat.get("name", "") for chat in existing_group_chats]
    existing_chat_participants = []
    for chat in existing_group_chats:
        participants = [p.get("name", "") for p in chat.get("participants", []) if p.get("type") == "ai"]
        if participants:
            existing_chat_participants.append(participants)
    
    # Prepare data for OpenAI API
    prompt = f"""
    I have a list of AI characters with their names and personalities. I want to create engaging group chats by combining 
    characters that would have interesting interactions. Each group chat should contain around 10 characters.
    
    Here are the characters:
    {json.dumps(character_info, indent=2)}
    
    Here are existing group chat names to avoid duplicating:
    {json.dumps(existing_chat_names, indent=2)}
    
    Here are existing combinations of AI participants in group chats to avoid duplicating:
    {json.dumps(existing_chat_participants, indent=2)}
    
    Please suggest 5-10 new group chat combinations. For each group chat, provide:
    1. A catchy name for the group chat
    2. A list of characters (use their UIDs to identify them)
    3. A theme or category (sports, entertainment, technology, lifestyle, etc.)
    4. A brief description for the group chat
    5. A recommended price tier (0 for free, or 10-30 for premium)
    
    Format the response as a valid JSON array where each object has these fields: 
    name, participants (array of UIDs), category, description, price.
    """
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": "You are a creative assistant that helps create engaging group chat combinations based on character personalities."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=32000
        )
        
        # Parse the JSON response
        content = response.choices[0].message.content
        # Extract JSON from the response if it's wrapped in markdown or other text
        json_start = content.find("[")
        json_end = content.rfind("]") + 1
        
        if json_start >= 0 and json_end > json_start:
            json_content = content[json_start:json_end]
            group_suggestions = json.loads(json_content)
            return group_suggestions
        else:
            print("Error: Could not parse JSON response from OpenAI")
            return []
            
    except Exception as e:
        print(f"Error with OpenAI API: {e}")
        # Fallback to a default group if OpenAI API fails
        return []

def create_group_chats_from_suggestions(group_suggestions, characters, user_uid="qL73zIfq9OQP5WIHz6oxSRSesgx1", user_name="aryan527"):
    """
    Create group chats based on OpenAI suggestions
    
    Args:
        group_suggestions (list): List of group chat suggestions from OpenAI
        characters (list): List of all characters to reference
        user_uid (str): UID of the user to add to all chats
        user_name (str): Name of the user to add to all chats
    """
    # Create lookup for characters by uid
    characters_by_uid = {char["uid"]: char for char in characters}
    
    for suggestion in group_suggestions:
        group_name = suggestion.get("name")
        
        # Skip if missing required fields
        if not all(key in suggestion for key in ["name", "participants", "category", "description"]):
            print(f"Skipping incomplete suggestion: {suggestion}")
            continue
            
        # Skip if this group chat exists
        if group_chat_exists(group_name):
            print(f"Group chat '{group_name}' already exists. Skipping...")
            continue
            
        # Create participants list
        participants = [
            {"uid": user_uid, "type": "user", "name": user_name}
        ]
        
        # Add AI characters
        valid_participants = True
        for char_uid in suggestion.get("participants", []):
            if char_uid not in characters_by_uid:
                print(f"Character with UID {char_uid} not found. Skipping this group chat.")
                valid_participants = False
                break
                
            char = characters_by_uid[char_uid]
            participants.append({
                "uid": char_uid,
                "type": "ai",
                "name": char.get("name", "Unknown"),
                "personality": char.get("personality", "")
            })
            
        if not valid_participants:
            continue
            
        # Ensure we have enough participants
        if len(participants) < 3:  # 1 user + at least 2 AI characters
            print(f"Not enough valid participants for group '{group_name}'. Skipping...")
            continue
            
        # Create initial messages
        current_time = datetime.datetime.now()
        initial_messages = [
            {
                "id": current_time.strftime("%Y%m%d%H%M%S"),
                "sender": {"uid": user_uid, "type": "user", "name": user_name},
                "content": f"Hi everyone! Welcome to {group_name}! I'm excited to chat with all of you!",
                "isProcessed": True
            }
        ]
        
        # Add responses from each AI character
        ai_participants = [p for p in participants if p["type"] == "ai"]
        for idx, participant in enumerate(ai_participants):
            # Generate a personalized greeting based on character personality
            char_uid = participant["uid"]
            char = characters_by_uid[char_uid]
            
            greeting = f"Hello! I'm {participant['name']}. "
            if "personality" in char:
                greeting += f"Excited to be here with everyone! {random.choice(['Looking forward to our conversations!', 'Happy to join this group!', 'Great to meet you all!'])}"
            
            initial_messages.append({
                "id": (current_time + timedelta(seconds=idx+1)).strftime("%Y%m%d%H%M%S"),
                "sender": {
                    "uid": char_uid,
                    "type": "ai",
                    "name": char.get("name", "Unknown")
                },
                "content": greeting,
                "isProcessed": True
            })
        
        # Set price tier
        entry_fee = suggestion.get("price", 0)
        if entry_fee <= 0:
            access_tier = "Free"
            chat_type = "free"
        else:
            access_tier = "Premium Monthly"
            chat_type = "premium"
        
        # Get image URL from first character or default
        first_ai = next((p for p in participants if p["type"] == "ai"), None)
        image_url = "https://firebasestorage.googleapis.com/v0/b/inzone-f93e4.appspot.com/o/default_group.png?alt=media"
        if first_ai and first_ai["uid"] in characters_by_uid:
            image_url = characters_by_uid[first_ai["uid"]].get("profile_picture_url", image_url)
        
        # Create group chat data
        group_chat_data = {
            "name": group_name,
            "accessTier": access_tier,
            "entryFee": entry_fee,
            "description": suggestion.get("description", f"Chat with {', '.join([p['name'] for p in participants if p['type'] == 'ai'])}"),
            "imageUrl": image_url,
            "groupChatType": chat_type,
            "groupChatStatus": "active",
            "groupChatCategory": suggestion.get("category", "entertainment"),
            "createdAt": current_time,
            "updatedAt": current_time,
            "participants": participants,
            "messages": initial_messages,
            "lastProcessedMessageId": initial_messages[-1]["id"] if initial_messages else None
        }
        
        # Add to Firestore
        doc_id = f"group_chat_{current_time.strftime('%Y%m%d%H%M%S')}"
        group_chat_ref = db.collection("groupChats").document(doc_id)
        group_chat_ref.set(group_chat_data)
        
        print(f"Created group chat: {group_name} with {len(participants)-1} characters (ID: {doc_id})")
        # Sleep to ensure unique timestamps
        time.sleep(1)

def main():
    """Main function to create group chats using OpenAI recommendations"""
    print("Fetching popular characters...")
    characters = fetch_popular_characters(limit=50)
    
    if not characters:
        print("No characters found in the popularCharacters collection.")
        return
    
    print("Fetching existing group chats...")
    existing_group_chats = fetch_existing_group_chats(limit=20)
    
    print("Generating group chat suggestions with OpenAI...")
    group_suggestions = categorize_characters_with_openai(characters, existing_group_chats)
    
    if not group_suggestions:
        print("Could not generate group chat suggestions. Please check your OpenAI API key.")
        return
        
    print(f"Generated {len(group_suggestions)} group chat suggestions.")
    print("Creating group chats...")
    create_group_chats_from_suggestions(group_suggestions, characters)
    print("Done!")

if __name__ == "__main__":
    main()