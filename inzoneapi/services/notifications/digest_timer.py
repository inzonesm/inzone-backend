# services/notifications/digest_timer.py
"""
Per-user digest timer system.
Schedules digest delivery when each user's quiet hours end.
"""

from datetime import datetime, time, timedelta
from threading import Thread, Lock
import logging
from dependencies import db

logger = logging.getLogger(__name__)


class DigestTimerManager:
    """Manages per-user timers for digest delivery"""
    
    _instance = None
    _lock = Lock()
    _user_timers = {}  # {user_id: Timer}
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DigestTimerManager, cls).__new__(cls)
        return cls._instance
    
    @staticmethod
    def initialize_timers():
        """
        Initialize timers for all users who are currently in quiet hours.
        Should be called on backend startup.
        """
        if DigestTimerManager._initialized:
            return
            
        try:
            logger.info("Initializing digest timers for users in quiet hours...")
            
            # Get all users with quiet hours enabled
            users_ref = db.collection('humanUsers')
            users = users_ref.where('notificationPrefs.quietHoursEnabled', '==', True).stream()
            
            count = 0
            for user_doc in users:
                try:
                    user_id = user_doc.id
                    user_data = user_doc.to_dict()
                    prefs = user_data.get('notificationPrefs', {})
                    
                    # Check if this user is currently in quiet hours
                    from services.notifications.queue_service import NotificationQueueService
                    is_quiet, reason = NotificationQueueService.is_user_in_quiet_state(user_id)
                    
                    if is_quiet and reason == 'quietHours':
                        # Schedule digest for this user
                        quiet_hours = prefs.get('quietHours', {})
                        end_str = quiet_hours.get('end', '08:00')
                        end_parts = end_str.split(':')
                        end_time = time(int(end_parts[0]), int(end_parts[1]))
                        timezone_offset = prefs.get('timezoneOffset', 0)
                        
                        DigestTimerManager.schedule_user_digest(user_id, end_time, timezone_offset)
                        count += 1
                        
                except Exception as e:
                    logger.error(f"Error initializing timer for user {user_id}: {e}")
                    continue
            
            logger.info(f"Initialized {count} digest timers")
            DigestTimerManager._initialized = True
            
        except Exception as e:
            logger.error(f"Error initializing digest timers: {e}")
    
    @staticmethod
    def schedule_user_digest(user_id: str, quiet_hours_end: time, timezone_offset_hours: int):
        """
        Schedule a digest to be sent when this user's quiet hours end.
        
        Args:
            user_id: The user ID
            quiet_hours_end: Time when quiet hours end (e.g., time(0, 55) for 12:55 AM)
            timezone_offset_hours: User's timezone offset in hours (e.g., -5 for EST)
        """
        try:
            # Calculate when to send the digest (in UTC)
            now_utc = datetime.utcnow()
            
            # Convert user's local end time to UTC
            # If quiet hours end at 12:55 AM EST (offset -5), that's 5:55 AM UTC
            end_hour = (quiet_hours_end.hour - timezone_offset_hours) % 24
            end_minute = quiet_hours_end.minute
            
            # Calculate next occurrence of this time
            target_utc = now_utc.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
            
            # If the target time has already passed today, schedule for tomorrow
            if target_utc <= now_utc:
                target_utc += timedelta(days=1)
            
            delay_seconds = (target_utc - now_utc).total_seconds()
            
            logger.info(f"Scheduling digest for user {user_id} in {delay_seconds/60:.1f} minutes (at {target_utc} UTC)")
            
            # Cancel existing timer if any
            DigestTimerManager.cancel_user_digest(user_id)
            
            # Create new timer
            timer = Thread(target=DigestTimerManager._send_digest_after_delay, args=(user_id, delay_seconds))
            timer.daemon = True
            timer.start()
            
            with DigestTimerManager._lock:
                DigestTimerManager._user_timers[user_id] = timer
                
        except Exception as e:
            logger.error(f"Error scheduling digest for user {user_id}: {e}")
    
    @staticmethod
    def cancel_user_digest(user_id: str):
        """Cancel scheduled digest for a user"""
        with DigestTimerManager._lock:
            if user_id in DigestTimerManager._user_timers:
                # Note: Python threads can't be cancelled, but daemon threads will exit when the program exits
                del DigestTimerManager._user_timers[user_id]
                logger.info(f"Cancelled digest timer for user {user_id}")
    
    @staticmethod
    def _send_digest_after_delay(user_id: str, delay_seconds: float):
        """Internal method to wait and then send digest"""
        import time as time_module
        
        try:
            # Wait for the specified delay
            time_module.sleep(delay_seconds)
            
            # Check if user still has pending digest notifications
            from services.notifications.queue_service import NotificationQueueService
            
            logger.info(f"Digest timer triggered for user {user_id}, checking for pending notifications...")
            
            # Check if user is still in quiet state
            is_quiet, _ = NotificationQueueService.is_user_in_quiet_state(user_id)
            
            if is_quiet:
                logger.info(f"User {user_id} still in quiet state, not sending digest yet")
                return
            
            # Get pending digest notifications
            notifications_ref = db.collection('notifications')
            pending_digest = (notifications_ref
                            .where('userId', '==', user_id)
                            .where('quietDigest', '==', True)
                            .where('isRead', '==', False)
                            .get())
            
            pending_list = list(pending_digest)
            
            if pending_list:
                logger.info(f"Sending scheduled digest to user {user_id} with {len(pending_list)} notifications")
                NotificationQueueService.send_digest_notification(user_id, pending_list)
            else:
                logger.info(f"No pending digest notifications for user {user_id}")
                
            # Remove from active timers
            with DigestTimerManager._lock:
                if user_id in DigestTimerManager._user_timers:
                    del DigestTimerManager._user_timers[user_id]
                    
        except Exception as e:
            logger.error(f"Error in digest timer for user {user_id}: {e}")


# Singleton instance
digest_timer_manager = DigestTimerManager()
