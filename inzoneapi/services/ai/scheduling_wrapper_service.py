# services/ai/scheduling_wrapper_service.py
from flask import jsonify
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class AISchedulingWrapperService:
    """Service wrapper for AI scheduler operations"""

    def __init__(self, ai_scheduler):
        """
        Initialize with AI scheduler instance

        Args:
            ai_scheduler: The AI scheduler instance
        """
        self.ai_scheduler = ai_scheduler

    def schedule_character_engagement(self, data: dict) -> tuple:
        """
        Schedule AI engagement for a specific popular character

        Args:
            data: Dictionary containing character_id

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            character_id = data.get('character_id')

            if not character_id:
                return jsonify({"success": False, "error": "character_id is required"}), 400

            result = self.ai_scheduler.schedule_character_engagement(character_id)

            if result['success']:
                return jsonify({"success": True, "data": result}), 200
            else:
                return jsonify({"success": False, "error": result.get('error', 'Unknown error')}), 400

        except Exception as ex:
            logger.error("Error scheduling character engagement: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    def schedule_all_characters(self, data: dict) -> tuple:
        """
        Schedule AI engagement for all popular characters

        Args:
            data: Dictionary containing optional limit

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            limit = data.get('limit', 20)

            result = self.ai_scheduler.schedule_all_characters(limit)

            if result['success']:
                return jsonify({"success": True, "data": result}), 200
            else:
                return jsonify({"success": False, "error": result.get('error', 'Unknown error')}), 400

        except Exception as ex:
            logger.error("Error scheduling all characters: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    def execute_scheduled_engagement(self, data: dict) -> tuple:
        """
        Execute scheduled AI engagement with proper rate limiting and cooldowns

        Args:
            data: Dictionary containing character_limit and force_execute

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            from dependencies import db, openai_client
            from inzone_ai_engagement import InZoneAIEngagementService
            import random

            character_limit = data.get('character_limit', 10)
            force_execute = data.get('force_execute', False)

            # Schedule all characters
            schedule_result = self.ai_scheduler.schedule_all_characters(character_limit)

            if not schedule_result['success']:
                return jsonify({"success": False, "error": "Failed to create schedule"}), 400

            executed_interactions = []
            errors = []

            # Helper function to get user data
            def get_user_data(user_id):
                # Try humanUsers first
                doc = db.collection('humanUsers').document(user_id).get()
                if doc.exists:
                    data = doc.to_dict()
                    data['id'] = doc.id
                    return data
                # Try popularCharacters
                doc = db.collection('popularCharacters').document(user_id).get()
                if doc.exists:
                    data = doc.to_dict()
                    data['id'] = doc.id
                    return data
                return None

            # Execute scheduled interactions
            for character_data in schedule_result['characters']:
                character_id = character_data['character_id']
                character_name = character_data['character_name']

                for interaction in character_data['scheduled_interactions']:
                    target_user_id = interaction['target_user_id']
                    interaction_type = interaction['interaction_type']

                    try:
                        if interaction_type == 'dm':
                            ai_user_data = get_user_data(character_id)
                            target_user_data = get_user_data(target_user_id)

                            if ai_user_data and target_user_data:
                                ai_service = InZoneAIEngagementService(db, openai_client)
                                message = ai_service.generate_ai_dm_message(ai_user_data, target_user_data)
                                conversation_id = f"{character_id}_{target_user_id}"

                                conv_ref = db.collection('conversations').document(conversation_id)
                                conv_doc = conv_ref.get()

                                if not conv_doc.exists:
                                    conv_ref.set({
                                        'participants': [character_id, target_user_id],
                                        'created_at': datetime.now(),
                                        'last_message_at': datetime.now()
                                    })

                                message_ref = conv_ref.collection('messages').add({
                                    'sender_id': character_id,
                                    'message': message,
                                    'timestamp': datetime.now(),
                                    'read': False
                                })

                                executed_interactions.append({
                                    'type': 'dm',
                                    'character': character_name,
                                    'target_user': target_user_data.get('name', 'Unknown'),
                                    'message': message
                                })

                                from ai_nudge_scheduler import EngagementType
                                self.ai_scheduler.log_interaction(
                                    character_id,
                                    target_user_id,
                                    EngagementType.DM,
                                    {'conversation_id': conversation_id}
                                )

                        elif interaction_type == 'like':
                            posts_ref = db.collection('humanPosts').where('user_id', '==', target_user_id).limit(3)
                            posts = list(posts_ref.stream())

                            if posts:
                                post_doc = random.choice(posts)
                                post_ref = db.collection('humanPosts').document(post_doc.id)

                                like_data = {
                                    'user_id': character_id,
                                    'timestamp': datetime.now()
                                }
                                post_ref.collection('likes').document(character_id).set(like_data)

                                post_data = post_doc.to_dict()
                                current_likes = post_data.get('likes', 0)
                                post_ref.update({'likes': current_likes + 1})

                                executed_interactions.append({
                                    'type': 'like',
                                    'character': character_name,
                                    'post_author': post_data.get('author_name', 'Unknown'),
                                    'post_id': post_doc.id
                                })

                                from ai_nudge_scheduler import EngagementType
                                self.ai_scheduler.log_interaction(
                                    character_id,
                                    target_user_id,
                                    EngagementType.LIKE,
                                    {'post_id': post_doc.id}
                                )

                        elif interaction_type == 'comment':
                            posts_ref = db.collection('humanPosts').where('user_id', '==', target_user_id).limit(3)
                            posts = list(posts_ref.stream())

                            if posts:
                                post_doc = random.choice(posts)
                                post_data = post_doc.to_dict()

                                ai_service = InZoneAIEngagementService(db, openai_client)
                                ai_user_data = get_user_data(character_id)
                                trends = ai_service.get_trending_content_insights()
                                comment_text = ai_service.generate_contextual_ai_comment(ai_user_data, post_data, trends)

                                comment_data = {
                                    'user_id': character_id,
                                    'comment': comment_text,
                                    'timestamp': datetime.now(),
                                    'likes': 0
                                }

                                post_ref = db.collection('humanPosts').document(post_doc.id)
                                comment_ref = post_ref.collection('comments').add(comment_data)

                                current_comments = post_data.get('comments', 0)
                                post_ref.update({'comments': current_comments + 1})

                                executed_interactions.append({
                                    'type': 'comment',
                                    'character': character_name,
                                    'post_author': post_data.get('author_name', 'Unknown'),
                                    'comment': comment_text,
                                    'post_id': post_doc.id
                                })

                                from ai_nudge_scheduler import EngagementType
                                self.ai_scheduler.log_interaction(
                                    character_id,
                                    target_user_id,
                                    EngagementType.COMMENT,
                                    {'post_id': post_doc.id, 'comment_id': comment_ref[1].id}
                                )

                    except Exception as interaction_error:
                        errors.append({
                            'character': character_name,
                            'target': target_user_id,
                            'type': interaction_type,
                            'error': str(interaction_error)
                        })

            return jsonify({
                "success": True,
                "data": {
                    "scheduled_plan": schedule_result,
                    "executed_interactions": executed_interactions,
                    "total_executed": len(executed_interactions),
                    "errors": errors,
                    "execution_timestamp": datetime.now().isoformat()
                }
            }), 200

        except Exception as ex:
            logger.error("Error executing scheduled engagement: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500
