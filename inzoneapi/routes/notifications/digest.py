# routes/notifications/digest.py
from flask import Blueprint, jsonify, request
from services.notifications.queue_service import NotificationQueueService
import logging

logger = logging.getLogger(__name__)
digest_bp = Blueprint('digest', __name__)


@digest_bp.route('/api/notifications/check-digest', methods=['POST'])
def check_digest():
    """
    Check if user has pending digest notifications and send if quiet period ended
    Called by Flutter app when user opens app or becomes active
    NO CRON JOB NEEDED - this is triggered by user activity
    """
    try:
        data = request.get_json()
        user_id = data.get('userId')
        
        if not user_id:
            return jsonify({'success': False, 'error': 'userId required'}), 400
        
        logger.info(f'=== CHECKING DIGEST FOR USER {user_id} ===')
        
        # This automatically checks and sends digest if needed
        NotificationQueueService._auto_check_user_digest(user_id)
        
        return jsonify({'success': True, 'message': 'Digest check completed'}), 200
        
    except Exception as e:
        logger.error(f'Error checking digest: {e}', exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@digest_bp.route('/api/notifications/send-user-digest/<user_id>', methods=['POST'])
def send_user_digest(user_id: str):
    """
    Manually trigger digest send for a specific user
    Useful for testing or manual intervention
    """
    try:
        logger.info(f'=== MANUALLY SENDING DIGEST FOR USER {user_id} ===')
        
        # Force send digest regardless of quiet state
        from dependencies import db
        
        quiet_notifs = (db.collection('notifications')
                      .where('userId', '==', user_id)
                      .where('quietDigest', '==', True)
                      .where('isRead', '==', False)
                      .get())
        
        quiet_notif_list = list(quiet_notifs)
        
        if not quiet_notif_list:
            return jsonify({
                'success': True,
                'message': f'No digest notifications for user {user_id}'
            }), 200
        
        success = NotificationQueueService.send_digest_notification(
            user_id,
            [doc.to_dict() for doc in quiet_notif_list]
        )
        
        if success:
            # Clear flags
            batch = db.batch()
            for doc in quiet_notif_list:
                doc_ref = db.collection('notifications').document(doc.id)
                batch.update(doc_ref, {'quietDigest': False})
            batch.commit()
        
        return jsonify({
            'success': success,
            'message': f'Digest {"sent" if success else "failed"} for user {user_id}',
            'count': len(quiet_notif_list)
        }), 200 if success else 500
        
    except Exception as e:
        logger.error(f'Error sending user digest: {e}', exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
