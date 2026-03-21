import firebase_admin
from firebase_admin import credentials, firestore
import datetime
import argparse
import sys

def initialize_firebase():
    """Initialize Firebase connection"""
    try:
        # Try to get existing app
        firebase_admin.get_app()
    except ValueError:
        # Initialize with credentials if not already initialized
        cred = credentials.Certificate("/Users/aryan/Inzone/agent_dashboard/key.json")
        firebase_admin.initialize_app(cred)
    
    return firestore.client()

def get_group_chat(db, group_chat_id):
    """Get a group chat by ID"""
    group_chat_ref = db.collection("groupChats").document(group_chat_id)
    group_chat = group_chat_ref.get()
    
    if not group_chat.exists:
        print(f"Error: Group chat with ID {group_chat_id} does not exist.")
        return None
    
    return group_chat.to_dict(), group_chat_ref

def list_group_chats(db, limit=10):
    """List available group chats"""
    group_chats = db.collection("groupChats").limit(limit).get()
    
    if not group_chats:
        print("No group chats found.")
        return
    
    print("\nAvailable Group Chats:")
    print("-" * 50)
    for i, chat in enumerate(group_chats, 1):
        chat_data = chat.to_dict()
        print(f"{i}. ID: {chat.id}")
        print(f"   Name: {chat_data.get('name', 'Unnamed')}")
        print(f"   Participants: {len(chat_data.get('participants', []))}")
        print(f"   Messages: {len(chat_data.get('messages', []))}")
        print("-" * 50)
    
    return group_chats

def add_user_message(db, group_chat_id, user_id, user_name, message_content):
    """Add a user message to a group chat"""
    # Get the group chat
    chat_data, chat_ref = get_group_chat(db, group_chat_id)
    if not chat_data:
        return False
    
    # Verify user is in participants
    user_in_chat = False
    for participant in chat_data.get('participants', []):
        if participant.get('uid') == user_id and participant.get('type') == 'user':
            user_in_chat = True
            break
    
    if not user_in_chat:
        print(f"Error: User {user_id} is not a participant in this chat. Adding them first.")
        # Add user to participants
        chat_data['participants'].append({
            "uid": user_id, 
            "type": "user", 
            "name": user_name
        })
    
    # Create a new message
    current_time = datetime.datetime.now()
    new_message = {
        "id": current_time.strftime("%Y%m%d%H%M%S"),
        "sender": {"uid": user_id, "type": "user", "name": user_name},
        "content": message_content,
        "isProcessed": False
    }
    
    # Add message to the chat
    if 'messages' not in chat_data or not chat_data['messages']:
        chat_data['messages'] = [new_message]
    else:
        chat_data['messages'].append(new_message)
    
    # Update last processed message ID
    chat_data['lastProcessedMessageId'] = new_message['id']
    
    # Update the 'updatedAt' timestamp
    chat_data['updatedAt'] = current_time
    
    # Update the document in Firestore
    chat_ref.update({
        'messages': chat_data['messages'],
        'lastProcessedMessageId': chat_data['lastProcessedMessageId'],
        'updatedAt': chat_data['updatedAt'],
        'participants': chat_data['participants']
    })
    
    print(f"Message added successfully to group chat '{chat_data.get('name')}'")
    return True

def main():
    parser = argparse.ArgumentParser(description='Add a user message to a group chat')
    parser.add_argument('--list', action='store_true', help='List available group chats')
    parser.add_argument('--chat-id', type=str, help='Group chat ID to add the message to')
    parser.add_argument('--user-id', type=str, default="qL73zIfq9OQP5WIHz6oxSRSesgx1", help='User ID (default: aryan527 user ID)')
    parser.add_argument('--user-name', type=str, default="aryan527", help='User name (default: aryan527)')
    parser.add_argument('--message', type=str, help='Message content')
    
    args = parser.parse_args()
    
    # Initialize Firebase
    db = initialize_firebase()
    
    # List group chats if requested
    if args.list:
        list_group_chats(db)
        return
    
    # Check required arguments for adding a message
    if not args.chat_id:
        print("Error: --chat-id is required. Use --list to see available group chats.")
        parser.print_help()
        return
    
    if not args.message:
        print("Error: --message is required.")
        parser.print_help()
        return
    
    # Add the message
    success = add_user_message(db, args.chat_id, args.user_id, args.user_name, args.message)
    if success:
        print("Message added successfully!")
    else:
        print("Failed to add message.")

if __name__ == "__main__":
    main()