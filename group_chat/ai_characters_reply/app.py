import firebase_admin
from firebase_admin import credentials, firestore
import os
import time
import logging
from datetime import datetime
from dotenv import load_dotenv
from orchestrator import ChatOrchestrator
from utils import setup_environment, log_agent_activity

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ai_characters_reply')

# Load environment variables
load_dotenv()

def initialize_firebase():
    """
    Initialize Firebase with credentials and return the Firestore client
    """
    # Initialize Firebase with credentials
    cred = credentials.Certificate("/Users/aryan/Inzone/agent_dashboard/key.json")
    try:
        firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized successfully")
    except ValueError:
        # App already initialized
        logger.info("Firebase Admin SDK already initialized")
        
    # Return the Firestore client
    return firestore.client()

def listen_for_new_messages(db):
    """
    Sets up a listener for changes in the groupChats collection.
    When a new message is detected, triggers the AI response orchestrator.
    
    Args:
        db: The initialized Firestore client
    """
    logger.info("Setting up listener for groupChats collection")
    group_chats_ref = db.collection("groupChats")
    
    # Track the last processed message IDs for each chat to avoid duplicate processing
    last_processed = {}
    
    def on_snapshot(doc_snapshots, changes, read_time):
        for change in changes:
            if change.type.name in ('MODIFIED', 'ADDED'):
                # Get the updated document
                doc_id = change.document.id
                
                try:
                    # Using the latest Firebase API to get document data
                    group_chat = change.document.to_dict()
                    
                    if not group_chat:
                        logger.warning(f"Document {doc_id} exists but has no data")
                        continue
                        
                    # Log activity for monitoring
                    log_agent_activity(doc_id, "document_update", {
                        "change_type": change.type.name,
                        "timestamp": datetime.now().isoformat()
                    })
                    
                    # Check if we have new messages to process
                    messages = group_chat.get("messages", [])
                    last_processed_id = last_processed.get(doc_id, None)
                    current_last_id = group_chat.get("lastProcessedMessageId")
                    
                    # Skip if no messages or if we've already processed the last message
                    if not messages or (last_processed_id and last_processed_id == current_last_id):
                        continue
                    
                    # Only get messages we haven't processed yet
                    if last_processed_id:
                        # Find where the last processed message is in the list
                        last_idx = next((i for i, m in enumerate(messages) if m.get('id') == last_processed_id), -1)
                        # Get only new messages after the last processed one
                        new_messages = messages[last_idx+1:] if last_idx >= 0 else messages
                    else:
                        new_messages = messages
                    
                    # Only process if there are new messages and the last message is from a user
                    if new_messages and new_messages[-1].get('sender', {}).get('type') == 'user':
                        logger.info(f"Processing new messages in chat {doc_id}")
                        process_new_messages(db, doc_id, group_chat, new_messages)
                        
                    # Update last processed ID
                    if messages:
                        last_processed[doc_id] = messages[-1].get('id')
                        
                except Exception as e:
                    logger.error(f"Error processing document {doc_id}: {e}")
    
    # Watch the collection for changes using the latest Firebase API
    # The event_loop and background options are new in firebase-admin 6.x
    group_chats_watch = group_chats_ref.on_snapshot(
        on_snapshot,
        error_callback=lambda err: logger.error(f"Firestore listen error: {err}")
    )
    
    logger.info("Listener established for groupChats collection")
    
    # Keep the listener running
    try:
        # Block the main thread to keep the script running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        group_chats_watch.unsubscribe()
        logger.info("Listener stopped")

def process_new_messages(db, doc_id, group_chat, new_messages):
    """
    Process new messages in a group chat and generate AI character responses
    
    Args:
        db: The Firestore client
        doc_id: The document ID of the group chat
        group_chat: The group chat data
        new_messages: The new messages to process
    """
    logger.info(f"Processing {len(new_messages)} new messages in chat: {group_chat.get('name')}")
    
    # Get the last 5 messages or all if less than 5
    all_messages = group_chat.get("messages", [])
    last_messages = all_messages[-5:] if len(all_messages) > 5 else all_messages
    
    # Extract AI participants from the group chat
    ai_participants = [p for p in group_chat.get("participants", []) if p.get("type") == "ai"]
    
    if not ai_participants:
        logger.info("No AI participants in this chat")
        return
    
    try:
        # Initialize the orchestrator with the AI participants
        orchestrator = ChatOrchestrator(ai_participants)
        
        # Generate responses from AI characters
        new_ai_messages = orchestrator.generate_responses(last_messages)
        
        if new_ai_messages:
            # Add the new AI messages to the group chat
            update_group_chat_with_ai_responses(db, doc_id, all_messages, new_ai_messages)
    except Exception as e:
        logger.error(f"Error orchestrating AI responses: {e}")
        
def update_group_chat_with_ai_responses(db, doc_id, existing_messages, new_ai_messages):
    """
    Update the group chat document with new AI messages using the latest Firebase API
    
    Args:
        db: The Firestore client
        doc_id: The document ID of the group chat
        existing_messages: The existing messages in the group chat
        new_ai_messages: New AI messages to add
    """
    # Append new messages to existing ones
    updated_messages = existing_messages + new_ai_messages
    
    # Get the ID of the last message
    last_message_id = updated_messages[-1]['id'] if updated_messages else None
    
    try:
        # Using new atomic update operation from firebase-admin 6.x
        db.collection("groupChats").document(doc_id).update({
            "messages": updated_messages,
            "lastProcessedMessageId": last_message_id,
            "updatedAt": firestore.SERVER_TIMESTAMP
        })
        logger.info(f"Added {len(new_ai_messages)} new AI messages to chat {doc_id}")
        
        # Log the successful update
        log_agent_activity(doc_id, "ai_responses_added", {
            "message_count": len(new_ai_messages),
            "character_names": [msg.get("sender", {}).get("name") for msg in new_ai_messages]
        })
    except Exception as e:
        logger.error(f"Error updating group chat: {e}")

if __name__ == "__main__":
    logger.info("Starting AI character response system...")
    
    # Check environment setup
    if not setup_environment():
        logger.error("Environment setup failed. Exiting.")
        exit(1)
        
    # Initialize Firebase and get Firestore client
    db = initialize_firebase()
    
    # Start listening for new messages
    listen_for_new_messages(db)