import firebase_admin
from firebase_admin import credentials, firestore
import datetime
from datetime import timedelta
import time
import random
import os
import csv
from dotenv import load_dotenv
import openai

# Load environment variables
load_dotenv()

# Initialize OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Initialize Firebase
try:
    # If already initialized, use the existing app
    db = firestore.client()
except ValueError:
    # Otherwise initialize Firebase
    cred = credentials.Certificate("/Users/aryan/Inzone/agent_dashboard/key.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()

def fetch_popular_characters(limit=100):
    """
    Fetch popular characters from Firestore with group information.
    
    Args:
        limit (int): Maximum number of characters to fetch
        
    Returns:
        List of character documents with their IDs and group info
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

def load_character_groups_from_csv(file_path):
    """
    Load character groups from a CSV file.
    
    Args:
        file_path (str): Path to the CSV file
        
    Returns:
        dict: Mapping of character names to their group information
    """
    character_groups = {}
    
    try:
        with open(file_path, mode='r', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            
            # Skip header row
            headers = next(reader)
            
            for row in reader:
                # The format is: Group #, Common Denominator, Name, Description, Greeting
                if len(row) >= 3:
                    try:
                        group_id = int(row[0])
                        group_name = row[1]
                        character_name = row[2]
                        
                        character_groups[character_name] = {
                            "group_id": group_id,
                            "group_name": group_name
                        }
                    except (ValueError, IndexError) as e:
                        # Skip rows that don't have valid data
                        print(f"Warning: Skipping CSV row due to error: {e}, row: {row}")
    except Exception as e:
        print(f"Error reading CSV file {file_path}: {e}")
    
    return character_groups

def group_characters_by_csv_group(characters, character_groups):
    """
    Group characters based on their names into predefined groups from the CSV.
    
    This function uses a mapping of character names to their groups based on the CSV data,
    since the Firestore documents don't directly contain the group information.
    
    Args:
        characters (list): List of character documents
        character_groups (dict): Mapping of character names to their group information
        
    Returns:
        dict: Characters grouped by their assigned groups
    """
    # Group characters according to the mapping
    grouped_characters = {}
    unassigned_characters = []
    
    for character in characters:
        # Skip if missing important fields
        if "name" not in character:
            continue
            
        character_name = character["name"]
        
        if character_name in character_groups:
            group_info = character_groups[character_name]
            group_id = group_info["group_id"]
            
            if group_id not in grouped_characters:
                grouped_characters[group_id] = {
                    "characters": [],
                    "group_name": group_info["group_name"]
                }
                
            grouped_characters[group_id]["characters"].append(character)
        else:
            unassigned_characters.append(character)
    
    print(f"Organized {sum(len(g['characters']) for g in grouped_characters.values())} characters into {len(grouped_characters)} groups")
    print(f"Found {len(unassigned_characters)} characters without group assignments")
    
    return grouped_characters

def generate_group_description(group_name, characters):
    """
    Generate a description for a group chat using OpenAI API.
    
    Args:
        group_name (str): Name of the group
        characters (list): List of characters in the group
        
    Returns:
        str: Generated description
    """
    if not os.getenv("OPENAI_API_KEY"):
        # Fallback if no API key is available
        return f"A dynamic group chat featuring {', '.join([char['name'] for char in characters[:3]])} and others. Join the conversation!"
    
    try:
        character_names = [char["name"] for char in characters]
        character_info = "\n".join([f"{char['name']}: {char.get('Description', '')}" for char in characters])
        
        prompt = f"""
        Create a brief, engaging description (maximum 100 words) for a group chat named "{group_name}" 
        featuring these characters:
        
        {character_info}
        
        Make it conversational, fun, and appealing to fans who would want to join this chat.
        """
        
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.7
        )
        
        description = response.choices[0].message.content.strip()
        return description
    except Exception as e:
        print(f"Error generating description: {e}")
        # Fallback description
        return f"An exclusive chat with {', '.join(character_names[:3])} and more. Join the conversation!"

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

def create_group_chats_from_csv_groups(grouped_characters, user_uid="qL73zIfq9OQP5WIHz6oxSRSesgx1", user_name="aryan527"):
    """
    Create group chats based on the groupings from the CSV data.
    
    Args:
        grouped_characters (dict): Characters grouped by their assigned groups
        user_uid (str): UID of the user to add to all chats
        user_name (str): Name of the user to add to all chats
    """
    for group_id, group_info in grouped_characters.items():
        characters = group_info["characters"]
        group_name = group_info["group_name"]
        
        if len(characters) < 2:
            print(f"Group {group_id} has fewer than 2 characters. Skipping...")
            continue
        
        # Check if group already exists
        if group_chat_exists(group_name):
            print(f"Group chat '{group_name}' already exists. Skipping...")
            continue
        
        # Generate description using OpenAI
        description = generate_group_description(group_name, characters)
        
        # Create participants list
        participants = [
            {"uid": user_uid, "type": "user", "name": user_name}
        ]
        
        for char in characters:
            participants.append({
                "uid": char["uid"],
                "type": "ai",
                "name": char["name"],
                "personality": char.get("Description", "")
            })
        
        # Create initial messages
        current_time = datetime.datetime.now()
        initial_messages = [
            {
                "id": current_time.strftime("%Y%m%d%H%M%S"),
                "sender": {"uid": user_uid, "type": "user", "name": user_name},
                "content": f"Hi everyone! I'm excited to chat with all of you!",
                "isProcessed": True
            }
        ]
        
        # Add responses from each character using their greetings from the CSV
        for idx, char in enumerate(characters):
            greeting = char.get("Greeting", f"Hello! I'm {char['name']}. Nice to meet you!")
            
            initial_messages.append({
                "id": (current_time + timedelta(seconds=idx+1)).strftime("%Y%m%d%H%M%S"),
                "sender": {
                    "uid": char["uid"],
                    "type": "ai",
                    "name": char["name"]
                },
                "content": greeting,
                "isProcessed": True
            })
        
        # Define group category based on group name
        group_category = "entertainment"
        if "tech" in group_name.lower() or "entrepreneur" in group_name.lower():
            group_category = "technology"
        elif "sports" in group_name.lower() or "athlete" in group_name.lower():
            group_category = "sports"
        elif "lifestyle" in group_name.lower() or "fashion" in group_name.lower():
            group_category = "lifestyle"
        
        # Set price tier based on exclusivity/popularity
        entry_fee = random.choice([15, 20, 25, 30])
        access_tier = "Premium Monthly"
        chat_type = "premium"
        
        # Create group chat data
        group_chat_data = {
            "name": group_name,
            "accessTier": access_tier,
            "entryFee": entry_fee,
            "description": description,
            "imageUrl": characters[0].get("profile_picture_url", "https://firebasestorage.googleapis.com/v0/b/inzone-f93e4.appspot.com/o/default_group.png?alt=media"),
            "groupChatType": chat_type,
            "groupChatStatus": "active",
            "groupChatCategory": group_category,
            "createdAt": current_time,
            "updatedAt": current_time,
            "participants": participants,
            "messages": initial_messages,
            "lastProcessedMessageId": initial_messages[-1]["id"] if initial_messages else None
        }
        
        # Add to Firestore
        doc_id = f"group_chat_{group_id}_{current_time.strftime('%Y%m%d%H%M%S')}"
        group_chat_ref = db.collection("groupChats").document(doc_id)
        group_chat_ref.set(group_chat_data)
        
        print(f"Created group chat: {group_name} with {len(characters)} characters (ID: {doc_id})")
        # Sleep to ensure unique timestamps
        time.sleep(1)

def main():
    """Main function to create group chats from popular characters"""
    print("Fetching popular characters...")
    characters = fetch_popular_characters(limit=1000)
    
    if not characters:
        print("No characters found in the popularCharacters collection.")
        return
    
    # Load character groups from CSV
    csv_file_path = os.path.join(os.path.dirname(__file__), "popular_char.csv")
    print(f"Reading character groups from CSV: {csv_file_path}")
    character_groups = load_character_groups_from_csv(csv_file_path)
    
    if not character_groups:
        print("No character groups found in CSV. Please check the CSV file.")
        return
        
    print(f"Loaded {len(character_groups)} character group mappings from CSV")
    
    print("Organizing characters by CSV groups...")
    grouped_characters = group_characters_by_csv_group(characters, character_groups)
    
    print("Creating group chats based on CSV groupings...")
    create_group_chats_from_csv_groups(grouped_characters)
    print("Done!")

if __name__ == "__main__":
    main()