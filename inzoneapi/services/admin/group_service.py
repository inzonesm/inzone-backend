# services/admin/group_service.py
from flask import jsonify
from dependencies import db
import logging

logger = logging.getLogger(__name__)


class AdminGroupService:
    """Service for admin group operations"""

    @staticmethod
    def create_group(data: dict) -> tuple:
        """
        Create a new group

        Args:
            data: Dictionary containing group data with 'id' field

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            if 'id' not in data:
                return jsonify({'error': 'Group ID is required'}), 400

            db.collection('groups').document(data['id']).set(data)
            return jsonify({'message': 'Group created successfully'}), 200

        except Exception as ex:
            logger.error("Error creating group: %s", ex)
            return jsonify({'error': 'Failed to create group'}), 500
