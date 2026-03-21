import firebase_admin
from firebase_admin import credentials, firestore
import datetime
import time

# Initialize Firebase
try:
    # If already initialized, use the existing app
    db = firestore.client()
except ValueError:
    # Otherwise initialize Firebase
    cred = credentials.Certificate("/Users/aryan/Inzone/agent_dashboard/key.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()

def fetch_all_group_chats(limit=100):
    """
    Fetch all group chats from Firestore.
    
    Args:
        limit (int): Maximum number of group chats to fetch
        
    Returns:
        List of tuples containing (document_id, group_chat_data)
    """
    group_chats_ref = db.collection("groupChats")
    group_chats = group_chats_ref.limit(limit).get()
    
    result = []
    for chat in group_chats:
        result.append((chat.id, chat.to_dict()))
    
    print(f"Fetched {len(result)} group chats")
    return result

def get_character_personality(uid):
    """
    Get personality information for a character from popularCharacters collection.
    
    Args:
        uid (str): Character UID
        
    Returns:
        str: Personality description or empty string if not found
    """
    character_ref = db.collection("popularCharacters").document(uid)
    character_doc = character_ref.get()
    
    if character_doc.exists:
        character_data = character_doc.to_dict()
        return character_data.get("personality", "")
    
    return ""

def update_group_chat_personalities():
    """
    Check and update personality fields for AI characters in group chats.
    """
    group_chats = fetch_all_group_chats()
    updates_count = 0
    characters_updated = 0
    
    for doc_id, chat_data in group_chats:
        participants = chat_data.get("participants", [])
        chat_updated = False
        
        for i, participant in enumerate(participants):
            # Only process AI participants
            if participant.get("type") == "ai":
                # Check if personality field is missing or empty
                if "personality" not in participant or not participant["personality"]:
                    uid = participant.get("uid")
                    if not uid:
                        print(f"Warning: AI participant without UID in group chat {doc_id}")
                        continue
                        
                    personality = get_character_personality(uid)
                    if personality:
                        participants[i]["personality"] = personality
                        chat_updated = True
                        characters_updated += 1
                        print(f"Added personality for {participant.get('name', 'Unknown')} in group chat {doc_id}")
        
        # Only update the document if changes were made
        if chat_updated:
            chat_ref = db.collection("groupChats").document(doc_id)
            
            # Update only the participants field
            chat_ref.update({
                "participants": participants,
                "updatedAt": datetime.datetime.now()
            })
            
            updates_count += 1
            # Add small delay to prevent overwhelming the database
            time.sleep(0.2)
    
    print(f"Updated {updates_count} group chats, added personalities for {characters_updated} AI characters")

def main():
    """Main function to update personality fields in group chats."""
    print("Starting update of personality fields for AI characters in group chats...")
    update_group_chat_personalities()
    print("Update completed!")

if __name__ == "__main__":
    main()