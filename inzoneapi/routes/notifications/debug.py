# routes/notifications/debug.py
from flask import Blueprint, request, jsonify
from services.notifications.debug_service import NotificationDebugService

notif_debug_bp = Blueprint('notif_debug', __name__)


@notif_debug_bp.route('/api/notifications/debug/count', methods=['GET'])
def debug_notification_count():
    """Debug endpoint to count notifications in queue"""
    try:
        user_id = request.args.get('user_id')
        return NotificationDebugService.debug_notification_count(user_id)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@notif_debug_bp.route('/api/notifications/user/<user_id>/all', methods=['GET'])
def get_all_user_notifications(user_id):
    """Get all notifications for a user"""
    try:
        return NotificationDebugService.get_all_user_notifications(user_id)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@notif_debug_bp.route('/api/notifications/test/create-sample', methods=['POST'])
def create_sample_notifications():
    """Create sample notifications for testing"""
    try:
        data = request.get_json()
        return NotificationDebugService.create_sample_notifications(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
