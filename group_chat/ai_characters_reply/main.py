import firebase_admin
from firebase_admin import credentials, firestore
from firebase_functions.firestore_fn import (
    on_document_updated,
    Event,
    Change,
    DocumentSnapshot
)
import os
import logging
from datetime import datetime
import uuid
from orchestrator import ChatOrchestrator
from utils import setup_environment

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ai_characters_cloud_function')

# Initialize Firebase Admin SDK
# No need to explicitly initialize with credentials in deployed Cloud Functions
firebase_admin.initialize_app()

@on_document_updated(document="groupChats/{groupChatId}")
def add_ai_message_on_update(event: Event[Change[DocumentSnapshot]]) -> None:
    """
    Cloud Function that triggers when a document in the groupChats collection is updated
    Specifically responds when new messages are added
    
    Args:
        event: The event payload containing before and after snapshots
    """
    try:
        # Get the data before and after the update
        before_data = event.data.before.to_dict() if event.data.before else {}
        after_data = event.data.after.to_dict() if event.data.after else {}
        group_chat_id = event.params["groupChatId"]
        
        logger.info(f"Processing update for group chat: {group_chat_id}")
        
        # Extract messages from before and after
        before_messages = before_data.get("messages", [])
        after_messages = after_data.get("messages", [])
        
        # If no new messages were added, exit early
        if len(after_messages) <= len(before_messages):
            logger.info('No new messages detected, exiting early.')
            return
            
        # Get the last processed message ID
        last_processed_id = before_data.get("lastProcessedMessageId", "")
        
        # Find new messages that need processing
        new_messages = []
        if last_processed_id:
            # Find where the last processed message is in the list
            last_idx = next((i for i, m in enumerate(after_messages) if m.get('id') == last_processed_id), -1)
            if last_idx >= 0:
                new_messages = after_messages[last_idx + 1:]
            else:
                # If the last processed message is not found, process all messages
                # This shouldn't happen in normal operation
                new_messages = after_messages
        else:
            new_messages = after_messages
            
        # Only continue if there are new messages and the last message is from a user
        if not new_messages:
            logger.info('No new messages to process, exiting.')
            return
            
        last_message = new_messages[-1]
        if not last_message or last_message.get("sender", {}).get("type") != "user":
            logger.info('Last message is not from a user, exiting.')
            return
            
        logger.info(f"Processing {len(new_messages)} new messages in chat {group_chat_id}")
        
        # Get AI participants from the group chat
        ai_participants = [p for p in after_data.get("participants", []) if p.get("type") == "ai"]
        
        if not ai_participants:
            logger.info('No AI participants in this chat')
            return
            
        # Get the last 5 messages for context
        last_five_messages = after_messages[-5:] if len(after_messages) > 5 else after_messages
        
        # Generate AI responses using the orchestrator
        try:
            # Set up environment variables if needed
            setup_environment()
            
            # Initialize the orchestrator with the AI participants
            orchestrator = ChatOrchestrator(ai_participants)
            
            # Generate responses from AI characters
            ai_responses = orchestrator.generate_responses(last_five_messages)
            
            if not ai_responses:
                logger.info('No AI responses generated')
                return
                
            # Append AI responses to the messages
            updated_messages = after_messages + ai_responses
            
            # Update the document with new messages and last processed message ID
            db = firestore.client()
            db.collection("groupChats").document(group_chat_id).update({
                "messages": updated_messages,
                "lastProcessedMessageId": ai_responses[-1]["id"],
                "updatedAt": firestore.SERVER_TIMESTAMP
            })
            
            logger.info(f"Added {len(ai_responses)} AI responses to chat {group_chat_id}")
            
        except Exception as e:
            logger.error(f"Error generating AI responses: {str(e)}")
            raise
            
    except Exception as e:
        logger.error(f"Error processing document update: {str(e)}")
        raise