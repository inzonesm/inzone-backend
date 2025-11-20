# services/notifications/scheduler_service.py
from flask import jsonify
from services.notifications.queue_service import NotificationQueueService
from datetime import datetime, timedelta
from dependencies import db
import logging
import random

logger = logging.getLogger(__name__)


class NotificationSchedulerService:
    """Service for scheduled notification tasks"""

    @staticmethod
    def trigger_daily_nudges() -> tuple:
        """
        Cloud Scheduler endpoint for daily AI nudges

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            nudges_created = 0

            # Get active users who might need nudges
            try:
                # Get users who haven't had recent AI interactions
                day_ago = datetime.utcnow() - timedelta(days=1)

                # Query recent AI chat activity
                recent_chats = (db.collection('conversations')
                              .where('timestamp', '>', day_ago)
                              .limit(100)
                              .get())

                # Create sample nudges for testing
                for i in range(5):  # Create 5 test nudges
                    user_id = f"test_user_{i}"
                    character_id = f"test_character_{i}"

                    notification_data = {
                        'type': 'ai_nudge',
                        'userId': user_id,
                        'characterId': character_id,
                        'characterName': f"AI Friend {i}",
                        'chatId': f"chat_{i}",
                        'personalizedHook': f"Come back and chat with AI Friend {i}!",
                        'timestamp': datetime.utcnow().isoformat()
                    }

                    # Queue nudge notification
                    NotificationQueueService.queue_notification(notification_data, delay_minutes=random.randint(10, 60))
                    nudges_created += 1

            except Exception as e:
                logger.error(f"Error creating daily nudges: {e}")

            return jsonify({
                "success": True,
                "message": "Daily nudges scheduled",
                "stats": {"nudges_created": nudges_created}
            }), 200

        except Exception as e:
            logger.error(f"Error triggering daily nudges: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @staticmethod
    def trigger_weekly_rare_offers() -> tuple:
        """
        Cloud Scheduler endpoint for weekly rare offer selection

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            # Get eligible users for rare offers
            eligible_users = NotificationQueueService.get_rare_offer_eligible_users()

            offers_created = 0
            for user_id in eligible_users:
                # Create random rare offer
                offer_type = random.choice(['watch_video', 'refer_friend', 'double_coins'])
                coin_amount = random.randint(50, 200)

                notification_data = {
                    'userId': user_id,
                    'offerType': offer_type,
                    'coinAmount': coin_amount,
                    'reason': 'weekly_selection',
                    'timestamp': datetime.utcnow().isoformat()
                }

                # Queue rare offer notification
                NotificationQueueService.queue_notification({
                    'type': 'rare_offer',
                    'userId': user_id,
                    'characterName': NotificationQueueService.get_random_character_name(),
                    'offerType': offer_type,
                    'offerText': f"Special offer: +{coin_amount} InCash",
                    'coinAmount': coin_amount,
                    'reason': 'weekly_selection',
                    'timestamp': datetime.utcnow().isoformat()
                }, immediate=True)

                offers_created += 1

            return jsonify({
                "success": True,
                "message": f"Weekly rare offers created: {offers_created}",
                "eligible_users": len(eligible_users)
            }), 200

        except Exception as e:
            logger.error(f"Error triggering weekly rare offers: {e}")
            return jsonify({"success": False, "error": str(e)}), 500
