# services/notifications/queue_service.py
from flask import jsonify
from google.cloud import firestore
from dependencies import db
from datetime import datetime, timedelta
import logging
import uuid
import random

logger = logging.getLogger(__name__)


class NotificationQueueService:
    """Service for notification queueing and helper functions"""

    @staticmethod
    def queue_notification(notification_data: dict, immediate: bool = False, batch: bool = False, delay_minutes: int = 0):
        """
        Queue notification for processing

        Args:
            notification_data: Notification payload data
            immediate: Send immediately
            batch: Batch with other notifications
            delay_minutes: Delay in minutes before sending
        """
        try:
            notification_id = str(uuid.uuid4())

            # Calculate when to send
            send_time = datetime.utcnow()
            if delay_minutes > 0:
                send_time += timedelta(minutes=delay_minutes)
            elif not immediate:
                send_time += timedelta(minutes=1)  # Default small delay

            queue_data = {
                'id': notification_id,
                'uid': notification_data['userId'],
                'type': notification_data['type'],
                'payload': notification_data,
                'status': 'pending',
                'notBefore': send_time,
                'immediate': immediate,
                'batch': batch,
                'createdAt': firestore.SERVER_TIMESTAMP,
                'retryCount': 0
            }

            db.collection('notificationsQueue').document(notification_id).set(queue_data)
            logger.info(f"Notification queued: {notification_id}")

        except Exception as e:
            logger.error(f"Error queueing notification: {e}")

    @staticmethod
    def check_rare_offer_eligibility(user_id: str) -> bool:
        """
        Check if user is eligible for rare offers

        Args:
            user_id: The user ID to check

        Returns:
            bool: True if eligible, False otherwise
        """
        try:
            # Check user preferences
            user_doc = db.collection('humanUsers').document(user_id).get()
            if not user_doc.exists:
                return False

            user_data = user_doc.to_dict()
            prefs = user_data.get('notificationPrefs', {})
            categories = prefs.get('categories', {})
            rare_offers = categories.get('rareOffers', {})

            if not rare_offers.get('enabled', True):
                return False

            # Check weekly limit
            max_per_week = rare_offers.get('maxPerWeek', 2)

            # Check recent rare offers
            week_ago = datetime.utcnow() - timedelta(days=7)
            recent_offers = (db.collection('rareOffersLog')
                            .where('userId', '==', user_id)
                            .where('timestamp', '>', week_ago)
                            .get())

            if len(list(recent_offers)) >= max_per_week:
                return False

            return True

        except Exception as e:
            logger.error(f"Error checking rare offer eligibility: {e}")
            return False

    @staticmethod
    def get_user_name(user_id: str) -> str:
        """
        Get user's display name

        Args:
            user_id: The user ID

        Returns:
            str: User's name or default
        """
        try:
            # Try humanUsers first
            user_doc = db.collection('humanUsers').document(user_id).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                return user_data.get('displayName', user_data.get('username', 'User'))

            # Try popularCharacters for AI users
            ai_doc = db.collection('popularCharacters').document(user_id).get()
            if ai_doc.exists:
                ai_data = ai_doc.to_dict()
                return ai_data.get('name', 'AI User')

            return 'User'

        except Exception as e:
            logger.error(f"Error getting user name: {e}")
            return 'User'

    @staticmethod
    def get_character_name(character_id: str) -> str:
        """
        Get AI character's name

        Args:
            character_id: The character ID

        Returns:
            str: Character's name or default
        """
        try:
            char_doc = db.collection('popularCharacters').document(character_id).get()
            if char_doc.exists:
                char_data = char_doc.to_dict()
                return char_data.get('name', 'AI Friend')
            return 'AI Friend'

        except Exception as e:
            logger.error(f"Error getting character name: {e}")
            return 'AI Friend'

    @staticmethod
    def get_random_character_name() -> str:
        """
        Get a random AI character name

        Returns:
            str: Random character's name
        """
        try:
            # Get a random character from popularCharacters
            characters = list(db.collection('popularCharacters').limit(10).stream())
            if characters:
                char = random.choice(characters)
                char_data = char.to_dict()
                return char_data.get('name', 'AI Friend')
            return 'AI Friend'

        except Exception as e:
            logger.error(f"Error getting random character name: {e}")
            return 'AI Friend'

    @staticmethod
    def log_rare_offer(user_id: str, offer_type: str, coin_amount: int):
        """
        Log rare offer to database

        Args:
            user_id: The user ID
            offer_type: Type of offer
            coin_amount: Amount of coins offered
        """
        try:
            log_data = {
                'userId': user_id,
                'offerType': offer_type,
                'coinAmount': coin_amount,
                'timestamp': firestore.SERVER_TIMESTAMP
            }
            db.collection('rareOffersLog').add(log_data)

        except Exception as e:
            logger.error(f"Error logging rare offer: {e}")

    @staticmethod
    def get_rare_offer_eligible_users() -> list:
        """
        Get list of users eligible for rare offers

        Returns:
            list: List of user IDs
        """
        try:
            # Get active users from last week
            week_ago = datetime.utcnow() - timedelta(days=7)

            # Simple implementation - get some recent active users
            # In production, you'd want more sophisticated logic
            eligible_users = []

            # Get users who have been active recently
            active_docs = db.collection('humanUsers').limit(50).stream()

            for doc in active_docs:
                user_id = doc.id
                if NotificationQueueService.check_rare_offer_eligibility(user_id):
                    eligible_users.append(user_id)

            return eligible_users[:10]  # Limit to 10 users

        except Exception as e:
            logger.error(f"Error getting eligible users: {e}")
            return []
