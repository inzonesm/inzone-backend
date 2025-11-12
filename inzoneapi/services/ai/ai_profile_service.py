# services/ai/ai_profile_service.py
from dependencies import db
from typing import Dict, Any
import logging
from flask import jsonify
from google.cloud import firestore

logger = logging.getLogger(__name__)

class AIProfileService:
    """Service for AI profile management"""

    @staticmethod
    def get_all_profiles() -> Dict[str, Any]:
        """Get all AI character profiles"""
        try:
            query = db.collection('ai_characters')
            snapshot = query.stream()
            profiles = [doc.to_dict() for doc in snapshot]

            return jsonify({"success": True, "data": profiles}), 200
        except Exception as ex:
            logger.error(f"Error getting AI profiles: {ex}")
            return jsonify({"success": False, "error": "Failed to get AI profiles", "code": "PROFILE_GET_ERROR"}), 500

    @staticmethod
    def create_profile(data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new AI character profile"""
        try:
            profile_data = {
                "userName": data.get("UserName"),
                "description": data.get("Description"),
                "timestamp": firestore.SERVER_TIMESTAMP
            }

            doc_ref = db.collection('ai_characters').add(profile_data)
            return jsonify({"success": True, "data": {"profileId": doc_ref[1].id}}), 200
        except Exception as ex:
            logger.error(f"Error creating AI profile: {ex}")
            return jsonify({"success": False, "error": "Failed to create AI profile", "code": "AI_PROFILE_CREATE_ERROR"}), 500
