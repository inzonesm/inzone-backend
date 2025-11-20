# services/ai/engagement_service.py
from flask import jsonify
from google.cloud import firestore
from dependencies import db
from datetime import datetime, timedelta
import logging
import random

logger = logging.getLogger(__name__)


class AIEngagementService:
    """Service for AI user engagement operations"""

    def __init__(self, inzone_ai_service):
        """
        Initialize with InZoneAIEngagementService instance

        Args:
            inzone_ai_service: The InZoneAIEngagementService instance
        """
        self.inzone_ai_service = inzone_ai_service

    def send_dm(self, data: dict) -> tuple:
        """
        AI user sends a DM using existing conversations system

        Args:
            data: Dictionary containing ai_user_id and target_user_id

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            ai_user_id = data.get('ai_user_id')
            target_user_id = data.get('target_user_id')

            if not ai_user_id or not target_user_id:
                return jsonify({"success": False, "error": "Missing required fields"}), 400

            # Check daily limits
            can_interact = self.inzone_ai_service.check_ai_daily_limit(ai_user_id)
            if not can_interact:
                return jsonify({"success": False, "error": "Daily interaction limit reached"}), 429

            # Get AI user details
            ai_user_doc = db.collection('aiUsers').document(ai_user_id).get()
            ai_user = None

            if ai_user_doc.exists:
                ai_user = ai_user_doc.to_dict()
                ai_user['username'] = ai_user_id
            else:
                # Try popularCharacters collection
                popular_char_doc = db.collection('popularCharacters').document(ai_user_id).get()
                if popular_char_doc.exists:
                    ai_user = popular_char_doc.to_dict()
                    ai_user['username'] = ai_user.get('name', ai_user_id)
                else:
                    return jsonify({"success": False, "error": "AI user not found"}), 404

            # Get target user details
            target_user_doc = db.collection('humanUsers').document(target_user_id).get()
            if not target_user_doc.exists:
                return jsonify({"success": False, "error": "Target user not found"}), 404

            target_user = target_user_doc.to_dict()

            # Create conversation ID
            participants = sorted([ai_user_id, target_user_id])
            conversation_id = f"{participants[0]}_{participants[1]}"

            # Check if conversation exists and get context
            conversation_ref = db.collection('conversations').document(conversation_id)
            conversation_doc = conversation_ref.get()

            conversation_context = None
            if conversation_doc.exists:
                # Get recent messages for context
                messages_ref = conversation_ref.collection('messages').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(5)
                recent_messages = []

                for msg_doc in messages_ref.stream():
                    msg_data = msg_doc.to_dict()
                    recent_messages.append({
                        'senderId': msg_data.get('senderId'),
                        'text': msg_data.get('text', ''),
                        'timestamp': msg_data.get('timestamp')
                    })

                # Count total messages
                all_messages_ref = conversation_ref.collection('messages')
                total_message_count = len(list(all_messages_ref.stream()))

                conversation_context = {
                    'message_count': total_message_count,
                    'recent_messages': recent_messages,
                    'has_conversation': True
                }

            # Generate DM message
            dm_content = self.inzone_ai_service.generate_ai_dm_message(ai_user, target_user, conversation_context)

            # Check similarity to avoid repetition
            if conversation_context and conversation_context.get('recent_messages'):
                recent_texts = [msg.get('text', '').lower() for msg in conversation_context['recent_messages']]
                dm_lower = dm_content.lower()

                for recent_text in recent_texts:
                    if recent_text and len(recent_text) > 10:
                        dm_words = set(dm_lower.split())
                        recent_words = set(recent_text.split())
                        if len(dm_words.intersection(recent_words)) / max(len(dm_words), len(recent_words)) > 0.6:
                            dm_content = self.inzone_ai_service.generate_ai_dm_message(ai_user, target_user, conversation_context)
                            break

            # Create message
            new_message = {
                'text': dm_content,
                'senderId': ai_user_id,
                'senderName': ai_user.get('name', ai_user_id),
                'timestamp': firestore.SERVER_TIMESTAMP,
                'isRead': False,
                'isAIGenerated': True
            }

            conversation_ref.collection('messages').add(new_message)

            # Update conversation metadata
            conversation_ref.set({
                'lastMessage': dm_content,
                'lastMessageTime': firestore.SERVER_TIMESTAMP,
                'participants': [ai_user_id, target_user_id],
                'participantNames': {
                    ai_user_id: ai_user.get('name', ai_user_id),
                    target_user_id: target_user.get('name', target_user_id)
                },
                'lastUpdated': firestore.SERVER_TIMESTAMP,
                'isAIConversation': True
            }, merge=True)

            # Store DM notification
            try:
                notification_doc = {
                    'userId': target_user_id,
                    'type': 'direct_message',
                    'title': ai_user.get('name', ai_user_id),
                    'body': dm_content[:100] + '...' if len(dm_content) > 100 else dm_content,
                    'isRead': False,
                    'createdAt': firestore.SERVER_TIMESTAMP,
                    'data': {
                        'chatId': conversation_id,
                        'senderId': ai_user_id,
                        'senderName': ai_user.get('name', ai_user_id),
                        'messageContent': dm_content
                    }
                }
                db.collection('notifications').add(notification_doc)
            except Exception as notif_error:
                logger.error(f"Error creating DM notification: {notif_error}")

            return jsonify({
                "success": True,
                "data": {
                    "conversation_id": conversation_id,
                    "message": dm_content,
                    "ai_user": ai_user.get('name'),
                    "target_user": target_user.get('name')
                }
            }), 200

        except Exception as ex:
            logger.error("Error sending AI DM: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    def like_post(self, data: dict) -> tuple:
        """
        AI user likes a post

        Args:
            data: Dictionary containing ai_user_id, post_id, post_collection

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            ai_user_id = data.get('ai_user_id')
            post_id = data.get('post_id')
            post_collection = data.get('post_collection', 'humanPosts')

            if not ai_user_id or not post_id:
                return jsonify({"success": False, "error": "Missing required fields"}), 400

            # Check daily limits
            can_interact = self.inzone_ai_service.check_ai_daily_limit(ai_user_id)
            if not can_interact:
                return jsonify({"success": False, "error": "Daily interaction limit reached"}), 429

            # Verify AI user exists
            ai_user_doc = db.collection('aiUsers').document(ai_user_id).get()
            if not ai_user_doc.exists:
                return jsonify({"success": False, "error": "AI user not found"}), 404

            # Verify post exists
            post_doc = db.collection(post_collection).document(post_id).get()
            if not post_doc.exists:
                return jsonify({"success": False, "error": "Post not found"}), 404

            # Check if already liked
            existing_like = list(db.collection('postLikes').where('user_id', '==', ai_user_id).where('post_id', '==', post_id).limit(1).get())
            if existing_like:
                return jsonify({"success": False, "error": "Post already liked by this AI user"}), 400

            # Add like
            like_data = {
                "user_id": ai_user_id,
                "post_id": post_id,
                "timestamp": firestore.SERVER_TIMESTAMP,
                "isAIGenerated": True
            }

            db.collection('postLikes').add(like_data)

            # Increment likes count
            post_ref = db.collection(post_collection).document(post_id)
            post_ref.update({"likes": firestore.Increment(1)})

            ai_user = ai_user_doc.to_dict()
            return jsonify({
                "success": True,
                "data": {
                    "post_id": post_id,
                    "ai_user": ai_user.get('name'),
                    "action": "liked"
                }
            }), 200

        except Exception as ex:
            logger.error("Error AI liking post: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    def comment_on_post(self, data: dict) -> tuple:
        """
        AI user comments on a post

        Args:
            data: Dictionary containing ai_user_id, post_id, post_collection

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            ai_user_id = data.get('ai_user_id')
            post_id = data.get('post_id')
            post_collection = data.get('post_collection', 'humanPosts')

            if not ai_user_id or not post_id:
                return jsonify({"success": False, "error": "Missing required fields"}), 400

            # Check daily limits
            can_interact = self.inzone_ai_service.check_ai_daily_limit(ai_user_id)
            if not can_interact:
                return jsonify({"success": False, "error": "Daily interaction limit reached"}), 429

            # Get AI user details
            ai_user_doc = db.collection('aiUsers').document(ai_user_id).get()
            if not ai_user_doc.exists:
                return jsonify({"success": False, "error": "AI user not found"}), 404

            ai_user = ai_user_doc.to_dict()
            ai_user['username'] = ai_user_id

            # Get post details
            post_doc = db.collection(post_collection).document(post_id).get()
            if not post_doc.exists:
                return jsonify({"success": False, "error": "Post not found"}), 404

            post_data = post_doc.to_dict()
            post_data['id'] = post_id
            post_data['collection'] = post_collection

            # Get trending insights
            trends = self.inzone_ai_service.get_trending_content_insights()

            # Generate contextual comment
            comment_content = self.inzone_ai_service.generate_contextual_ai_comment(ai_user, post_data, trends)

            # Add comment
            comment_data = {
                "postId": post_id,
                "userId": ai_user_id,
                "content": comment_content,
                "createdAt": firestore.SERVER_TIMESTAMP,
                "isAIGenerated": True,
                "aiUserName": ai_user.get('name', ai_user_id)
            }

            doc_ref = db.collection('postComments').add(comment_data)

            return jsonify({
                "success": True,
                "data": {
                    "comment_id": doc_ref[1].id,
                    "post_id": post_id,
                    "comment": comment_content,
                    "ai_user": ai_user.get('name'),
                    "post_author": post_data.get('user_name'),
                    "post_collection": post_collection
                }
            }), 200

        except Exception as ex:
            logger.error("Error AI commenting on post: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    def get_engagement_stats(self, ai_user_id: str = None, days: int = 7) -> tuple:
        """
        Get statistics on AI engagement activities

        Args:
            ai_user_id: Optional AI user ID to filter by
            days: Number of days to look back

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            start_date = datetime.now() - timedelta(days=days)

            stats = {
                'comments': 0,
                'likes': 0,
                'dms': 0,
                'total_interactions': 0
            }

            if ai_user_id:
                # Get stats for specific AI user
                comments_ref = db.collection('postComments').where('userId', '==', ai_user_id).where('createdAt', '>=', start_date)
                stats['comments'] = len(list(comments_ref.stream()))

                likes_ref = db.collection('postLikes').where('user_id', '==', ai_user_id).where('timestamp', '>=', start_date)
                stats['likes'] = len(list(likes_ref.stream()))

                # Count DMs
                conversations_ref = db.collection('conversations')
                dm_count = 0
                for conv_doc in conversations_ref.stream():
                    conv_data = conv_doc.to_dict()
                    participants = conv_data.get('participants', [])
                    if ai_user_id in participants:
                        messages_ref = conv_doc.reference.collection('messages')
                        ai_messages = messages_ref.where('senderId', '==', ai_user_id).where('timestamp', '>=', start_date)
                        if len(list(ai_messages.stream())) > 0:
                            dm_count += 1
                stats['dms'] = dm_count

            stats['total_interactions'] = stats['comments'] + stats['likes'] + stats['dms']

            return jsonify({"success": True, "data": stats}), 200

        except Exception as ex:
            logger.error("Error getting AI engagement stats: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    def get_popular_characters(self, limit: int = 50) -> tuple:
        """
        Get available popular characters for DM conversations

        Args:
            limit: Maximum number of characters to return

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            chars_ref = db.collection('popularCharacters').limit(limit)
            characters = []

            for doc in chars_ref.stream():
                char_data = doc.to_dict()
                characters.append({
                    'id': doc.id,
                    'name': char_data.get('name', 'Unknown Character'),
                    'personality': char_data.get('personality', ''),
                    'greeting': char_data.get('greeting', 'Hello!'),
                    'profile_picture_url': char_data.get('profile_picture_url', ''),
                    'votes': char_data.get('votes', 0),
                    'numberOfChats': char_data.get('numberOfChats', 0),
                    'collection_type': 'popularCharacters'
                })

            return jsonify({"success": True, "data": characters}), 200

        except Exception as ex:
            logger.error("Error getting popular characters: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500
