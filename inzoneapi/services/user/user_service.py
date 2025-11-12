# services/user/user_service.py
from dependencies import db
from typing import Dict, Any
import logging
from flask import jsonify
from google.cloud import firestore

logger = logging.getLogger(__name__)

class UserService:
    """Service for user management operations"""

    @staticmethod
    def add_user(data: Dict[str, Any]) -> Dict[str, Any]:
        """Add a new user to the humanUsers collection"""
        try:
            user_data = {
                "name": data.get("Name"),
                "born": data.get("Born"),
                "timestamp": firestore.SERVER_TIMESTAMP
            }

            doc_ref = db.collection('humanUsers').add(user_data)
            return jsonify({"success": True, "data": {"userId": doc_ref[1].id}}), 200
        except Exception as ex:
            logger.error(f"Error adding user: {ex}")
            return jsonify({"success": False, "error": "Failed to add user", "code": "USER_ADD_ERROR"}), 500

    @staticmethod
    def get_avatars() -> Dict[str, Any]:
        """Get all avatars, prioritizing predefined ones"""
        try:
            # Retrieve all avatars
            avatars_ref = db.collection('avatars')
            snapshot = avatars_ref.stream()

            # Separate predefined avatars based on the image URL
            predefined_avatars = []
            user_created_avatars = []

            for doc in snapshot:
                avatar = doc.to_dict()
                if "predefined" in avatar.get("imgPath", ""):
                    predefined_avatars.append(avatar)
                else:
                    user_created_avatars.append(avatar)

            # Combine lists, prioritizing predefined avatars
            prioritized_avatars = predefined_avatars + user_created_avatars

            return jsonify(prioritized_avatars), 200
        except Exception as ex:
            logger.error(f"Error getting avatars: {ex}")
            return jsonify({"success": False, "error": str(ex)}), 500
