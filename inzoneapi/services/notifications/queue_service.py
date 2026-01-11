# services/notifications/queue_service.py
from flask import jsonify
from google.cloud import firestore
from dependencies import db
from datetime import datetime, timedelta, time
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
    def smart_queue_notification(notification_data: dict, immediate: bool = False, batch: bool = False, delay_minutes: int = 0):
        """
        Smart queue notification with automatic digest checking
        
        This method queues a notification and then automatically checks if the user
        has any pending digest notifications that should be sent (if they're no longer
        in quiet state). This eliminates the need for cron jobs.

        Args:
            notification_data: Notification payload data
            immediate: Send immediately
            batch: Batch with other notifications
            delay_minutes: Delay in minutes before sending
        """
        try:
            # First, queue the notification normally
            NotificationQueueService.queue_notification(notification_data, immediate, batch, delay_minutes)
            
            # Then, auto-check if this user has pending digest notifications
            user_id = notification_data.get('userId')
            if user_id:
                NotificationQueueService._auto_check_user_digest(user_id)
                
        except Exception as e:
            logger.error(f"Error in smart_queue_notification: {e}")

    @staticmethod
    def _auto_check_user_digest(user_id: str):
        """
        Automatically check and send digest for a user if they have pending
        quietDigest notifications and are no longer in quiet state.
        
        This is called whenever ANY notification is queued, providing automatic
        digest delivery without needing cron jobs.

        Args:
            user_id: The user ID to check
        """
        try:
            # Check if user is still in quiet state
            is_quiet, _ = NotificationQueueService.is_user_in_quiet_state(user_id)
            
            # If user is still in quiet state, nothing to do
            if is_quiet:
                return
            
            # User is NOT in quiet state - check for pending digest notifications
            notifications_ref = db.collection('notifications')
            pending_digest = (notifications_ref
                            .where('userId', '==', user_id)
                            .where('quietDigest', '==', True)
                            .where('isRead', '==', False)
                            .get())
            
            pending_list = list(pending_digest)
            
            # If there are pending digest notifications, send them
            if pending_list:
                logger.info(f"Auto-check found {len(pending_list)} pending digest notifications for user {user_id}")
                NotificationQueueService.send_digest_notification(user_id, pending_list)
                
        except Exception as e:
            logger.error(f"Error in auto_check_user_digest: {e}")

    @staticmethod
    def send_digest_notification(user_id: str, notifications: list):
        """
        Send a single digest push notification summarizing accumulated notifications

        Args:
            user_id: The user ID
            notifications: List of notification documents
        """
        try:
            notification_count = len(notifications)
            
            # Import here to avoid circular dependency
            from services.notifications.push_service import NotificationPushService
            
            # Create digest push notification
            digest_data = {
                'userId': user_id,
                'title': 'New Notifications',
                'body': f'You have {notification_count} new notification{"s" if notification_count != 1 else ""}',
                'data': {
                    'type': 'digest',
                    'count': str(notification_count),
                    'action': 'navigate_to_notifications'
                }
            }
            
            # Send the digest push
            NotificationPushService.send_push_notification(digest_data)
            logger.info(f"Sent digest notification to user {user_id} for {notification_count} notifications")
            
            # Clear quietDigest flags from the notifications
            for notif_doc in notifications:
                notif_ref = db.collection('notifications').document(notif_doc.id)
                notif_ref.update({'quietDigest': False})
            
            logger.info(f"Cleared quietDigest flags for {notification_count} notifications")
            
        except Exception as e:
            logger.error(f"Error sending digest notification: {e}")

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
    def is_user_in_quiet_state(user_id: str) -> tuple:
        """
        Check if user is in a quiet state (pauseAll or quiet hours)

        Args:
            user_id: The user ID to check

        Returns:
            tuple: (is_quiet: bool, reason: str)
        """
        try:
            # Get user preferences
            user_doc = db.collection('humanUsers').document(user_id).get()
            if not user_doc.exists:
                return (False, None)

            user_data = user_doc.to_dict()
            prefs = user_data.get('notificationPrefs', {})

            # Check if pauseAll is enabled
            if prefs.get('pauseAll', False):
                return (True, 'pauseAll')

            # Check if quiet hours are enabled and active
            if prefs.get('quietHoursEnabled', False):
                quiet_hours = prefs.get('quietHours', {})
                start_str = quiet_hours.get('start', '22:00')
                end_str = quiet_hours.get('end', '08:00')

                # Parse time strings (format: HH:MM)
                start_parts = start_str.split(':')
                end_parts = end_str.split(':')
                start_time = time(int(start_parts[0]), int(start_parts[1]))
                end_time = time(int(end_parts[0]), int(end_parts[1]))

                # Get timezone offset from user prefs (in hours, e.g., -5 for EST)
                # If not set, assume UTC (offset 0)
                timezone_offset_hours = prefs.get('timezoneOffset', 0)
                
                # Get current UTC time and convert to user's local time
                current_utc = datetime.utcnow()
                current_local = current_utc + timedelta(hours=timezone_offset_hours)
                current_time = current_local.time()
                
                logger.info(f"Quiet hours check for user {user_id}:")
                logger.info(f"  Start: {start_str} ({start_time}), End: {end_str} ({end_time})")
                logger.info(f"  Current UTC time: {current_utc.time()}")
                logger.info(f"  Timezone offset: {timezone_offset_hours} hours")
                logger.info(f"  Current local time: {current_time}")

                # Handle quiet hours that span midnight
                in_quiet_hours = False
                if start_time <= end_time:
                    # Simple case: daytime quiet hours (unusual)
                    in_quiet_hours = start_time <= current_time <= end_time
                    logger.info(f"  Simple case: {in_quiet_hours}")
                else:
                    # Spans midnight: e.g., 10 PM to 8 AM
                    in_quiet_hours = current_time >= start_time or current_time <= end_time
                    logger.info(f"  Spans midnight case: {in_quiet_hours} (>= start: {current_time >= start_time}, <= end: {current_time <= end_time})")

                if in_quiet_hours:
                    logger.info(f"  ✅ User IS in quiet hours")
                    # Schedule digest timer for when quiet hours end
                    from services.notifications.digest_timer import digest_timer_manager
                    digest_timer_manager.schedule_user_digest(user_id, end_time, timezone_offset_hours)
                    return (True, 'quietHours')
                else:
                    logger.info(f"  ❌ User NOT in quiet hours")

            return (False, None)

        except Exception as e:
            logger.error(f"Error checking user quiet state: {e}")
            return (False, None)

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
