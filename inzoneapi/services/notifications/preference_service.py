# services/notifications/preference_service.py
from flask import jsonify
from google.cloud import firestore
from dependencies import db
import logging
from datetime import datetime, time

logger = logging.getLogger(__name__)


class NotificationPreferenceService:
    """Service for notification preference management"""

    @staticmethod
    def update_preferences(data: dict) -> tuple:
        """
        Update user notification preferences

        Args:
            data: Dictionary containing userId and preferences

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            if 'userId' not in data or 'preferences' not in data:
                return jsonify({"success": False, "error": "Missing userId or preferences"}), 400

            user_id = data['userId']
            preferences = data['preferences']
            
            # Get old preferences to detect changes
            old_prefs = NotificationPreferenceService.get_user_preferences(user_id)
            old_pause_all = old_prefs.get('pauseAll', False)
            old_quiet_hours_enabled = old_prefs.get('quietHoursEnabled', False)
            old_was_in_quiet = old_quiet_hours_enabled and NotificationPreferenceService.is_in_quiet_hours(user_id)
            
            new_pause_all = preferences.get('pauseAll', False)
            new_quiet_hours_enabled = preferences.get('quietHoursEnabled', False)

            # Update user preferences (try humanUsers collection first)
            try:
                user_ref = db.collection('humanUsers').document(user_id)
                user_ref.update({
                    'notificationPrefs': preferences,
                    'preferencesUpdatedAt': firestore.SERVER_TIMESTAMP
                })
            except Exception as e1:
                # If humanUsers doesn't work, try users collection
                try:
                    user_ref = db.collection('users').document(user_id)
                    user_ref.update({
                        'notificationPrefs': preferences,
                        'preferencesUpdatedAt': firestore.SERVER_TIMESTAMP
                    })
                except Exception as e2:
                    return jsonify({"success": False, "error": f"User document not found in any collection: {str(e2)}"}), 404
            
            # Handle digest timer scheduling based on quiet hours changes
            from services.notifications.digest_timer import digest_timer_manager
            
            if new_quiet_hours_enabled:
                # Quiet hours are enabled - schedule/reschedule digest timer
                quiet_hours = preferences.get('quietHours', {})
                end_str = quiet_hours.get('end', '08:00')
                end_parts = end_str.split(':')
                end_time = time(int(end_parts[0]), int(end_parts[1]))
                timezone_offset = preferences.get('timezoneOffset', 0)
                
                digest_timer_manager.schedule_user_digest(user_id, end_time, timezone_offset)
                logger.info(f"Scheduled digest timer for user {user_id} at {end_str}")
            else:
                # Quiet hours disabled - cancel any scheduled digest timer
                digest_timer_manager.cancel_user_digest(user_id)
                logger.info(f"Cancelled digest timer for user {user_id}")
            
            # Check if we need to send a digest notification
            should_send_digest = False
            
            # Case 1: pauseAll was true and is now false
            if old_pause_all and not new_pause_all:
                should_send_digest = True
                logger.info(f"User {user_id} unpaused notifications - will send digest")
            
            # Case 2: quietHoursEnabled changed from true to false
            elif old_quiet_hours_enabled and not new_quiet_hours_enabled:
                should_send_digest = True
                logger.info(f"User {user_id} disabled quiet hours - will send digest")
            
            # Case 3: quiet hours were active and now are not (even if still enabled)
            # This handles the case where quiet hours end naturally
            elif old_was_in_quiet and not NotificationPreferenceService.is_in_quiet_hours(user_id):
                should_send_digest = True
                logger.info(f"User {user_id} exited quiet hours period - will send digest")
            
            if should_send_digest:
                # Send digest of all quietDigest notifications
                from services.notifications.queue_service import NotificationQueueService
                NotificationPreferenceService._send_quiet_digest(user_id)
            
            return jsonify({"success": True, "message": "Preferences updated"}), 200

        except Exception as e:
            logger.error(f"Error updating preferences: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @staticmethod
    def _send_quiet_digest(user_id: str):
        """
        Send digest notification for all quiet notifications
        
        Args:
            user_id: The user's ID
        """
        try:
            from services.notifications.queue_service import NotificationQueueService
            
            # Get all notifications with quietDigest=true that are unread
            quiet_notifs = (db.collection('notifications')
                          .where('userId', '==', user_id)
                          .where('quietDigest', '==', True)
                          .where('isRead', '==', False)
                          .get())
            
            quiet_notif_list = [doc.to_dict() for doc in quiet_notifs]
            
            if quiet_notif_list:
                # Send the digest push notification
                success = NotificationQueueService.send_digest_notification(user_id, quiet_notif_list)
                
                if success:
                    # Remove quietDigest flag from these notifications
                    # They're now visible in notification center
                    batch = db.batch()
                    for doc in quiet_notifs:
                        doc_ref = db.collection('notifications').document(doc.id)
                        batch.update(doc_ref, {'quietDigest': False})
                    batch.commit()
                    
                    logger.info(f"Sent digest of {len(quiet_notif_list)} notifications to user {user_id}")
                else:
                    logger.warning(f"Failed to send digest to user {user_id}")
            else:
                logger.info(f"No quiet notifications to digest for user {user_id}")
                
        except Exception as e:
            logger.error(f"Error sending quiet digest: {e}")

    @staticmethod
    def get_user_preferences(user_id: str) -> dict:
        """
        Get user notification preferences
        
        Args:
            user_id: The user's ID
            
        Returns:
            dict: User preferences or default preferences if not found
        """
        try:
            # Try humanUsers collection first
            user_doc = db.collection('humanUsers').document(user_id).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                return user_data.get('notificationPrefs', {})
            
            # Try users collection
            user_doc = db.collection('users').document(user_id).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                return user_data.get('notificationPrefs', {})
                
        except Exception as e:
            logger.error(f"Error getting preferences for user {user_id}: {e}")
        
        # Return empty dict if not found (will use defaults)
        return {}

    @staticmethod
    def should_send_notification(user_id: str, notification_type: str, actor_id: str = None) -> bool:
        """
        Check if a notification should be sent based on user preferences
        
        Args:
            user_id: The user receiving the notification
            notification_type: Type of notification (likes, comments, dm, group, etc.)
            actor_id: The user performing the action (optional)
            
        Returns:
            bool: True if notification should be sent
        """
        try:
            prefs = NotificationPreferenceService.get_user_preferences(user_id)
            
            # Check if all notifications are paused
            if prefs.get('pauseAll', False):
                logger.info(f"All notifications paused for user {user_id}")
                return False
            
            categories = prefs.get('categories', {})
            
            # Check specific notification type
            if notification_type == 'like':
                likes_prefs = categories.get('likes', {'enabled': True, 'from': 'everyone'})
                if not likes_prefs.get('enabled', True):
                    return False
                from_filter = likes_prefs.get('from', 'everyone')
                if from_filter == 'off':
                    return False
                if from_filter == 'following' and actor_id:
                    return NotificationPreferenceService._is_following(user_id, actor_id)
                    
            elif notification_type == 'comment':
                comment_prefs = categories.get('comments', {'enabled': True, 'from': 'everyone'})
                if not comment_prefs.get('enabled', True):
                    return False
                from_filter = comment_prefs.get('from', 'everyone')
                if from_filter == 'off':
                    return False
                if from_filter == 'following' and actor_id:
                    return NotificationPreferenceService._is_following(user_id, actor_id)
                if from_filter == 'followingAndFollowers' and actor_id:
                    return (NotificationPreferenceService._is_following(user_id, actor_id) or 
                           NotificationPreferenceService._is_follower(user_id, actor_id))
                    
            elif notification_type == 'comment_like':
                # Comment likes now use the same settings as regular likes
                likes_prefs = categories.get('likes', {'enabled': True, 'from': 'everyone'})
                if not likes_prefs.get('enabled', True):
                    return False
                from_filter = likes_prefs.get('from', 'everyone')
                if from_filter == 'off':
                    return False
                if from_filter == 'following' and actor_id:
                    return NotificationPreferenceService._is_following(user_id, actor_id)
                    
            elif notification_type == 'dm' or notification_type == 'direct_message':
                dm_prefs = categories.get('dm', {'enabled': True, 'from': 'everyone'})
                if not dm_prefs.get('enabled', True):
                    return False
                from_filter = dm_prefs.get('from', 'everyone')
                if from_filter == 'off':
                    return False
                if from_filter == 'following' and actor_id:
                    return NotificationPreferenceService._is_following(user_id, actor_id)
                    
            elif notification_type == 'group':
                group_prefs = categories.get('group', {'enabled': True, 'notifyFor': 'everyone'})
                if not group_prefs.get('enabled', True):
                    return False
                notify_for = group_prefs.get('notifyFor', 'everyone')
                if notify_for == 'off':
                    return False
                # Note: mentions and popularCharacters filtering handled in event_service
                    
            elif notification_type == 'follower':
                follower_prefs = categories.get('followers', {'enabled': True})
                return follower_prefs.get('enabled', True)
                
            elif notification_type == 'system':
                system_prefs = categories.get('system', {'enabled': True})
                return system_prefs.get('enabled', True)
                
            elif notification_type == 'rare_offer':
                offer_prefs = categories.get('rareOffers', {'enabled': True})
                return offer_prefs.get('enabled', True)
                
            elif notification_type == 'ai_nudge':
                nudge_prefs = categories.get('aiNudges', {'enabled': False})
                return nudge_prefs.get('enabled', False)
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking notification preferences: {e}")
            # Default to sending notification on error
            return True

    @staticmethod
    def is_in_quiet_hours(user_id: str) -> bool:
        """Check if current time is within user's quiet hours
        
        Args:
            user_id: The user's ID
            
        Returns:
            bool: True if in quiet hours, False otherwise
        """
        try:
            prefs = NotificationPreferenceService.get_user_preferences(user_id)
            
            # Check if quiet hours are enabled
            if not prefs.get('quietHoursEnabled', False):
                return False
            
            quiet_hours = prefs.get('quietHours', {})
            start_str = quiet_hours.get('start', '22:00')
            end_str = quiet_hours.get('end', '08:00')
            
            # Parse time strings (format: HH:MM)
            start_parts = start_str.split(':')
            end_parts = end_str.split(':')
            start_time = time(int(start_parts[0]), int(start_parts[1]))
            end_time = time(int(end_parts[0]), int(end_parts[1]))
            
            # Get current time (user's local time would be better, but using UTC for now)
            current_time = datetime.utcnow().time()
            
            # Handle quiet hours that span midnight
            if start_time <= end_time:
                # Simple case: 10 PM to 8 AM next day would be False here
                # This case is: 8 AM to 10 PM (daytime quiet hours, unusual)
                return start_time <= current_time <= end_time
            else:
                # Spans midnight: 10 PM to 8 AM
                return current_time >= start_time or current_time <= end_time
                
        except Exception as e:
            logger.error(f"Error checking quiet hours for user {user_id}: {e}")
            return False

    @staticmethod
    def _is_following(user_id: str, followed_id: str) -> bool:
        """Check if user_id follows followed_id"""
        try:
            user_doc = db.collection('humanUsers').document(user_id).get()
            if user_doc.exists:
                following = user_doc.to_dict().get('following', [])
                return followed_id in following
        except Exception as e:
            logger.error(f"Error checking following status: {e}")
        return False

    @staticmethod
    def _is_follower(user_id: str, follower_id: str) -> bool:
        """Check if follower_id follows user_id"""
        try:
            follower_doc = db.collection('humanUsers').document(follower_id).get()
            if follower_doc.exists:
                following = follower_doc.to_dict().get('following', [])
                return user_id in following
        except Exception as e:
            logger.error(f"Error checking follower status: {e}")
        return False
