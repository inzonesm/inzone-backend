# routes/notifications/preferences.py
from flask import Blueprint, request, jsonify
from services.notifications.preference_service import NotificationPreferenceService
import logging

logger = logging.getLogger(__name__)
notif_prefs_bp = Blueprint('notif_prefs', __name__)


@notif_prefs_bp.route('/api/notifications/preferences', methods=['POST'])
def update_notification_preferences():
    """Update user notification preferences"""
    try:
        logger.info('=== NOTIFICATION PREFERENCES UPDATE REQUEST ===')
        data = request.get_json()
        logger.info(f'Request data: {data}')
        
        if not data:
            logger.error('No data provided')
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        result = NotificationPreferenceService.update_preferences(data)
        logger.info(f'Update result: {result}')
        return result
    except Exception as e:
        logger.error(f'Error updating preferences: {e}', exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
