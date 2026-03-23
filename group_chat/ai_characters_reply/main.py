import firebase_admin
from firebase_admin import credentials, firestore
import json
import os
import logging
from datetime import datetime
import uuid
from orchestrator import ChatOrchestrator
from utils import setup_environment

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ai_characters_cloud_function')

firebase_admin.initialize_app()

def add_ai_message_on_update(data, context):
    """
    Cloud Function triggered when a Firestore document in groupChats is updated.
    Uses the legacy (data, context) signature for 1st-gen Cloud Functions.
    """
    try:
        group_chat_id = _extract_group_chat_id_from_context(context)
        if not group_chat_id:
            payload = _normalize_event_payload(data)
            name_path = payload.get("value", {}).get("name", "")
            if name_path:
                group_chat_id = name_path.split("/")[-1]

        if not group_chat_id:
            logger.info("Could not determine group chat ID from event context/payload.")
            return

        logger.info(f"Processing update for group chat: {group_chat_id}")

        # Use the Firestore Admin SDK to get the full document (avoids dealing with raw field encoding)
        db = firestore.client()
        doc_ref = db.collection("groupChats").document(group_chat_id)
        doc = doc_ref.get()

        if not doc.exists:
            logger.info("Document does not exist, exiting.")
            return

        after_data = doc.to_dict()
        after_messages = after_data.get("messages", [])

        if not after_messages:
            logger.info("No messages in chat, exiting.")
            return

        last_message = after_messages[-1]
        last_message_id = last_message.get("id", "")
        sender_type = (last_message.get("sender", {}).get("type") or "").lower()

        if sender_type != "user":
            logger.info(f"Last message sender type is '{sender_type or 'unknown'}', exiting.")
            return

        last_processed_user_message_id = after_data.get("lastProcessedUserMessageId", "")
        if last_message_id and last_message_id == last_processed_user_message_id:
            logger.info(
                f"Latest user message already processed (id={last_message_id}), exiting."
            )
            return

        logger.info(
            f"Processing latest user message id={last_message_id or 'missing-id'} in chat {group_chat_id}"
        )

        ai_participants = [
            p for p in after_data.get("participants", []) if p.get("type") == "ai"
        ]

        if not ai_participants:
            participant_types = [p.get("type", "unknown") for p in after_data.get("participants", [])]
            logger.info(f"No AI participants in this chat. participant_types={participant_types}")
            return

        context_window_size = 12
        recent_messages = (
            after_messages[-context_window_size:]
            if len(after_messages) > context_window_size
            else after_messages
        )

        try:
            setup_environment()
            orchestrator = ChatOrchestrator(ai_participants)
            ai_responses = orchestrator.generate_responses(recent_messages)

            if not ai_responses:
                logger.info(
                    f"No AI responses generated for latest user message id={last_message_id or 'missing-id'}."
                )
                return

            updated_messages = after_messages + ai_responses

            doc_ref.update({
                "messages": updated_messages,
                "lastProcessedMessageId": ai_responses[-1]["id"],
                "lastProcessedUserMessageId": last_message_id,
                "updatedAt": firestore.SERVER_TIMESTAMP
            })

            logger.info(f"Added {len(ai_responses)} AI responses to chat {group_chat_id}")

        except Exception as e:
            logger.error(f"Error generating AI responses: {str(e)}")
            raise

    except Exception as e:
        logger.error(f"Error processing document update: {str(e)}")
        raise


def _normalize_event_payload(data):
    if isinstance(data, dict):
        return data

    if isinstance(data, (bytes, bytearray)):
        text = data.decode("utf-8")
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("Decoded event payload is not a JSON object")

    if isinstance(data, str):
        parsed = json.loads(data)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("Parsed event payload is not a JSON object")

    raise TypeError(f"Unsupported event payload type: {type(data).__name__}")


def _extract_group_chat_id_from_context(context):
    if context is None:
        return ""

    resource = getattr(context, "resource", "")
    if not resource:
        return ""

    if "/documents/" in resource:
        doc_path = resource.split("/documents/", 1)[1]
        parts = doc_path.split("/")
        if len(parts) >= 2 and parts[0] == "groupChats":
            return parts[1]

    parts = resource.split("/")
    return parts[-1] if parts else ""