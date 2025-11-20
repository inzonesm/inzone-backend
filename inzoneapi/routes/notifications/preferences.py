# routes/notifications/preferences.py
from flask import Blueprint, request, jsonify
from services.notifications.preference_service import NotificationPreferenceService

notif_prefs_bp = Blueprint('notif_prefs', __name__)


@notif_prefs_bp.route('/api/notifications/preferences', methods=['POST'])
def update_notification_preferences():
    """Update user notification preferences"""
    try:
        data = request.get_json()
        return NotificationPreferenceService.update_preferences(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
