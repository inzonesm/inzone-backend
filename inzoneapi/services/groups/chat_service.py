# services/groups/chat_service.py
from flask import jsonify
from google.cloud import firestore
from dependencies import db
from services.groups.recommendation_service import GroupChatRecommendationService
import logging

logger = logging.getLogger(__name__)


class GroupChatService:
    """Service for group chat operations"""

    @staticmethod
    def add_participant(data: dict) -> tuple:
        """
        Add a participant to a group chat

        Args:
            data: Dictionary containing groupchat_id, user_id, username

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            groupchat_id = data.get('groupchat_id')
            user_id = data.get('user_id')
            username = data.get('username')

            if not all([groupchat_id, user_id, username]):
                return jsonify({"error": "Missing required fields"}), 400

            groupchat_ref = db.collection('groupChats').document(groupchat_id)
            groupchat = groupchat_ref.get()

            if not groupchat.exists:
                return jsonify({"error": "Group chat not found"}), 404

            groupchat_data = groupchat.to_dict()
            if user_id in groupchat_data.get('user_ids', []):
                return jsonify({"error": "User already in the group chat"}), 400

            groupchat_ref.update({
                'user_ids': firestore.ArrayUnion([user_id]),
                'usernames': firestore.ArrayUnion([username])
            })

            return jsonify({"message": "Participant added successfully"}), 200

        except Exception as ex:
            logger.error("Error adding participant: %s", ex)
            return jsonify({"error": "Failed to add participant"}), 500

    @staticmethod
    def delete_participant(data: dict) -> tuple:
        """
        Remove a participant from a group chat

        Args:
            data: Dictionary containing groupchat_id, user_id, username

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            groupchat_id = data.get('groupchat_id')
            user_id = data.get('user_id')
            username = data.get('username')

            if not all([groupchat_id, user_id, username]):
                return jsonify({"error": "Missing required fields"}), 400

            groupchat_ref = db.collection('groupChats').document(groupchat_id)
            groupchat = groupchat_ref.get()

            if not groupchat.exists:
                return jsonify({"error": "Group chat not found"}), 404

            groupchat_data = groupchat.to_dict()
            if user_id not in groupchat_data.get('user_ids', []):
                return jsonify({"error": "User not in the group chat"}), 400

            groupchat_ref.update({
                'user_ids': firestore.ArrayRemove([user_id]),
                'usernames': firestore.ArrayRemove([username])
            })

            return jsonify({"message": "Participant removed successfully"}), 200

        except Exception as ex:
            logger.error("Error deleting participant: %s", ex)
            return jsonify({"error": "Failed to delete participant"}), 500

    @staticmethod
    def create_groupchat(data: dict) -> tuple:
        """
        Create a new group chat

        Args:
            data: Dictionary containing groupchat_name, bio, creator_id, creator_username, GroupchatDocId

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            groupchat_name = data.get('groupchat_name')
            bio = data.get('bio')
            creator_id = data.get('creator_id')
            creator_username = data.get('creator_username')
            groupchat_doc_id = data.get('GroupchatDocId')

            if not all([groupchat_name, creator_id, creator_username, groupchat_doc_id]):
                return jsonify({"error": "Missing required fields"}), 400

            # Auto-categorize the group chat based on name and bio
            master_categories = GroupChatRecommendationService.categorize_groupchat(
                groupchat_name=groupchat_name,
                bio=bio
            )

            new_groupchat = {
                'groupchat_name': groupchat_name,
                'bio': bio,
                'user_ids': [creator_id],
                'usernames': [creator_username],
                'ai_usernames': [],
                'messages': [],
                'date_created': firestore.SERVER_TIMESTAMP,
                'groupchat_doc_id': groupchat_doc_id,
                'masterCategories': master_categories  # Add categorization
            }

            db.collection('groupChats').document(groupchat_doc_id).set(new_groupchat)

            # Sync with Gorse (placeholder for future integration)
            GroupChatRecommendationService.sync_groupchat_to_gorse(
                groupchat_id=groupchat_doc_id,
                groupchat_data=new_groupchat
            )

            logger.info(f"Created group chat '{groupchat_name}' with categories: {master_categories}")

            return jsonify({
                "message": "Group chat created successfully",
                "groupchat_id": groupchat_doc_id,
                "masterCategories": master_categories
            }), 201

        except Exception as ex:
            logger.error("Error creating group chat: %s", ex)
            return jsonify({"error": "Failed to create group chat"}), 500

    @staticmethod
    def add_ai_character(data: dict) -> tuple:
        """
        Add an AI character to a group chat

        Args:
            data: Dictionary containing groupchat_id, ai_username

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            groupchat_id = data.get('groupchat_id')
            ai_username = data.get('ai_username')

            if not all([groupchat_id, ai_username]):
                return jsonify({"error": "Missing required fields"}), 400

            groupchat_ref = db.collection('groupChats').document(groupchat_id)
            groupchat = groupchat_ref.get()

            if not groupchat.exists:
                return jsonify({"error": "Group chat not found"}), 404

            groupchat_ref.update({
                'ai_usernames': firestore.ArrayUnion([ai_username])
            })

            return jsonify({"message": "AI character added successfully"}), 200

        except Exception as ex:
            logger.error("Error adding AI character: %s", ex)
            return jsonify({"error": "Failed to add AI character"}), 500

    @staticmethod
    def delete_ai_character(data: dict) -> tuple:
        """
        Remove an AI character from a group chat

        Args:
            data: Dictionary containing groupchat_id, ai_username

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            groupchat_id = data.get('groupchat_id')
            ai_username = data.get('ai_username')

            if not all([groupchat_id, ai_username]):
                return jsonify({"error": "Missing required fields"}), 400

            groupchat_ref = db.collection('groupChats').document(groupchat_id)
            groupchat = groupchat_ref.get()

            if not groupchat.exists:
                return jsonify({"error": "Group chat not found"}), 404

            groupchat_data = groupchat.to_dict()
            if ai_username not in groupchat_data.get('ai_usernames', []):
                return jsonify({"error": "AI character not in the group chat"}), 400

            groupchat_ref.update({
                'ai_usernames': firestore.ArrayRemove([ai_username])
            })

            return jsonify({"message": "AI character removed successfully"}), 200

        except Exception as ex:
            logger.error("Error deleting AI character: %s", ex)
            return jsonify({"error": "Failed to delete AI character"}), 500
