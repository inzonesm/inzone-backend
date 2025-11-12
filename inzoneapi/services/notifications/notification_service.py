from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore, messaging
import os
import json
import logging
from typing import Dict, List, Optional
import uuid
import hashlib

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(self):
        # Initialize Firebase if not already done
        if not firebase_admin._apps:
            cred = credentials.Certificate('key.json')
            firebase_admin.initialize_app(cred)
        
        self.db = firestore.client()
        self.batch_windows = {
            'group': 30,  # 30 minutes
            'engagement': 60,  # 60 minutes
        }
        
    def create_notification_event(self, event_data: Dict) -> str:
        """Create a notification event and add to queue"""
        try:
            # Generate unique notification ID
            notification_id = str(uuid.uuid4())
            
            # Create dedupe key
            dedupe_key = self._generate_dedupe_key(event_data)
            
            # Check if notification already exists with same dedupe key
            existing = self._check_duplicate_notification(dedupe_key)
            if existing:
                logger.info(f"Duplicate notification found with dedupe key: {dedupe_key}")
                return existing
            
            # Get user preferences
            user_prefs = self._get_user_preferences(event_data.get('userId'))
            if not self._should_send_notification(event_data, user_prefs):
                logger.info(f"Notification blocked by user preferences: {event_data.get('type')}")
                return notification_id
            
            # Create notification queue entry
            notification_data = {
                'id': notification_id,
                'uid': event_data.get('userId'),
                'type': event_data.get('type'),
                'payload': event_data,
                'dedupeKey': dedupe_key,
                'notBefore': self._calculate_not_before(user_prefs),
                'status': 'pending',
                'createdAt': firestore.SERVER_TIMESTAMP,
                'batchGroup': self._get_batch_group(event_data),
            }
            
            # Add to Firestore queue
            self.db.collection('notificationsQueue').document(notification_id).set(notification_data)
            
            logger.info(f"Notification queued: {notification_id}")
            return notification_id
            
        except Exception as e:
            logger.error(f"Error creating notification: {str(e)}")
            raise
    
    def _generate_dedupe_key(self, event_data: Dict) -> str:
        """Generate a unique dedupe key for the notification"""
        key_components = [
            event_data.get('type', ''),
            event_data.get('userId', ''),
            event_data.get('postId', ''),
            event_data.get('groupId', ''),
            event_data.get('chatId', ''),
        ]
        
        # Add timestamp component for batching window
        now = datetime.utcnow()
        window_mins = self.batch_windows.get(event_data.get('category', 'default'), 5)
        window_timestamp = int(now.timestamp() // (window_mins * 60))
        key_components.append(str(window_timestamp))
        
        key_string = '|'.join(filter(None, key_components))
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def _check_duplicate_notification(self, dedupe_key: str) -> Optional[str]:
        """Check if a notification with the same dedupe key already exists"""
        query = self.db.collection('notificationsQueue').where('dedupeKey', '==', dedupe_key).limit(1)
        docs = query.get()
        
        if docs:
            return docs[0].id
        return None
    
    def _get_user_preferences(self, user_id: str) -> Dict:
        """Get user notification preferences"""
        try:
            user_doc = self.db.collection('users').document(user_id).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                return user_data.get('notificationPrefs', self._get_default_preferences())
            return self._get_default_preferences()
        except Exception as e:
            logger.error(f"Error getting user preferences: {str(e)}")
            return self._get_default_preferences()
    
    def _get_default_preferences(self) -> Dict:
        """Return default notification preferences"""
        return {
            'allEnabled': True,
            'quietHours': {'start': '22:00', 'end': '08:00'},
            'categories': {
                'dm': {'enabled': True, 'sound': True},
                'group': {'enabled': True, 'mentionsOnly': False, 'batchMins': 30},
                'engagement': {'enabled': True, 'batchMins': 60},
                'aiNudges': {'enabled': True, 'maxPerDay': 2},
                'system': {'enabled': True},
                'rareOffers': {'enabled': True, 'maxPerWeek': 2}
            }
        }
    
    def _should_send_notification(self, event_data: Dict, user_prefs: Dict) -> bool:
        """Check if notification should be sent based on user preferences"""
        if not user_prefs.get('allEnabled', True):
            return False
        
        notification_type = event_data.get('type', '')
        categories = user_prefs.get('categories', {})
        
        # Check category-specific preferences
        if notification_type.startswith('dm_'):
            return categories.get('dm', {}).get('enabled', True)
        elif notification_type in ['group_digest', 'mention']:
            group_prefs = categories.get('group', {})
            if not group_prefs.get('enabled', True):
                return False
            # If mentions only and this is not a mention
            if group_prefs.get('mentionsOnly', False) and notification_type != 'mention':
                return False
            return True
        elif notification_type == 'engagement_digest':
            return categories.get('engagement', {}).get('enabled', True)
        elif notification_type == 'ai_nudge':
            return categories.get('aiNudges', {}).get('enabled', True)
        elif notification_type == 'rare_offer':
            return categories.get('rareOffers', {}).get('enabled', True)
        elif notification_type == 'system':
            return categories.get('system', {}).get('enabled', True)
        
        return True
    
    def _calculate_not_before(self, user_prefs: Dict) -> datetime:
        """Calculate when notification can be sent (respecting quiet hours)"""
        now = datetime.utcnow()
        quiet_hours = user_prefs.get('quietHours', {})
        
        if not quiet_hours:
            return now
        
        start_time = quiet_hours.get('start', '22:00')
        end_time = quiet_hours.get('end', '08:00')
        
        # Parse quiet hours
        start_hour, start_min = map(int, start_time.split(':'))
        end_hour, end_min = map(int, end_time.split(':'))
        
        current_time = now.time()
        quiet_start = datetime.time(start_hour, start_min)
        quiet_end = datetime.time(end_hour, end_min)
        
        # Check if currently in quiet hours
        if quiet_start <= current_time or current_time <= quiet_end:
            # Schedule for end of quiet hours
            tomorrow = now.date() + timedelta(days=1)
            return datetime.combine(tomorrow, quiet_end)
        
        return now
    
    def _get_batch_group(self, event_data: Dict) -> str:
        """Get batch group for notification batching"""
        notification_type = event_data.get('type', '')
        user_id = event_data.get('userId', '')
        
        if notification_type in ['group_digest']:
            return f"group_{user_id}_{event_data.get('groupId', '')}"
        elif notification_type == 'engagement_digest':
            return f"engagement_{user_id}_{event_data.get('postId', '')}"
        
        return f"single_{user_id}_{notification_type}"
    
    def process_pending_notifications(self):
        """Process pending notifications (called periodically)"""
        try:
            # Get pending notifications ready to be sent
            now = datetime.utcnow()
            query = (self.db.collection('notificationsQueue')
                    .where('status', '==', 'pending')
                    .where('notBefore', '<=', now)
                    .limit(50))
            
            pending = query.get()
            
            # Group notifications for batching
            batched_notifications = self._batch_notifications(pending)
            
            # Send notifications
            for batch in batched_notifications:
                self._send_notification_batch(batch)
                
        except Exception as e:
            logger.error(f"Error processing pending notifications: {str(e)}")
    
    def _batch_notifications(self, notifications: List) -> List[List]:
        """Group notifications by batch group for batching"""
        batches = {}
        
        for doc in notifications:
            data = doc.to_dict()
            batch_group = data.get('batchGroup', f"single_{doc.id}")
            
            if batch_group not in batches:
                batches[batch_group] = []
            
            batches[batch_group].append({
                'id': doc.id,
                'data': data
            })
        
        return list(batches.values())
    
    def _send_notification_batch(self, batch: List[Dict]):
        """Send a batch of notifications"""
        try:
            if not batch:
                return
            
            # Get the first notification to determine user and type
            first_notif = batch[0]['data']
            user_id = first_notif.get('uid')
            
            if not user_id:
                logger.error("No user ID found for notification batch")
                return
            
            # Get user's FCM tokens
            user_doc = self.db.collection('users').document(user_id).get()
            if not user_doc.exists:
                logger.error(f"User document not found: {user_id}")
                return
            
            user_data = user_doc.to_dict()
            fcm_tokens = user_data.get('fcmTokens', [])
            
            if not fcm_tokens:
                logger.warning(f"No FCM tokens found for user: {user_id}")
                return
            
            # Create notification message
            if len(batch) > 1:
                # Batched notification
                message_data = self._create_batched_message(batch)
            else:
                # Single notification
                message_data = self._create_single_message(batch[0]['data'])
            
            # Send to all user's devices
            for token in fcm_tokens:
                try:
                    message = messaging.Message(
                        notification=messaging.Notification(
                            title=message_data['title'],
                            body=message_data['body'],
                        ),
                        data=message_data['data'],
                        token=token,
                    )
                    
                    response = messaging.send(message)
                    logger.info(f"Notification sent successfully: {response}")
                    
                except messaging.UnregisteredError:
                    # Remove invalid token
                    self._remove_invalid_token(user_id, token)
                except Exception as e:
                    logger.error(f"Error sending to token {token}: {str(e)}")
            
            # Mark notifications as sent
            for notif in batch:
                self.db.collection('notificationsQueue').document(notif['id']).update({
                    'status': 'sent',
                    'sentAt': firestore.SERVER_TIMESTAMP
                })
                
        except Exception as e:
            logger.error(f"Error sending notification batch: {str(e)}")
    
    def _create_single_message(self, notification_data: Dict) -> Dict:
        """Create message for single notification"""
        payload = notification_data.get('payload', {})
        notification_type = notification_data.get('type', '')
        
        # Get template based on type
        template = self._get_notification_template(notification_type)
        
        # Fill template with data
        title = template['title'].format(**payload)
        body = template['body'].format(**payload)
        # deeplink production disabled - include structured payload only
        # deeplink = template['deeplink'].format(**payload)

        return {
            'title': title,
            'body': body,
            'data': {
                'type': notification_type,
                'notification_id': notification_data.get('id'),
                **payload
            }
        }
    
    def _create_batched_message(self, batch: List[Dict]) -> Dict:
        """Create message for batched notifications"""
        first_notif = batch[0]['data']
        notification_type = first_notif.get('type', '')
        count = len(batch)
        
        if notification_type == 'group_digest':
            payload = first_notif.get('payload', {})
            group_name = payload.get('groupName', 'Group')
            return {
                'title': group_name,
                'body': f"{count} new messages",
                'data': {
                    'type': 'group_digest',
                    'batch_size': str(count),
                }
            }
        elif notification_type == 'engagement_digest':
            payload = first_notif.get('payload', {})
            return {
                'title': "New activity on your post",
                'body': f"{count} new interactions",
                'data': {
                    'type': 'engagement_digest',
                    'batch_size': str(count),
                }
            }
        
        # Fallback for other types
        return self._create_single_message(first_notif)
    
    def _get_notification_template(self, notification_type: str) -> Dict:
        """Get notification template by type"""
        templates = {
            'dm_new': {
                'title': '{senderName}',
                'body': '{preview}',
                # 'deeplink': 'inzone://chat/{chatId}'
            },
            'group_digest': {
                'title': '{groupName}',
                'body': '{count} new messages • {topParticipant} is active',
                # 'deeplink': 'inzone://chat/{groupId}'
            },
            'mention': {
                'title': '{groupName}',
                'body': '{senderName} mentioned you: {snippet}',
                # 'deeplink': 'inzone://chat/{groupId}?msg={msgId}'
            },
            'engagement_digest': {
                'title': 'New activity on your post',
                'body': '{likes} likes • {comments} comments',
                # 'deeplink': 'inzone://post/{postId}'
            },
            'ai_nudge': {
                'title': '{characterName} wants your take',
                'body': '{personalizedHook}',
                # 'deeplink': 'inzone://chat/{chatId}'
            },
            'rare_offer': {
                'title': '🎁 {characterName} has coins for you',
                'body': '{offerText}',
                # 'deeplink': 'inzone://earn/{offerType}'
            },
            'system': {
                'title': 'InZone',
                'body': '{message}',
                # 'deeplink': 'inzone://app'
            }
        }
        
        return templates.get(notification_type, templates['system'])
    
    def _remove_invalid_token(self, user_id: str, token: str):
        """Remove invalid FCM token from user document"""
        try:
            user_ref = self.db.collection('users').document(user_id)
            user_ref.update({
                'fcmTokens': firestore.ArrayRemove([token])
            })
            logger.info(f"Removed invalid token for user {user_id}")
        except Exception as e:
            logger.error(f"Error removing invalid token: {str(e)}")

# Global notification service instance
notification_service = NotificationService()