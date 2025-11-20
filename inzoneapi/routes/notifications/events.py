# routes/notifications/events.py
from flask import Blueprint, request, jsonify
from services.notifications.event_service import NotificationEventService

notif_events_bp = Blueprint('notif_events', __name__)


@notif_events_bp.route('/api/notifications/events/group-message', methods=['POST'])
def handle_group_message_notification():
    """Handle group message notification event"""
    try:
        data = request.get_json()
        return NotificationEventService.handle_group_message(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@notif_events_bp.route('/api/notifications/events/group-mention', methods=['POST'])
def handle_group_mention_notification():
    """Handle group mention notification event"""
    try:
        data = request.get_json()
        return NotificationEventService.handle_group_mention(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@notif_events_bp.route('/api/notifications/events/direct-message', methods=['POST'])
def handle_direct_message_notification():
    """Handle direct message notification event"""
    try:
        data = request.get_json()
        return NotificationEventService.handle_direct_message(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@notif_events_bp.route('/api/notifications/events/post-engagement', methods=['POST'])
def handle_post_engagement_notification():
    """Handle post engagement notification event"""
    try:
        data = request.get_json()
        return NotificationEventService.handle_post_engagement(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@notif_events_bp.route('/api/notifications/events/user-follow', methods=['POST'])
def handle_user_follow_notification():
    """Handle user follow notification event"""
    try:
        data = request.get_json()
        return NotificationEventService.handle_user_follow(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@notif_events_bp.route('/api/notifications/events/rare-offer', methods=['POST'])
def handle_rare_offer_notification():
    """Handle rare coin offer notification event"""
    try:
        data = request.get_json()
        return NotificationEventService.handle_rare_offer(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@notif_events_bp.route('/api/notifications/events/ai-nudge', methods=['POST'])
def handle_ai_nudge_notification():
    """Handle AI nudge notification event"""
    try:
        data = request.get_json()
        return NotificationEventService.handle_ai_nudge(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@notif_events_bp.route('/api/notifications/events/comment-reply', methods=['POST'])
def trigger_comment_reply_notification():
    """Trigger notification when a user replies to a comment"""
    try:
        data = request.get_json()
        return NotificationEventService.handle_comment_reply(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
