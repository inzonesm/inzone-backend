# services/notifications/digest_scheduler_thread.py
import logging
import threading
import time
from datetime import datetime
from dependencies import db
from services.notifications.queue_service import NotificationQueueService

logger = logging.getLogger(__name__)


class DigestSchedulerThread:
    """Background thread that automatically sends digest notifications when quiet hours end"""
    
    def __init__(self):
        self.running = False
        self.thread = None
        
    def start(self):
        """Start the background scheduler thread"""
        if self.running:
            logger.warning("Digest scheduler already running")
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.thread.start()
        logger.info("✅ Digest scheduler thread started")
        
    def stop(self):
        """Stop the background scheduler thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Digest scheduler thread stopped")
        
    def _run_scheduler(self):
        """Main scheduler loop that runs every minute"""
        logger.info("Digest scheduler loop started")
        
        while self.running:
            try:
                self._check_all_users_for_digest()
            except Exception as e:
                logger.error(f"Error in digest scheduler loop: {e}")
                
            # Sleep for 60 seconds before next check
            time.sleep(60)
            
    def _check_all_users_for_digest(self):
        """Check all users who have pending digest notifications and send if quiet hours ended"""
        try:
            # Find all notifications with quietDigest=true that are unread
            notifications_ref = db.collection('notifications')
            pending_digest_query = (notifications_ref
                                   .where('quietDigest', '==', True)
                                   .where('isRead', '==', False)
                                   .stream())
            
            # Group notifications by userId
            user_notifications = {}
            for notif_doc in pending_digest_query:
                notif_data = notif_doc.to_dict()
                user_id = notif_data.get('userId')
                if user_id:
                    if user_id not in user_notifications:
                        user_notifications[user_id] = []
                    user_notifications[user_id].append(notif_doc)
            
            if not user_notifications:
                logger.debug("No pending digest notifications found")
                return
                
            logger.info(f"Found {len(user_notifications)} users with pending digest notifications")
            
            # Check each user and send digest if they're no longer in quiet state
            for user_id, notifications in user_notifications.items():
                try:
                    # Check if user is still in quiet state
                    is_quiet, quiet_reason = NotificationQueueService.is_user_in_quiet_state(user_id)
                    
                    if not is_quiet:
                        # User is no longer in quiet state - send digest!
                        logger.info(f"User {user_id} has {len(notifications)} pending digest notifications and quiet hours ended - sending digest")
                        NotificationQueueService.send_digest_notification(user_id, notifications)
                    else:
                        logger.debug(f"User {user_id} still in quiet state ({quiet_reason}) - not sending digest yet")
                        
                except Exception as e:
                    logger.error(f"Error checking digest for user {user_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error in _check_all_users_for_digest: {e}")


# Global instance
_digest_scheduler = None


def start_digest_scheduler():
    """Start the global digest scheduler"""
    global _digest_scheduler
    if _digest_scheduler is None:
        _digest_scheduler = DigestSchedulerThread()
    _digest_scheduler.start()
    return _digest_scheduler


def stop_digest_scheduler():
    """Stop the global digest scheduler"""
    global _digest_scheduler
    if _digest_scheduler:
        _digest_scheduler.stop()
        _digest_scheduler = None
