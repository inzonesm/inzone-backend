# services/notifications/push_service.py
from flask import jsonify
from google.cloud import firestore
from firebase_admin import messaging
from dependencies import db
import logging

logger = logging.getLogger(__name__)


class NotificationPushService:
    """Service for FCM push notifications"""

    @staticmethod
    def register_fcm_token(data: dict) -> tuple:
        """
        Register FCM token for user

        Args:
            data: Dictionary containing userId and token

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            if 'userId' not in data or 'token' not in data:
                return jsonify({"success": False, "error": "Missing userId or token"}), 400

            user_id = data['userId']
            token = data['token']

            # Update user's FCM tokens in humanUsers collection
            user_ref = db.collection('humanUsers').document(user_id)
            user_ref.set({
                'fcmTokens': firestore.ArrayUnion([token]),
                'lastTokenUpdate': firestore.SERVER_TIMESTAMP
            }, merge=True)

            return jsonify({"success": True, "message": "FCM token registered"}), 200

        except Exception as e:
            logger.error(f"Error registering FCM token: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @staticmethod
    def send_push_notification(data: dict) -> tuple:
        """
        Send push notification to user via FCM

        Args:
            data: Dictionary containing userId, title, body, and optional data payload

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            logger.info("=== SEND PUSH NOTIFICATION ENDPOINT HIT ===")
            logger.info(f"Request data received: {data}")

            if not data:
                logger.error("No request data provided")
                return jsonify({"success": False, "error": "Missing request data"}), 400

            required_fields = ['userId', 'title', 'body']
            if not all(field in data for field in required_fields):
                logger.error(f"Missing required fields. Data: {data}")
                return jsonify({"success": False, "error": "Missing required fields: userId, title, body"}), 400

            user_id = data['userId']
            title = data['title']
            body = data['body']
            notification_data = data.get('data', {})

            logger.info(f"Sending push notification to user {user_id}: {title}")

            # Get user's FCM tokens - check humanUsers first
            user_tokens = []
            try:
                logger.info(f"Fetching user document for user_id: {user_id}")
                user_doc = db.collection('humanUsers').document(user_id).get()
                logger.info(f"User document exists in humanUsers: {user_doc.exists}")

                if user_doc.exists:
                    user_data = user_doc.to_dict()
                    user_tokens = user_data.get('fcmTokens', [])
                    logger.info(f"Found user in humanUsers collection with {len(user_tokens)} FCM tokens")
                    logger.info(f"FCM tokens: {[token[:20] + '...' for token in user_tokens]}")
                else:
                    # Check if this is an AI character (should not receive push notifications)
                    ai_doc = db.collection('popularCharacters').document(user_id).get()
                    if ai_doc.exists:
                        logger.warning(f"Attempted to send push notification to AI character {user_id}")
                        return jsonify({"success": False, "error": f"Cannot send push notifications to AI characters (ID: {user_id})"}), 400
                    else:
                        logger.warning(f"User {user_id} not found in humanUsers or popularCharacters collections")
                        return jsonify({"success": False, "error": f"User {user_id} not found"}), 404
            except Exception as e:
                logger.error(f"Error fetching user tokens: {e}")
                return jsonify({"success": False, "error": f"Error fetching user: {str(e)}"}), 500

            if not user_tokens:
                logger.warning(f"No FCM tokens found for user {user_id}")
                return jsonify({"success": False, "error": "No FCM tokens found for user"}), 400

            # Send push notification to all user's devices
            successful_sends = 0
            failed_sends = 0
            invalid_tokens = []

            logger.info(f"Starting to send notifications to {len(user_tokens)} tokens")

            for i, token in enumerate(user_tokens):
                try:
                    logger.info(f"Sending to token {i+1}/{len(user_tokens)}: {token[:20]}...")

                    # Create FCM message
                    message = messaging.Message(
                        notification=messaging.Notification(
                            title=title,
                            body=body,
                        ),
                        data={str(k): str(v) for k, v in notification_data.items()},  # FCM data must be strings
                        token=token,
                        android=messaging.AndroidConfig(
                            notification=messaging.AndroidNotification(
                                channel_id='high_importance_channel',
                                priority='high',
                            ),
                        ),
                        apns=messaging.APNSConfig(
                            payload=messaging.APNSPayload(
                                aps=messaging.Aps(
                                    alert=messaging.ApsAlert(
                                        title=title,
                                        body=body,
                                    ),
                                    badge=1,
                                    sound='default',
                                ),
                            ),
                        ),
                    )

                    logger.info(f"FCM message created, sending...")

                    # Send message
                    response = messaging.send(message)
                    logger.info(f"✅ Push notification sent successfully to token {token[:20]}... Response: {response}")
                    successful_sends += 1

                except messaging.UnregisteredError as e:
                    logger.warning(f"❌ Invalid FCM token: {token[:20]}... Error: {e}")
                    invalid_tokens.append(token)
                    failed_sends += 1
                except Exception as e:
                    logger.error(f"❌ Error sending push notification to token {token[:20]}...: {e}")
                    failed_sends += 1

            # Remove invalid tokens from user document
            if invalid_tokens:
                try:
                    logger.info(f"Removing {len(invalid_tokens)} invalid tokens...")
                    user_ref = db.collection('humanUsers').document(user_id)
                    for invalid_token in invalid_tokens:
                        user_ref.update({
                            'fcmTokens': firestore.ArrayRemove([invalid_token])
                        })
                    logger.info(f"Removed {len(invalid_tokens)} invalid tokens for user {user_id}")
                except Exception as e:
                    logger.error(f"Error removing invalid tokens: {e}")

            result = {
                "success": True,
                "message": f"Push notification processing complete",
                "stats": {
                    "successful": successful_sends,
                    "failed": failed_sends,
                    "invalidTokens": len(invalid_tokens)
                }
            }

            logger.info(f"Push notification result: {result}")
            return jsonify(result), 200

        except Exception as e:
            logger.error(f"CRITICAL ERROR in send_push_notification: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return jsonify({"success": False, "error": "Internal error"}), 500
