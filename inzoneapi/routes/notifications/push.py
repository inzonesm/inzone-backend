# routes/notifications/push.py
from flask import Blueprint, request, jsonify
from services.notifications.push_service import NotificationPushService

notif_push_bp = Blueprint('notif_push', __name__)


@notif_push_bp.route('/api/notifications/register-token', methods=['POST'])
def register_fcm_token():
    """Register FCM token for user"""
    try:
        data = request.get_json()
        return NotificationPushService.register_fcm_token(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@notif_push_bp.route('/api/notifications/send-push', methods=['POST'])
def send_push_notification():
    """Send push notification to user via FCM"""
    try:
        data = request.get_json()
        return NotificationPushService.send_push_notification(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
