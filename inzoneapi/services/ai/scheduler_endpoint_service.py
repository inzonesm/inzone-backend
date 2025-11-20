# services/ai/scheduler_endpoint_service.py
from datetime import datetime, timezone
from google.cloud import firestore
import logging

logger = logging.getLogger(__name__)


class AISchedulerEndpointService:
    """Service for AI scheduler endpoints - handles scheduling and execution of AI engagement"""

    def __init__(self, ai_scheduler, db):
        """
        Initialize the scheduler endpoint service

        Args:
            ai_scheduler: The AIScheduler instance
            db: Firestore database instance
        """
        self.ai_scheduler = ai_scheduler
        self.db = db
        self._is_running = False  # Concurrency protection for auto-scheduling

    def schedule_character_engagement(self, data: dict) -> tuple:
        """
        Manually trigger engagement for a specific character

        Args:
            data: Dict containing 'character_id'

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            character_id = data.get('character_id')

            if not character_id:
                return {"success": False, "error": "Character ID required"}, 400

            result = self.ai_scheduler.schedule_character_engagement(character_id)
            return result, 200 if result.get('success') else 500

        except Exception as e:
            logger.error(f"Error in character engagement API: {e}")
            return {"success": False, "error": str(e)}, 500

    def schedule_all_characters(self, data: dict) -> tuple:
        """
        Trigger engagement for all popular characters

        Args:
            data: Dict containing optional 'limit' (default: 20)

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            limit = data.get('limit', 20)

            result = self.ai_scheduler.schedule_all_characters(limit=limit)
            return result, 200 if result.get('success') else 500

        except Exception as e:
            logger.error(f"Error in all characters engagement API: {e}")
            return {"success": False, "error": str(e)}, 500

    def schedule_engagement_auto(self, data: dict) -> tuple:
        """
        Auto-schedule and EXECUTE engagement with concurrency protection and rate limiting

        Args:
            data: Request data (optional)

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            # Simple in-memory lock to prevent concurrent executions
            if self._is_running:
                return {
                    'success': False,
                    'error': 'AI engagement already running',
                    'message': 'Another instance is currently executing AI engagement. Please wait and try again.',
                    'suggestion': 'Wait a few minutes before trying again.'
                }, 429

            # Set running flag
            self._is_running = True

            try:
                # Check if we've run recently (additional rate limiting)
                last_run_ref = self.db.collection('system_state').document('last_ai_engagement_run')
                last_run_doc = last_run_ref.get()

                if last_run_doc.exists:
                    last_run_data = last_run_doc.to_dict()
                    last_run_time = last_run_data.get('timestamp')

                    if last_run_time:
                        # Handle timezone-aware timestamps
                        if hasattr(last_run_time, 'tzinfo') and last_run_time.tzinfo is not None:
                            last_run_time = last_run_time.replace(tzinfo=None)

                        time_since_last_run = (datetime.now() - last_run_time).total_seconds()

                        # Prevent runs closer than 30 minutes apart (1800 seconds)
                        if time_since_last_run < 1800:
                            return {
                                'success': False,
                                'error': 'Rate limit exceeded',
                                'message': f'Last run was {int(time_since_last_run)} seconds ago. Minimum interval is 1800 seconds.',
                                'last_run_time': str(last_run_time),
                                'time_since_last_run': int(time_since_last_run)
                            }, 429

                # Execute the scheduling and actual interactions
                schedule_result = self.ai_scheduler.schedule_all_characters(limit=50)

                if not schedule_result['success']:
                    return schedule_result, 500

                executed_interactions = []
                total_executed = 0
                errors = []

                # Run DM monitoring FIRST to catch immediate responses
                try:
                    print('🔄 Running DM monitoring to catch pending responses...')
                    dm_monitor_result = self.ai_scheduler.monitor_and_respond_to_dms()

                    if dm_monitor_result['success']:
                        dm_responses = dm_monitor_result.get('responses_sent', 0)
                        total_executed += dm_responses

                        # Add DM responses to executed interactions
                        for response_detail in dm_monitor_result.get('response_details', []):
                            executed_interactions.append({
                                'type': 'dm_response',
                                'character': response_detail.get('ai_character', 'Unknown'),
                                'target_user': response_detail.get('human_user', 'Unknown'),
                                'conversation_id': response_detail.get('conversation_id', ''),
                                'immediate_response': True
                            })

                        print(f'✅ DM monitoring sent {dm_responses} immediate responses')
                    else:
                        print(f'⚠️ DM monitoring had issues: {dm_monitor_result.get("error", "Unknown")}')
                except Exception as dm_error:
                    print(f'❌ DM monitoring error: {dm_error}')
                    errors.append({
                        'type': 'dm_monitoring',
                        'error': str(dm_error)
                    })

                # Execute each character's scheduled interactions
                for character_data in schedule_result.get('characters', []):
                    character_id = character_data['character_id']
                    character_name = character_data['character_name']

                    for interaction in character_data.get('scheduled_interactions', []):
                        try:
                            interaction_type = interaction['interaction_type']
                            success = False

                            if interaction_type == 'like' and 'target_post_id' in interaction:
                                success = self.ai_scheduler.execute_like_interaction(
                                    character_id,
                                    interaction['target_post_id'],
                                    interaction.get('post_collection', 'humanPosts')
                                )
                                if success:
                                    executed_interactions.append({
                                        'type': 'like',
                                        'character': character_name,
                                        'post_id': interaction['target_post_id']
                                    })
                                    total_executed += 1

                            elif interaction_type == 'comment' and 'target_post_id' in interaction:
                                success = self.ai_scheduler.execute_comment_interaction(
                                    character_id,
                                    interaction['target_post_id'],
                                    interaction.get('post_collection', 'humanPosts')
                                )
                                if success:
                                    executed_interactions.append({
                                        'type': 'comment',
                                        'character': character_name,
                                        'post_id': interaction['target_post_id']
                                    })
                                    total_executed += 1

                            elif interaction_type == 'dm' and 'target_user_id' in interaction:
                                success = self.ai_scheduler.execute_dm_interaction(
                                    character_id,
                                    interaction['target_user_id']
                                )
                                if success:
                                    executed_interactions.append({
                                        'type': 'dm',
                                        'character': character_name,
                                        'target_user': interaction['target_user_id']
                                    })
                                    total_executed += 1

                        except Exception as e:
                            errors.append({
                                'character': character_name,
                                'interaction_type': interaction.get('interaction_type'),
                                'error': str(e)
                            })
                            logger.error(f"Error executing interaction for {character_name}: {e}")

                # Update last run timestamp
                last_run_ref.set({
                    'timestamp': firestore.SERVER_TIMESTAMP,
                    'total_executed': total_executed,
                    'total_scheduled': schedule_result.get('total_interactions_scheduled', 0)
                }, merge=True)

                result = {
                    'success': True,
                    'total_characters': schedule_result.get('total_characters', 0),
                    'total_interactions_scheduled': schedule_result.get('total_interactions_scheduled', 0),
                    'total_executed': total_executed,
                    'executed_interactions': executed_interactions,
                    'errors': errors,
                    'execution_summary': f"Executed {total_executed}/{schedule_result.get('total_interactions_scheduled', 0)} scheduled interactions"
                }

                logger.info(f"AI engagement completed: {total_executed} interactions executed for {result['total_characters']} characters")
                return result, 200

            finally:
                # Always clear the running flag
                self._is_running = False

        except Exception as e:
            # Make sure to clear the flag even if there's an exception
            self._is_running = False
            logger.error(f"Error in auto engagement scheduling: {e}")
            return {"success": False, "error": str(e)}, 500

    def get_engagement_status(self) -> tuple:
        """
        Get current engagement status and counts

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            # Get count of popular characters
            chars_ref = self.db.collection('popularCharacters')
            char_count = len(list(chars_ref.limit(100).stream()))

            # Get recent activity counts (use simple queries to avoid index issues)
            today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

            # Count today's likes (fetch all recent and filter in Python)
            likes_docs = list(self.db.collection('postLikes').limit(500).stream())
            likes_today = sum(1 for doc in likes_docs
                             if doc.to_dict().get('is_ai', False) and
                             doc.to_dict().get('timestamp', datetime.min.replace(tzinfo=timezone.utc)) >= today)

            # Count today's comments (fetch all recent and filter in Python)
            comments_docs = list(self.db.collection('postComments').limit(500).stream())
            comments_today = sum(1 for doc in comments_docs
                               if doc.to_dict().get('is_ai', False) and
                               doc.to_dict().get('timestamp', datetime.min.replace(tzinfo=timezone.utc)) >= today)

            # Count today's DMs (fetch all recent and filter in Python)
            dms_docs = list(self.db.collection('messages').limit(500).stream())
            dms_today = sum(1 for doc in dms_docs
                           if doc.to_dict().get('is_ai', False) and
                           doc.to_dict().get('timestamp', datetime.min.replace(tzinfo=timezone.utc)) >= today)

            return {
                "success": True,
                "data": {
                    "total_characters": char_count,
                    "today_stats": {
                        "likes": likes_today,
                        "comments": comments_today,
                        "dms": dms_today,
                        "total_interactions": likes_today + comments_today + dms_today
                    },
                    "scheduler_config": {
                        "comments_range": f"{self.ai_scheduler.limits.comments_min}-{self.ai_scheduler.limits.comments_max}",
                        "likes_range": f"{self.ai_scheduler.limits.likes_min}-{self.ai_scheduler.limits.likes_max}",
                        "max_dms": self.ai_scheduler.limits.dms_max
                    }
                }
            }, 200

        except Exception as e:
            logger.error(f"Error getting engagement status: {e}")
            return {"success": False, "error": str(e)}, 500

    def dm_auto_responder(self, data: dict) -> tuple:
        """
        SINGLE-CONVERSATION DM RESPONSE: Responds to a specific conversation when Flutter app triggers it.
        Use this when a human sends a message and you want an immediate AI response for that specific conversation.

        Args:
            data: Dict containing 'user_id', 'ai_character_id', 'message_text', 'conversation_id' (optional)

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            from datetime import datetime, timezone

            user_id = data.get('user_id')
            ai_character_id = data.get('ai_character_id')
            message_text = data.get('message_text', '')
            conversation_id = data.get('conversation_id')

            if not user_id or not ai_character_id:
                return {'success': False, 'error': 'Missing user_id or ai_character_id'}, 400

            # Generate conversation ID if not provided
            if not conversation_id:
                participants = sorted([user_id, ai_character_id])
                conversation_id = f"{participants[0]}_{participants[1]}"

            # Get AI character data
            ai_char_ref = self.db.collection('popularCharacters').document(ai_character_id)
            ai_char_doc = ai_char_ref.get()

            if not ai_char_doc.exists:
                return {'success': False, 'error': 'AI character not found'}, 404

            ai_character = ai_char_doc.to_dict()

            # Get human user data
            human_ref = self.db.collection('humanUsers').document(user_id)
            human_doc = human_ref.get()

            if not human_doc.exists:
                return {'success': False, 'error': 'Human user not found'}, 404

            human_data = human_doc.to_dict()

            # Get conversation history
            conv_ref = self.db.collection('conversations').document(conversation_id)
            conv_doc = conv_ref.get()

            # Ensure conversation exists
            if not conv_doc.exists:
                logger.info(f"Creating new conversation: {conversation_id}")
                from google.cloud import firestore
                conv_ref.set({
                    'participants': [user_id, ai_character_id],
                    'participantNames': {
                        user_id: human_data.get('name', user_id),
                        ai_character_id: ai_character.get('name', ai_character_id)
                    },
                    'lastMessage': message_text,
                    'lastMessageTime': firestore.SERVER_TIMESTAMP,
                    'lastUpdated': firestore.SERVER_TIMESTAMP,
                    'isAIConversation': True
                })

            messages_ref = conv_ref.collection('messages')
            from google.cloud import firestore
            recent_messages = messages_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(5).stream()
            message_history = [msg.to_dict() for msg in recent_messages]

            # Generate and send AI response
            logger.info(f"🚀 DM Auto-Responder: {ai_character.get('name', ai_character_id)} responding to {human_data.get('name', user_id)}")
            logger.info(f"Message history length: {len(message_history)}")

            success = self.ai_scheduler.send_immediate_dm_response(
                ai_character_id,
                user_id,
                conversation_id,
                message_history,
                ai_character
            )

            if success:
                return {
                    'success': True,
                    'message': 'AI auto-response sent',
                    'ai_character_name': ai_character.get('name', ai_character_id),
                    'conversation_id': conversation_id,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }, 200
            else:
                return {'success': False, 'error': 'Failed to generate response'}, 500

        except Exception as e:
            logger.error(f"Error in DM auto responder: {e}")
            return {'success': False, 'error': str(e)}, 500

    def monitor_and_respond_dms(self) -> tuple:
        """
        MASS DM MONITORING: Monitors ALL conversations across ALL AI characters and responds automatically.
        Use this for background monitoring to catch any missed messages. Includes notifications.

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            # Monitor conversations and respond to pending DMs
            result = self.ai_scheduler.monitor_and_respond_to_dms()

            if result['success']:
                return {
                    'success': True,
                    'message': f"Monitored conversations and sent {result['responses_sent']} immediate responses",
                    'responses_sent': result['responses_sent'],
                    'characters_checked': result.get('characters_checked', 0),
                    'response_details': result.get('response_details', []),
                    'timestamp': result.get('timestamp'),
                    'type': 'dm_monitoring'
                }, 200
            else:
                return {
                    'success': False,
                    'error': result.get('error', 'Unknown error'),
                    'type': 'dm_monitoring'
                }, 500

        except Exception as e:
            logger.error(f"Error in DM monitoring: {e}")
            return {
                'success': False,
                'error': str(e),
                'type': 'dm_monitoring'
            }, 500
