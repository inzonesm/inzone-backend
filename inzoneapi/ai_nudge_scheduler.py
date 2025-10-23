from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
import logging
import random
from typing import Dict, List
from notification_service import notification_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AINudgeScheduler:
    def __init__(self):
        # Initialize Firebase if not already done
        if not firebase_admin._apps:
            cred = credentials.Certificate('key.json')
            firebase_admin.initialize_app(cred)
        
        self.db = firestore.client()
        
        # AI nudge templates for personalization
        self.nudge_templates = [
            "⚡ {character_name}'s still arguing about your last spell. Jump back in?",
            "Your team's debating the MVP right now. Got a take?",
            "{character_name} just dropped a hot take. What's your response?",
            "The conversation heated up after you left. Join back in!",
            "🔥 {character_name} is waiting for your comeback",
            "Your last message started quite the debate. See what's happening!",
        ]
        
        # Character-specific hooks
        self.character_hooks = {
            'default': [
                "There's more to discuss...",
                "The conversation isn't over yet",
                "Your perspective is needed",
            ]
        }
    
    def schedule_daily_ai_nudges(self):
        """Schedule AI nudges for inactive users (run daily)"""
        try:
            logger.info("Starting daily AI nudge scheduling...")
            
            # Get users who haven't been active in the last 24 hours
            yesterday = datetime.utcnow() - timedelta(days=1)
            
            # Query for inactive users
            inactive_users = self._get_inactive_users(yesterday)
            
            for user_data in inactive_users:
                user_id = user_data['user_id']
                
                # Check if user has AI nudges enabled
                if not self._is_ai_nudges_enabled(user_id):
                    continue
                
                # Check daily nudge limit
                if self._has_reached_daily_nudge_limit(user_id):
                    continue
                
                # Get user's last active chat
                last_chat = self._get_last_active_chat(user_id)
                if not last_chat:
                    continue
                
                # Create personalized nudge
                nudge_data = self._create_ai_nudge(user_id, last_chat)
                
                # Schedule the nudge
                self._schedule_nudge(user_id, nudge_data)
                
                # Update nudge counter
                self._increment_nudge_counter(user_id)
            
            logger.info(f"Scheduled AI nudges for {len(inactive_users)} users")
            
        except Exception as e:
            logger.error(f"Error scheduling AI nudges: {str(e)}")
    
    def _get_inactive_users(self, since: datetime) -> List[Dict]:
        """Get users who haven't been active since the given time"""
        try:
            # This would typically query user activity logs
            # For now, we'll use a simple query on user sessions
            
            users_query = (self.db.collection('users')
                          .where('lastActive', '<', since)
                          .limit(100))
            
            users = users_query.get()
            
            return [{'user_id': doc.id, **doc.to_dict()} for doc in users]
            
        except Exception as e:
            logger.error(f"Error getting inactive users: {str(e)}")
            return []
    
    def _is_ai_nudges_enabled(self, user_id: str) -> bool:
        """Check if user has AI nudges enabled"""
        try:
            user_doc = self.db.collection('users').document(user_id).get()
            if not user_doc.exists:
                return False
            
            user_data = user_doc.to_dict()
            prefs = user_data.get('notificationPrefs', {})
            categories = prefs.get('categories', {})
            ai_nudges = categories.get('aiNudges', {})
            
            return ai_nudges.get('enabled', True)
            
        except Exception as e:
            logger.error(f"Error checking AI nudges preference: {str(e)}")
            return False
    
    def _has_reached_daily_nudge_limit(self, user_id: str) -> bool:
        """Check if user has reached daily nudge limit"""
        try:
            today = datetime.utcnow().strftime('%Y-%m-%d')
            nudge_doc = self.db.collection('nudges').document(user_id).collection('daily').document(today).get()
            
            if not nudge_doc.exists:
                return False
            
            nudge_data = nudge_doc.to_dict()
            sent_count = nudge_data.get('sentCount', 0)
            
            # Get user's max per day setting
            user_doc = self.db.collection('users').document(user_id).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                prefs = user_data.get('notificationPrefs', {})
                categories = prefs.get('categories', {})
                ai_nudges = categories.get('aiNudges', {})
                max_per_day = ai_nudges.get('maxPerDay', 2)
            else:
                max_per_day = 2
            
            return sent_count >= max_per_day
            
        except Exception as e:
            logger.error(f"Error checking nudge limit: {str(e)}")
            return True  # Err on the safe side
    
    def _get_last_active_chat(self, user_id: str) -> Dict:
        """Get user's last active chat for personalization"""
        try:
            # Query user's recent chat activity
            chats_query = (self.db.collection('conversations')
                          .where('participants', 'array_contains', user_id)
                          .order_by('lastMessageTime', direction=firestore.Query.DESCENDING)
                          .limit(1))
            
            chats = chats_query.get()
            
            if not chats:
                return {}
            
            chat_data = chats[0].to_dict()
            chat_id = chats[0].id
            
            # Get chat details
            return {
                'chat_id': chat_id,
                'chat_name': chat_data.get('groupName', 'Chat'),
                'is_group': chat_data.get('isGroupChat', False),
                'last_message': chat_data.get('lastMessage', ''),
                'participants': chat_data.get('participants', []),
            }
            
        except Exception as e:
            logger.error(f"Error getting last active chat: {str(e)}")
            return {}
    
    def _create_ai_nudge(self, user_id: str, chat_data: Dict) -> Dict:
        """Create personalized AI nudge data"""
        try:
            # Get character info from the chat
            character_name = "Your AI friend"
            character_id = "default"
            
            if chat_data.get('is_group'):
                # For group chats, use group name
                character_name = chat_data.get('chat_name', 'The group')
            else:
                # For DM chats, try to get AI character info
                participants = chat_data.get('participants', [])
                for participant in participants:
                    if participant != user_id:
                        # This would be the AI character
                        character_doc = self.db.collection('aiCharacters').document(participant).get()
                        if character_doc.exists:
                            char_data = character_doc.to_dict()
                            character_name = char_data.get('name', character_name)
                            character_id = participant
                        break
            
            # Select random template
            template = random.choice(self.nudge_templates)
            
            # Create personalized hook
            personalized_hook = template.format(character_name=character_name)
            
            # Add context from last message if available
            last_message = chat_data.get('last_message', '')
            if last_message and len(last_message) > 20:
                snippet = last_message[:50] + "..." if len(last_message) > 50 else last_message
                personalized_hook += f" About: '{snippet}'"
            
            return {
                'type': 'ai_nudge',
                'userId': user_id,
                'characterId': character_id,
                'characterName': character_name,
                'chatId': chat_data.get('chat_id', ''),
                'personalizedHook': personalized_hook,
                'template_used': template,
                'timestamp': datetime.utcnow().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Error creating AI nudge: {str(e)}")
            return {}
    
    def _schedule_nudge(self, user_id: str, nudge_data: Dict):
        """Schedule the AI nudge notification"""
        try:
            # Add random delay (0-2 hours) to avoid spam feel
            delay_minutes = random.randint(0, 120)
            scheduled_time = datetime.utcnow() + timedelta(minutes=delay_minutes)
            
            # Create notification event
            notification_data = {
                **nudge_data,
                'scheduledFor': scheduled_time.isoformat(),
            }
            
            # Use notification service to queue the nudge
            notification_service.create_notification_event(notification_data)
            
            logger.info(f"AI nudge scheduled for user {user_id} at {scheduled_time}")
            
        except Exception as e:
            logger.error(f"Error scheduling nudge: {str(e)}")
    
    def _increment_nudge_counter(self, user_id: str):
        """Increment daily nudge counter for user"""
        try:
            today = datetime.utcnow().strftime('%Y-%m-%d')
            nudge_ref = self.db.collection('nudges').document(user_id).collection('daily').document(today)
            
            # Use transaction to safely increment
            @firestore.transactional
            def update_counter(transaction, doc_ref):
                doc = doc_ref.get(transaction=transaction)
                if doc.exists:
                    current_count = doc.to_dict().get('sentCount', 0)
                    transaction.update(doc_ref, {'sentCount': current_count + 1})
                else:
                    transaction.set(doc_ref, {'sentCount': 1, 'date': today})
            
            transaction = self.db.transaction()
            update_counter(transaction, nudge_ref)
            
        except Exception as e:
            logger.error(f"Error incrementing nudge counter: {str(e)}")
    
    def check_onboarding_bounces(self):
        """Check for users who bounced from onboarding and send nudges"""
        try:
            # Get users who started onboarding but didn't complete their first chat
            two_hours_ago = datetime.utcnow() - timedelta(hours=2)
            
            # Query users who registered recently but have no chat activity
            users_query = (self.db.collection('users')
                          .where('createdAt', '>', two_hours_ago)
                          .where('createdAt', '<', datetime.utcnow() - timedelta(hours=1))
                          .limit(50))
            
            users = users_query.get()
            
            for user_doc in users:
                user_id = user_doc.id
                user_data = user_doc.to_dict()
                
                # Check if user has any chat activity
                chats_query = (self.db.collection('conversations')
                              .where('participants', 'array_contains', user_id)
                              .limit(1))
                
                chats = chats_query.get()
                
                if not chats:  # No chat activity
                    # Send onboarding nudge
                    self._send_onboarding_nudge(user_id, user_data)
            
        except Exception as e:
            logger.error(f"Error checking onboarding bounces: {str(e)}")
    
    def _send_onboarding_nudge(self, user_id: str, user_data: Dict):
        """Send nudge to user who bounced from onboarding"""
        try:
            # Create welcome back nudge
            nudge_data = {
                'type': 'ai_nudge',
                'userId': user_id,
                'characterId': 'system',
                'characterName': 'InZone',
                'chatId': '',
                'personalizedHook': "Ready to start your first conversation? Your AI friends are waiting!",
                'isOnboardingNudge': True,
                'timestamp': datetime.utcnow().isoformat(),
            }
            
            # Send immediately (no delay for onboarding nudges)
            notification_service.create_notification_event(nudge_data)
            
            logger.info(f"Onboarding nudge sent to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error sending onboarding nudge: {str(e)}")

# Global scheduler instance
ai_scheduler = AINudgeScheduler()
