# services/notifications/preference_service.py
from flask import jsonify
from google.cloud import firestore
from dependencies import db
import logging

logger = logging.getLogger(__name__)


class NotificationPreferenceService:
    """Service for notification preference management"""

    @staticmethod
    def update_preferences(data: dict) -> tuple:
        """
        Update user notification preferences

        Args:
            data: Dictionary containing userId and preferences

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            if 'userId' not in data or 'preferences' not in data:
                return jsonify({"success": False, "error": "Missing userId or preferences"}), 400

            user_id = data['userId']
            preferences = data['preferences']

            # Update user preferences (try humanUsers collection first)
            try:
                user_ref = db.collection('humanUsers').document(user_id)
                user_ref.update({
                    'notificationPrefs': preferences,
                    'preferencesUpdatedAt': firestore.SERVER_TIMESTAMP
                })
                return jsonify({"success": True, "message": "Preferences updated"}), 200
            except Exception as e1:
                # If humanUsers doesn't work, try users collection
                try:
                    user_ref = db.collection('users').document(user_id)
                    user_ref.update({
                        'notificationPrefs': preferences,
                        'preferencesUpdatedAt': firestore.SERVER_TIMESTAMP
                    })
                    return jsonify({"success": True, "message": "Preferences updated"}), 200
                except Exception as e2:
                    return jsonify({"success": False, "error": f"User document not found in any collection: {str(e2)}"}), 404

        except Exception as e:
            logger.error(f"Error updating preferences: {e}")
            return jsonify({"success": False, "error": str(e)}), 500
