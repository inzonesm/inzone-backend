# services/ai/user_management_service.py
import logging
from typing import Dict, Any
from flask import jsonify
from dependencies import db
from services.ai.voice_service import AIVoiceService

logger = logging.getLogger(__name__)


class AIUserManagementService:
    """Service for AI user CRUD operations"""

    @staticmethod
    def create_ai_user(data: Dict[str, Any]) -> tuple:
        """Create a new AI user"""
        try:
            if not data:
                return jsonify({
                    "success": False,
                    "error": "AI User data is required",
                    "code": "INVALID_AI_USER_DATA"
                }), 400

            username = data.get("Username")
            if not username:
                return jsonify({
                    "success": False,
                    "error": "Username is required",
                    "code": "MISSING_USERNAME"
                }), 400

            # Check if username already exists
            existing_users = db.collection('aiUsers').where("username", "==", username).stream()
            if any(existing_users):
                return jsonify({
                    "success": False,
                    "error": "Username already exists",
                    "code": "DUPLICATE_USERNAME"
                }), 400

            # Create voice for character
            voice_result, err_msg, code = AIVoiceService.ensure_voice_id_for_character(username)
            voice_id = voice_result["voice_id"] if voice_result else None

            character_data = {
                "name": data.get("Name"),
                "age": data.get("Age"),
                "gender": data.get("Gender"),
                "bio": data.get("Bio"),
                "popularity": bool(data.get("Popularity", False)),
                "followers": [],
                "followers_count": 0,
                "following": [],
                "following_count": 0,
                "personality": data.get("Personality"),
                "posts": [],
                "category": [],
                "conversations": [],
                "username": username,
                "voice_settings": {
                    "voice_id": voice_id,
                    "voice_enabled": True
                } if voice_id else {}
            }

            db.collection('aiUsers').document(username).set(character_data)

            return jsonify({"AiUserId": username}), 200

        except Exception as ex:
            logger.error("Error creating AI User: %s", ex)
            return jsonify({
                "success": False,
                "error": str(ex),
                "code": "CHARACTER_CREATE_ERROR"
            }), 500

    @staticmethod
    def update_ai_user(data: Dict[str, Any]) -> tuple:
        """Update an AI user profile"""
        try:
            username = data.get("username")
            if not username:
                return jsonify({"success": False, "error": "Username is required"}), 400

            update_data = {
                "name": data.get("Name"),
                "bio": data.get("Bio"),
                "username": data.get("UserName")
            }

            # Remove None values
            update_data = {k: v for k, v in update_data.items() if v is not None}

            db.collection('aiUsers').document(username).update(update_data)
            return jsonify({"success": True}), 200

        except Exception as ex:
            logger.error("Error updating profile: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    @staticmethod
    def get_ai_user(username: str) -> tuple:
        """Get an AI user profile"""
        try:
            if not username:
                return jsonify({"success": False, "error": "Username is required"}), 400

            user_doc = db.collection('aiUsers').document(username).get()

            if not user_doc.exists:
                return jsonify({"success": False, "error": "User not found"}), 404

            user_data = user_doc.to_dict()

            # Transform field names to match Flutter expectations
            if 'profile_picture_url' in user_data:
                user_data['profilePicture'] = user_data['profile_picture_url']

            return jsonify({"success": True, "data": user_data}), 200

        except Exception as ex:
            logger.error("Error retrieving profile: %s", ex)
            return jsonify({
                "success": False,
                "error": "Failed to retrieve profile",
                "code": "PROFILE_RETRIEVE_ERROR"
            }), 500
