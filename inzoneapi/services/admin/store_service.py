# services/admin/store_service.py
from flask import jsonify
from dependencies import db
import logging

logger = logging.getLogger(__name__)


class AdminStoreService:
    """Service for admin store operations"""

    @staticmethod
    def add_item(data: dict) -> tuple:
        """
        Add an item to the store

        Args:
            data: Dictionary containing item data with 'id' field

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            if 'id' not in data:
                return jsonify({'error': 'Item ID is required'}), 400

            db.collection('store_items').document(data['id']).set(data)
            return jsonify({'message': 'Item added successfully'}), 200

        except Exception as ex:
            logger.error("Error adding store item: %s", ex)
            return jsonify({'error': 'Failed to add item'}), 500
