# services/notifications/event_service.py
from flask import jsonify
from google.cloud import firestore
from firebase_admin import messaging
from dependencies import db
from services.notifications.queue_service import NotificationQueueService
import logging
import random

logger = logging.getLogger(__name__)


class NotificationEventService:
    """Service for handling notification events"""

    @staticmethod
    def handle_group_message(data: dict) -> tuple:
        """Handle group message notification event"""
        try:
            # Validate required fields
            required_fields = ['groupId', 'content', 'senderId', 'timestamp']
            if not all(field in data for field in required_fields):
                return jsonify({"success": False, "error": "Missing required fields"}), 400

            # Get group members to notify
            group_doc = db.collection('groupChats').document(data['groupId']).get()
            if not group_doc.exists:
                return jsonify({"success": False, "error": "Group not found"}), 404

            group_data = group_doc.to_dict()
            participants = group_data.get('participants', [])

            # Normalize and deduplicate participant IDs
            participant_ids = []
            seen_ids = set()
            for participant in participants:
                pid = None
                if isinstance(participant, dict):
                    pid = participant.get('uid')
                elif isinstance(participant, str):
                    pid = participant

                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    participant_ids.append(pid)

            # Create notification events for each unique participant (except sender)
            notifications_created = 0
            for participant_id in participant_ids:
                if not participant_id or participant_id == data['senderId']:
                    continue

                # Check if user has group notifications enabled
                user_doc = db.collection('humanUsers').document(participant_id).get()
                if user_doc.exists:
                    user_data = user_doc.to_dict()
                    prefs = user_data.get('notificationPrefs', {})
                    categories = prefs.get('categories', {})
                    group_prefs = categories.get('group', {'enabled': True})

                    if group_prefs.get('enabled', True):
                        # Create notification document
                        notification_doc = {
                            'userId': participant_id,
                            'type': 'group_message',
                            'title': f"New message in {group_data.get('name', 'Group Chat')}",
                            'body': f"{NotificationQueueService.get_user_name(data['senderId'])}: {data['content'][:50]}...",
                            'isRead': False,
                            'createdAt': firestore.SERVER_TIMESTAMP,
                            'data': {
                                'groupId': data['groupId'],
                                'groupName': group_data.get('name', 'Group Chat'),
                                'senderId': data['senderId'],
                                'senderName': NotificationQueueService.get_user_name(data['senderId']),
                                'messageContent': data['content']
                            }
                        }

                        # Store notification in Firestore
                        db.collection('notifications').add(notification_doc)

                        # Also queue for FCM push notification
                        notification_data = {
                            'type': 'group_digest',
                            'userId': participant_id,
                            'groupId': data['groupId'],
                            'groupName': group_data.get('name', 'Group Chat'),
                            'senderName': NotificationQueueService.get_user_name(data['senderId']),
                            'content': data['content'][:100],
                            'timestamp': data['timestamp']
                        }
                        NotificationQueueService.queue_notification(notification_data, batch=True, delay_minutes=5)
                        notifications_created += 1

            return jsonify({
                "success": True,
                "message": "Group message notifications created and queued",
                "notifications_created": notifications_created
            }), 200

        except Exception as e:
            logger.error(f"Error handling group message notification: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @staticmethod
    def handle_group_mention(data: dict) -> tuple:
        """Handle group mention notification event"""
        try:
            # Validate required fields
            required_fields = ['groupId', 'mentionedUserId', 'content', 'senderId', 'timestamp']
            if not all(field in data for field in required_fields):
                return jsonify({"success": False, "error": "Missing required fields"}), 400

            # Get group info
            group_doc = db.collection('groupChats').document(data['groupId']).get()
            if not group_doc.exists:
                return jsonify({"success": False, "error": "Group not found"}), 404

            group_data = group_doc.to_dict()

            # Create immediate mention notification
            notification_data = {
                'type': 'mention',
                'userId': data['mentionedUserId'],
                'groupId': data['groupId'],
                'groupName': group_data.get('name', 'Group Chat'),
                'senderName': NotificationQueueService.get_user_name(data['senderId']),
                'snippet': data['content'][:50],
                'msgId': data.get('msgId', ''),
                'timestamp': data['timestamp']
            }

            # Queue high-priority notification
            NotificationQueueService.queue_notification(notification_data, immediate=True)

            return jsonify({"success": True, "message": "Mention notification queued"}), 200

        except Exception as e:
            logger.error(f"Error handling mention notification: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @staticmethod
    def handle_direct_message(data: dict) -> tuple:
        """Handle direct message notification event"""
        try:
            # Validate required fields
            required_fields = ['chatId', 'content', 'senderId', 'receiverId', 'timestamp']
            if not all(field in data for field in required_fields):
                return jsonify({"success": False, "error": "Missing required fields"}), 400

            # Check if receiver has DM notifications enabled
            user_doc = db.collection('humanUsers').document(data['receiverId']).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                prefs = user_data.get('notificationPrefs', {})
                categories = prefs.get('categories', {})
                dm_prefs = categories.get('dm', {'enabled': True})

                if dm_prefs.get('enabled', True):
                    # Store notification directly in notifications collection
                    notification_doc = {
                        'userId': data['receiverId'],
                        'type': 'direct_message',
                        'title': NotificationQueueService.get_user_name(data['senderId']),
                        'body': data['content'][:100] + '...' if len(data['content']) > 100 else data['content'],
                        'isRead': False,
                        'createdAt': firestore.SERVER_TIMESTAMP,
                        'data': {
                            'chatId': data['chatId'],
                            'senderId': data['senderId'],
                            'senderName': NotificationQueueService.get_user_name(data['senderId']),
                            'messageContent': data['content']
                        }
                    }

                    # Store in main notifications collection
                    db.collection('notifications').add(notification_doc)

            return jsonify({"success": True, "message": "DM notification created"}), 200

        except Exception as e:
            logger.error(f"Error handling DM notification: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @staticmethod
    def handle_post_engagement(data: dict) -> tuple:
        """Handle post engagement notification event"""
        try:
            # Validate required fields
            required_fields = ['postId', 'type', 'userId', 'timestamp']
            if not all(field in data for field in required_fields):
                return jsonify({"success": False, "error": "Missing required fields"}), 400

            # Only notify if there's a post author and it's not the same user
            post_author_id = data.get('postAuthorId')
            if not post_author_id or post_author_id == data['userId']:
                return jsonify({"success": True, "message": "No notification needed"}), 200

            # Check if post author has engagement notifications enabled
            user_doc = db.collection('humanUsers').document(post_author_id).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                prefs = user_data.get('notificationPrefs', {})
                categories = prefs.get('categories', {})
                engagement_prefs = categories.get('engagement', {'enabled': True})

                if engagement_prefs.get('enabled', True):
                    # Create notification document
                    engagement_types = {
                        'like': 'liked',
                        'comment': 'commented on',
                        'share': 'shared'
                    }

                    # Create proper notification type and title based on engagement type
                    engagement_type = data['type']
                    if engagement_type == 'like':
                        notification_type = 'post_like'
                        notification_title = f"{NotificationQueueService.get_user_name(data['userId'])} liked your post"
                    elif engagement_type == 'comment':
                        notification_type = 'post_comment'
                        notification_title = f"{NotificationQueueService.get_user_name(data['userId'])} commented on your post"
                    elif engagement_type == 'share':
                        notification_type = 'post_share'
                        notification_title = f"{NotificationQueueService.get_user_name(data['userId'])} shared your post"
                    else:
                        notification_type = 'post_engagement'
                        notification_title = f"{NotificationQueueService.get_user_name(data['userId'])} engaged with your post"

                    notification_doc = {
                        'userId': post_author_id,
                        'type': notification_type,
                        'title': notification_title,
                        'body': f"{NotificationQueueService.get_user_name(data['userId'])} {engagement_types.get(data['type'], 'engaged with')} your post",
                        'isRead': False,
                        'createdAt': firestore.SERVER_TIMESTAMP,
                        'data': {
                            'postId': data['postId'],
                            'engagementType': data['type'],
                            'engagerUserId': data['userId'],
                            'content': data.get('content', '')
                        }
                    }

                    # Store notification in Firestore
                    db.collection('notifications').add(notification_doc)

                    # Also queue for FCM (batched)
                    notification_data = {
                        'type': 'engagement_digest',
                        'userId': post_author_id,
                        'postId': data['postId'],
                        'engagementType': data['type'],
                        'engagerUserId': data['userId'],
                        'content': data.get('content', ''),
                        'timestamp': data['timestamp']
                    }
                    NotificationQueueService.queue_notification(notification_data, batch=True, delay_minutes=30)

            return jsonify({"success": True, "message": "Engagement notification created and queued"}), 200

        except Exception as e:
            logger.error(f"Error handling engagement notification: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @staticmethod
    def handle_user_follow(data: dict) -> tuple:
        """Handle user follow notification event"""
        try:
            logger.info(f"=== USER FOLLOW NOTIFICATION EVENT ===")
            logger.info(f"Request data: {data}")

            # Validate required fields
            required_fields = ['followerId', 'followedUserId', 'timestamp']
            if not all(field in data for field in required_fields):
                logger.error(f"Missing required fields. Data: {data}")
                return jsonify({"success": False, "error": "Missing required fields"}), 400

            follower_id = data['followerId']
            followed_user_id = data['followedUserId']

            logger.info(f"Processing follow notification: {follower_id} -> {followed_user_id}")

            # Get follower name
            follower_name = NotificationQueueService.get_user_name(follower_id)
            logger.info(f"Follower name resolved: {follower_name}")

            # Get followed user's FCM tokens
            try:
                user_doc = db.collection('humanUsers').document(followed_user_id).get()
                if not user_doc.exists:
                    logger.warning(f"Followed user {followed_user_id} not found in humanUsers collection")
                    return jsonify({"success": False, "error": f"User {followed_user_id} not found"}), 404

                user_data = user_doc.to_dict()
                user_tokens = user_data.get('fcmTokens', [])

                if not user_tokens:
                    logger.info(f"No FCM tokens found for user {followed_user_id}")
                    return jsonify({"success": True, "message": "No tokens to send notification to"}), 200

                # Send FCM notifications to all user's devices
                successful_sends = 0
                failed_sends = 0

                for token in user_tokens:
                    try:
                        message = messaging.Message(
                            notification=messaging.Notification(
                                title='New Follower',
                                body=f'{follower_name} started following you'
                            ),
                            data={
                                'type': 'user_follow',
                                'followerId': follower_id,
                                'timestamp': data['timestamp'],
                                'action': 'navigate_to_profile',
                                'route': f'/profile/{follower_id}',
                            },
                            token=token
                        )

                        response = messaging.send(message)
                        logger.info(f"Follow notification sent to token {token[:20]}... Response: {response}")
                        successful_sends += 1

                    except Exception as token_error:
                        logger.error(f"Failed to send notification to token {token[:20]}...: {token_error}")
                        failed_sends += 1

                logger.info(f"Follow notification stats - Successful: {successful_sends}, Failed: {failed_sends}")

            except Exception as e:
                logger.error(f"Error sending follow push notification: {e}")
                return jsonify({"success": False, "error": f"Failed to send push notification: {str(e)}"}), 500

            return jsonify({"success": True, "message": "Follow notification processed", "stats": {"successful": successful_sends, "failed": failed_sends}}), 200

        except Exception as e:
            logger.error(f"Error handling follow notification: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @staticmethod
    def handle_rare_offer(data: dict) -> tuple:
        """Handle rare coin offer notification event"""
        try:
            # Validate required fields
            required_fields = ['userId', 'offerType', 'coinAmount', 'timestamp']
            if not all(field in data for field in required_fields):
                return jsonify({"success": False, "error": "Missing required fields"}), 400

            # Check if user is eligible for rare offers
            if not NotificationQueueService.check_rare_offer_eligibility(data['userId']):
                return jsonify({"success": True, "message": "User not eligible for rare offers"}), 200

            # Get a random AI character for the offer
            character_name = NotificationQueueService.get_random_character_name()

            # Create offer notification
            offer_texts = {
                'watch_video': f"Watch a short video for +{data['coinAmount']} InCash",
                'refer_friend': f"Invite 1 friend → +{data['coinAmount']} InCash",
                'double_coins': f"Limited time: Double coins for {data['coinAmount']} minutes!"
            }

            notification_data = {
                'type': 'rare_offer',
                'userId': data['userId'],
                'characterName': character_name,
                'offerType': data['offerType'],
                'offerText': offer_texts.get(data['offerType'], f"Earn {data['coinAmount']} InCash!"),
                'coinAmount': data['coinAmount'],
                'reason': data.get('reason', 'special_offer'),
                'timestamp': data['timestamp']
            }

            # Queue high-priority notification
            NotificationQueueService.queue_notification(notification_data, immediate=True)

            # Log rare offer
            NotificationQueueService.log_rare_offer(data['userId'], data['offerType'], data['coinAmount'])

            return jsonify({"success": True, "message": "Rare offer notification queued"}), 200

        except Exception as e:
            logger.error(f"Error handling rare offer notification: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @staticmethod
    def handle_ai_nudge(data: dict) -> tuple:
        """Handle AI nudge notification event"""
        try:
            # Validate required fields
            required_fields = ['userId', 'characterId', 'lastChatId', 'timestamp']
            if not all(field in data for field in required_fields):
                return jsonify({"success": False, "error": "Missing required fields"}), 400

            # Get character info
            character_name = NotificationQueueService.get_character_name(data['characterId'])

            # Create AI nudge notification
            notification_data = {
                'type': 'ai_nudge',
                'userId': data['userId'],
                'characterId': data['characterId'],
                'characterName': character_name,
                'chatId': data['lastChatId'],
                'personalizedHook': data.get('personalizedHook', f"{character_name} wants to continue your conversation"),
                'timestamp': data['timestamp']
            }

            # Queue with slight delay for natural feel
            delay_minutes = random.randint(5, 30)
            NotificationQueueService.queue_notification(notification_data, delay_minutes=delay_minutes)

            return jsonify({"success": True, "message": "AI nudge notification queued"}), 200

        except Exception as e:
            logger.error(f"Error handling AI nudge notification: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @staticmethod
    def handle_comment_reply(data: dict) -> tuple:
        """Handle comment reply notification event"""
        try:
            # Validate required fields
            required_fields = ['postId', 'replierId', 'parentCommentId', 'replyContent', 'replyId']
            if not all(field in data for field in required_fields):
                return jsonify({"success": False, "error": "Missing required fields: postId, replierId, parentCommentId, replyContent, replyId"}), 400

            post_id = data['postId']
            replier_id = data['replierId']
            parent_comment_id = data['parentCommentId']
            reply_content = data['replyContent']
            reply_id = data['replyId']

            # Get the post comments to find the parent comment
            post_comment_doc = db.collection('postComments').document(post_id).get()

            if not post_comment_doc.exists:
                return jsonify({"success": False, "error": "Post comments not found"}), 404

            comments = post_comment_doc.to_dict().get('comments', [])

            # Find the parent comment
            parent_comment = None
            post_author_id = None

            for comment in comments:
                if comment.get('id') == parent_comment_id:
                    parent_comment = comment
                    break

            if not parent_comment:
                return jsonify({"success": False, "error": "Parent comment not found"}), 404

            parent_comment_author_id = parent_comment.get('userId')
            parent_comment_author = parent_comment.get('author')

            # Validate that both users are human users (not AI)
            try:
                # Check if replier is human user
                replier_doc = db.collection('humanUsers').document(replier_id).get()
                if not replier_doc.exists:
                    return jsonify({"success": False, "error": "Replier is not a human user"}), 400

                # Check if parent comment author is human user
                parent_author_doc = db.collection('humanUsers').document(parent_comment_author_id).get()
                if not parent_author_doc.exists:
                    return jsonify({"success": False, "error": "Parent comment author is not a human user"}), 400

            except Exception as e:
                logger.error(f"Error validating user types: {e}")
                return jsonify({"success": False, "error": "Error validating user types"}), 500

            # Don't send notification if user is replying to their own comment
            if replier_id == parent_comment_author_id:
                return jsonify({"success": True, "message": "No notification sent - user replied to own comment"}), 200

            # Find the post owner
            collections = ['humanPosts', 'reposts', 'aiPosts']
            for collection in collections:
                try:
                    post_doc = db.collection(collection).document(post_id).get()
                    if post_doc.exists:
                        post_data = post_doc.to_dict()
                        post_author_id = post_data.get('user_document_id')
                        break
                except Exception as e:
                    continue

            # Get replier's username
            replier_username = NotificationQueueService.get_user_name(replier_id)

            # Create and store notification for the parent comment author
            notification_data = {
                'userId': parent_comment_author_id,
                'type': 'comment_reply',
                'title': '',
                'body': f'{replier_username} replied to your comment',
                'isRead': False,
                'createdAt': firestore.SERVER_TIMESTAMP,
                'data': {
                    'postId': post_id,
                    'parentCommentId': parent_comment_id,
                    'parentCommentAuthor': parent_comment_author,
                    'parentCommentAuthorId': parent_comment_author_id,
                    'replyId': reply_id,
                    'replierId': replier_id,
                    'replierUsername': replier_username,
                    'replyContent': reply_content,
                    'postAuthorId': post_author_id
                }
            }

            # Store notification in Firestore
            notification_ref = db.collection('notifications').add(notification_data)
            notification_id = notification_ref[1].id

            # Send push notification directly
            try:
                # Get the parent comment author's FCM tokens
                parent_user_doc = db.collection('humanUsers').document(parent_comment_author_id).get()
                if parent_user_doc.exists:
                    parent_user_data = parent_user_doc.to_dict()
                    fcm_tokens = parent_user_data.get('fcmTokens', [])

                    if fcm_tokens:
                        # Create push notification message - use replier name as title, reply content as body
                        title = f'{replier_username} replied to your comment'
                        body = reply_content[:100] + ('...' if len(reply_content) > 100 else '')  # Truncate if too long

                        # Send to all user's devices
                        for token in fcm_tokens:
                            try:
                                message = messaging.Message(
                                    notification=messaging.Notification(
                                        title=title,
                                        body=body,
                                    ),
                                    data={
                                        'type': 'comment_reply',
                                        'postId': post_id,
                                        'parentCommentId': parent_comment_id,
                                        'parentCommentAuthor': parent_comment_author,
                                        'parentCommentAuthorId': parent_comment_author_id,
                                        'replyId': reply_id,
                                        'replierId': replier_id,
                                        'replierUsername': replier_username,
                                        'replyContent': reply_content,
                                        'notificationId': notification_id
                                    },
                                    token=token,
                                )

                                response = messaging.send(message)
                                logger.info(f"Push notification sent successfully: {response}")

                            except messaging.UnregisteredError:
                                # Remove invalid token
                                logger.warning(f"Removing invalid FCM token for user {parent_comment_author_id}")
                                parent_user_ref = db.collection('humanUsers').document(parent_comment_author_id)
                                parent_user_ref.update({
                                    'fcmTokens': firestore.ArrayRemove([token])
                                })
                            except Exception as token_error:
                                logger.error(f"Error sending push notification to token {token}: {token_error}")
                    else:
                        logger.warning(f"No FCM tokens found for user: {parent_comment_author_id}")
                else:
                    logger.warning(f"Parent comment author not found: {parent_comment_author_id}")

            except Exception as e:
                logger.error(f"Error sending push notification for comment reply: {e}")
                # Continue even if push notification fails

            return jsonify({
                "success": True,
                "message": "Comment reply notification sent successfully",
                "notificationId": notification_id
            }), 200

        except Exception as ex:
            logger.error("Error triggering comment reply notification: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500
