# services/admin/user_service.py
from flask import jsonify
from dependencies import db
import logging

logger = logging.getLogger(__name__)


class AdminUserService:
    """Service for admin user operations"""

    @staticmethod
    def search_user(search_term: str) -> tuple:
        """
        Search for human users by name

        Args:
            search_term: Name search term

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            if not search_term:
                return jsonify({"success": False, "error": "Name parameter is required"}), 400

            # Get all human users and filter by name
            users_ref = db.collection('humanUsers')
            users_snapshot = users_ref.stream()

            matching_users = []

            for doc in users_snapshot:
                user_data = doc.to_dict()
                user_data['id'] = doc.id

                # Check if name contains the search term (case insensitive)
                user_name = user_data.get('name')
                if user_name and isinstance(user_name, str):
                    if search_term.lower() in user_name.lower():
                        matching_users.append(user_data)

            if not matching_users:
                return jsonify({
                    "success": True,
                    "message": f"No users found with name containing '{search_term}'",
                    "data": []
                }), 200

            return jsonify({
                "success": True,
                "message": f"Found {len(matching_users)} user(s) with name containing '{search_term}'",
                "data": matching_users
            }), 200

        except Exception as ex:
            logger.error("Error searching for user: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500
