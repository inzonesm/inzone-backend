# services/notifications/digest_scheduler.py
from google.cloud import firestore
from dependencies import db
from services.notifications.queue_service import NotificationQueueService
from services.notifications.preference_service import NotificationPreferenceService
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class DigestScheduler:
    """Service for scheduling and sending digest notifications"""

    @staticmethod
    def check_and_send_digests():
        """
        Check all users with quietDigest notifications and send if their quiet period has ended
        This should be called periodically (e.g., every 5-10 minutes)
        """
        try:
            # Get all unique userIds with quietDigest notifications
            quiet_notifs = (db.collection('notifications')
                          .where('quietDigest', '==', True)
                          .where('isRead', '==', False)
                          .get())
            
            user_ids = set()
            for doc in quiet_notifs:
                notif_data = doc.to_dict()
                user_id = notif_data.get('userId')
                if user_id:
                    user_ids.add(user_id)
            
            logger.info(f"Found {len(user_ids)} users with quiet digest notifications")
            
            # For each user, check if they're still in quiet state
            for user_id in user_ids:
                try:
                    is_quiet, reason = NotificationQueueService.is_user_in_quiet_state(user_id)
                    
                    # If no longer in quiet state, send digest
                    if not is_quiet:
                        logger.info(f"User {user_id} exited quiet state - sending digest")
                        DigestScheduler.send_user_digest(user_id)
                    else:
                        logger.debug(f"User {user_id} still in quiet state ({reason})")
                        
                except Exception as e:
                    logger.error(f"Error checking digest for user {user_id}: {e}")
            
            return len(user_ids)
            
        except Exception as e:
            logger.error(f"Error in check_and_send_digests: {e}")
            return 0

    @staticmethod
    def send_user_digest(user_id: str) -> bool:
        """
        Send digest notification for a specific user
        
        Args:
            user_id: The user's ID
            
        Returns:
            bool: True if sent successfully
        """
        try:
            # Get all quietDigest notifications for this user
            quiet_notifs = (db.collection('notifications')
                          .where('userId', '==', user_id)
                          .where('quietDigest', '==', True)
                          .where('isRead', '==', False)
                          .get())
            
            quiet_notif_list = list(quiet_notifs)
            
            if not quiet_notif_list:
                logger.info(f"No quiet notifications to digest for user {user_id}")
                return False
            
            # Send the digest push notification
            success = NotificationQueueService.send_digest_notification(
                user_id, 
                [doc.to_dict() for doc in quiet_notif_list]
            )
            
            if success:
                # Remove quietDigest flag from these notifications
                batch = db.batch()
                for doc in quiet_notif_list:
                    doc_ref = db.collection('notifications').document(doc.id)
                    batch.update(doc_ref, {'quietDigest': False})
                batch.commit()
                
                logger.info(f"Sent digest of {len(quiet_notif_list)} notifications to user {user_id}")
                return True
            else:
                logger.warning(f"Failed to send digest to user {user_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending digest for user {user_id}: {e}")
            return False

    @staticmethod
    def process_scheduled_quiet_hours_digests():
        """
        Process notifications in the queue that were scheduled for quiet hours end
        This sends individual push notifications for queued items
        """
        try:
            from firebase_admin import messaging
            
            # Get notifications in queue marked for quiet hours digest that are ready
            now = datetime.utcnow()
            ready_notifs = (db.collection('notificationsQueue')
                          .where('quietHoursDigest', '==', True)
                          .where('status', '==', 'pending')
                          .where('notBefore', '<=', now)
                          .limit(50)
                          .get())
            
            processed = 0
            for doc in ready_notifs:
                try:
                    notif_data = doc.to_dict()
                    user_id = notif_data.get('uid')
                    
                    # Double-check user is no longer in quiet state
                    is_quiet, _ = NotificationQueueService.is_user_in_quiet_state(user_id)
                    if is_quiet:
                        # Still in quiet state, skip for now
                        continue
                    
                    # Get FCM tokens
                    user_doc = db.collection('humanUsers').document(user_id).get()
                    if not user_doc.exists:
                        continue
                    
                    user_data = user_doc.to_dict()
                    fcm_tokens = user_data.get('fcmTokens', [])
                    
                    if not fcm_tokens:
                        # Mark as sent anyway since there's no token
                        db.collection('notificationsQueue').document(doc.id).update({
                            'status': 'sent',
                            'sentAt': firestore.SERVER_TIMESTAMP
                        })
                        continue
                    
                    # Send notification to all devices
                    payload = notif_data.get('payload', {})
                    notif_type = notif_data.get('type', '')
                    
                    for token in fcm_tokens:
                        try:
                            message = messaging.Message(
                                notification=messaging.Notification(
                                    title=payload.get('title', 'New notification'),
                                    body=payload.get('body', ''),
                                ),
                                data={
                                    'type': notif_type,
                                    **payload
                                },
                                token=token,
                            )
                            
                            messaging.send(message)
                            
                        except messaging.UnregisteredError:
                            # Remove invalid token
                            user_ref = db.collection('humanUsers').document(user_id)
                            user_ref.update({'fcmTokens': firestore.ArrayRemove([token])})
                        except Exception as e:
                            logger.error(f"Error sending queued notification: {e}")
                    
                    # Mark as sent
                    db.collection('notificationsQueue').document(doc.id).update({
                        'status': 'sent',
                        'sentAt': firestore.SERVER_TIMESTAMP
                    })
                    
                    processed += 1
                    
                except Exception as e:
                    logger.error(f"Error processing queued notification: {e}")
            
            if processed > 0:
                logger.info(f"Processed {processed} scheduled quiet hours notifications")
            
            return processed
            
        except Exception as e:
            logger.error(f"Error in process_scheduled_quiet_hours_digests: {e}")
            return 0
