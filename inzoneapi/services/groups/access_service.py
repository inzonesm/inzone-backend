# services/groups/access_service.py
from flask import jsonify
from google.cloud import firestore
from dependencies import db
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class GroupAccessService:
    """Service for premium group access and subscriptions"""

    @staticmethod
    def get_available_groups() -> tuple:
        """
        Get all available groups

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            groups = [doc.to_dict() for doc in db.collection('groups').stream()]
            return jsonify({'groups': groups}), 200

        except Exception as ex:
            logger.error("Error fetching available groups: %s", ex)
            return jsonify({'error': 'Failed to fetch groups'}), 500

    @staticmethod
    def join_group(data: dict) -> tuple:
        """
        Join a group with a subscription tier

        Args:
            data: Dictionary containing user_id, group_id, tier (free/pass/vip)

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            user_id = data.get('user_id')
            group_id = data.get('group_id')
            tier = data.get('tier', 'free').lower()

            if not all([user_id, group_id]):
                return jsonify({'error': 'Missing required fields'}), 400

            group_ref = db.collection('groups').document(group_id)
            group_doc = group_ref.get()

            if not group_doc.exists:
                return jsonify({'error': 'Group not found'}), 404

            group = group_doc.to_dict()

            user_ref = db.collection('humanUsers').document(user_id)
            user_doc = user_ref.get()

            if not user_doc.exists:
                return jsonify({'error': 'User not found'}), 404

            user_data = user_doc.to_dict()

            # Determine pricing and duration based on the tier
            if tier == 'free':
                price = 0
                duration = group.get('free_duration')  # Could be None for indefinite
            elif tier == 'pass':
                price = group.get('pass_price', 0)
                duration = group.get('pass_duration', 1)  # Default to 1 day
            elif tier == 'vip':
                price = group.get('vip_price', 0)
                duration = group.get('vip_duration', 30)  # Default to 30 days
            else:
                return jsonify({'error': 'Invalid tier specified'}), 400

            # Check if user has sufficient funds
            if price > 0 and user_data.get('balance', 200) < price:
                return jsonify({'error': 'Insufficient funds'}), 400

            # Deduct funds if necessary
            if price > 0:
                user_ref.update({'balance': firestore.Increment(-price)})

            # Add the group to the user's groups array
            user_ref.update({'groups': firestore.ArrayUnion([group_id])})

            # Calculate the subscription end time if a duration is provided
            if duration:
                subscription_end = datetime.utcnow() + timedelta(days=duration)
                subscription_end_iso = subscription_end.isoformat()
            else:
                subscription_end_iso = None

            membership_data = {
                'group_id': group_id,
                'tier': tier,
                'subscription_end': subscription_end_iso,
                'joined_at': datetime.utcnow().isoformat()
            }

            # Save the group subscription in a subcollection under humanUsers
            db.collection('humanUsers').document(user_id).collection('groups').document(group_id).set(membership_data)

            return jsonify({
                'message': 'Group joined successfully',
                'tier': tier,
                'subscription_end': subscription_end_iso
            }), 200

        except Exception as ex:
            logger.error("Error joining group: %s", ex)
            return jsonify({'error': 'Failed to join group'}), 500

    @staticmethod
    def get_user_access(user_id: str) -> tuple:
        """
        Get all groups a user has access to

        Args:
            user_id: The user ID

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            if not user_id:
                return jsonify({'error': 'User ID is required'}), 400

            groups = [
                doc.to_dict()
                for doc in db.collection('humanUsers').document(user_id).collection('groups').stream()
            ]
            return jsonify({'groups': groups}), 200

        except Exception as ex:
            logger.error("Error fetching user access: %s", ex)
            return jsonify({'error': 'Failed to fetch user access'}), 500
