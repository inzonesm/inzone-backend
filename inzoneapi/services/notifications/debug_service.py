# services/notifications/debug_service.py
from flask import jsonify
from google.cloud import firestore
from dependencies import db
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class NotificationDebugService:
    """Service for notification debugging and testing"""

    @staticmethod
    def debug_notification_count(user_id: str = None) -> tuple:
        """
        Debug endpoint to count notifications in queue

        Args:
            user_id: Optional user ID to filter by

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            # Count all documents in notificationsQueue
            all_docs = db.collection('notificationsQueue').get()
            total_count = len(list(all_docs))

            # Count for specific user if provided
            user_count = 0
            user_docs = []
            if user_id:
                user_query = db.collection('notificationsQueue').where('uid', '==', user_id).get()
                user_list = list(user_query)
                user_count = len(user_list)
                user_docs = [doc.to_dict() for doc in user_list]

            return jsonify({
                "success": True,
                "data": {
                    "total_notifications": total_count,
                    "user_notifications": user_count,
                    "user_id": user_id,
                    "sample_user_docs": user_docs[:3]  # First 3 for debugging
                }
            }), 200

        except Exception as e:
            logger.error(f"Error in debug count: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @staticmethod
    def get_all_user_notifications(user_id: str) -> tuple:
        """
        Get all notifications for a user - simplified to avoid index issues

        Args:
            user_id: The user ID

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            notifications = []

            # 1. Get notifications from main notifications collection
            try:
                notifications_query = (db.collection('notifications')
                                       .where('userId', '==', user_id)
                                       .limit(50))

                for doc in notifications_query.get():
                    notification = doc.to_dict()
                    notification['id'] = doc.id
                    # Ensure timestamp key exists for sorting logic later
                    if 'timestamp' not in notification and 'createdAt' in notification:
                        notification['timestamp'] = notification.get('createdAt')
                    notifications.append(notification)

            except Exception as e:
                logger.error(f"Error getting notifications: {e}")

            # 2. Get rare offers from rareOffersLog
            try:
                rare_offers_query = (db.collection('rareOffersLog')
                                     .document(user_id)
                                     .collection('offers')
                                     .order_by('sentAt', direction=firestore.Query.DESCENDING)
                                     .limit(20))
                for doc in rare_offers_query.get():
                    offer = doc.to_dict()
                    notif = {
                        'id': f"rare_{doc.id}",
                        'type': 'rare_offer',
                        'source': 'rare_offers_log',
                        'offerType': offer.get('type'),
                        'coinAmount': offer.get('coinAmount') or offer.get('coinsAwarded'),
                        'status': offer.get('status'),
                        'timestamp': offer.get('sentAt'),
                        'characterName': offer.get('characterName', 'InZone'),
                        'notificationId': offer.get('notificationId')
                    }
                    notifications.append(notif)
            except Exception as e:
                logger.error(f"Error fetching rareOffersLog for user {user_id}: {e}")

            # 3. Get AI nudge logs
            try:
                today_str = datetime.utcnow().strftime('%Y-%m-%d')
                nudge_doc = (db.collection('nudges')
                            .document(user_id)
                            .collection('daily')
                            .document(today_str)
                            .get())

                if nudge_doc.exists:
                    nudge_data = nudge_doc.to_dict()
                    if nudge_data.get('sentCount', 0) > 0:
                        notifications.append({
                            'type': 'ai_nudge',
                            'source': 'nudges_log',
                            'sentCount': nudge_data.get('sentCount'),
                            'lastNudgeAt': nudge_data.get('lastNudgeAt'),
                            'characterName': 'AI Assistant',
                            'personalizedHook': 'Come back and continue the conversation!'
                        })

            except Exception as e:
                logger.error(f"Error getting AI nudges: {e}")

            # Sort all notifications by timestamp (newest first)
            def get_timestamp(notif):
                ts = notif.get('timestamp')
                if ts is None:
                    return datetime.min
                if hasattr(ts, 'timestamp'):  # Firestore timestamp
                    return datetime.fromtimestamp(ts.timestamp())
                return ts

            notifications.sort(key=get_timestamp, reverse=True)

            # Group notifications by type for summary
            notification_summary = {}
            for notif in notifications:
                notif_type = notif.get('type', 'unknown')
                if notif_type not in notification_summary:
                    notification_summary[notif_type] = 0
                notification_summary[notif_type] += 1

            return jsonify({
                "success": True,
                "data": {
                    "user_id": user_id,
                    "total_notifications": len(notifications),
                    "summary_by_type": notification_summary,
                    "notifications": notifications[:50],  # Limit to 50 most recent
                    "sources_checked": [
                        "notificationsQueue",
                        "group_activity",
                        "post_likes",
                        "post_comments",
                        "direct_messages",
                        "rare_offers_log",
                        "nudges_log"
                    ]
                }
            }), 200

        except Exception as e:
            logger.error(f"Error getting all user notifications: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @staticmethod
    def create_sample_notifications(data: dict) -> tuple:
        """
        Create sample notifications for testing

        Args:
            data: Dictionary containing user_id

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            user_id = data.get('user_id')

            if not user_id:
                return jsonify({"success": False, "error": "user_id required"}), 400

            # Create sample notifications in queue
            sample_notifications = [
                {
                    'uid': user_id,
                    'type': 'group_digest',
                    'payload': {
                        'groupId': 'test_group_1',
                        'groupName': 'Test Group',
                        'senderName': 'TestUser',
                        'content': 'This is a test group message notification'
                    },
                    'status': 'pending',
                    'createdAt': firestore.SERVER_TIMESTAMP,
                    'immediate': False,
                    'batch': True
                },
                {
                    'uid': user_id,
                    'type': 'dm_new',
                    'payload': {
                        'chatId': 'test_chat_1',
                        'senderName': 'AI Friend',
                        'preview': 'Hey! How are you doing today?'
                    },
                    'status': 'pending',
                    'createdAt': firestore.SERVER_TIMESTAMP,
                    'immediate': True,
                    'batch': False
                },
                {
                    'uid': user_id,
                    'type': 'engagement_digest',
                    'payload': {
                        'postId': 'test_post_1',
                        'engagementType': 'like',
                        'engagerUserId': 'test_user_2',
                        'content': 'Your post got some engagement!'
                    },
                    'status': 'pending',
                    'createdAt': firestore.SERVER_TIMESTAMP,
                    'immediate': False,
                    'batch': True
                },
                {
                    'uid': user_id,
                    'type': 'rare_offer',
                    'payload': {
                        'characterName': 'InZone',
                        'offerType': 'watch_video',
                        'offerText': 'Watch a short video for +50 InCash',
                        'coinAmount': 50
                    },
                    'status': 'pending',
                    'createdAt': firestore.SERVER_TIMESTAMP,
                    'immediate': True,
                    'batch': False
                }
            ]

            created_ids = []
            for notification in sample_notifications:
                doc_ref = db.collection('notificationsQueue').add(notification)
                created_ids.append(doc_ref[1].id)

            return jsonify({
                "success": True,
                "message": f"Created {len(sample_notifications)} sample notifications",
                "notification_ids": created_ids
            }), 200

        except Exception as e:
            logger.error(f"Error creating sample notifications: {e}")
            return jsonify({"success": False, "error": str(e)}), 500
