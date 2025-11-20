# routes/ai/scheduler_endpoints.py
from flask import Blueprint, request, jsonify

scheduler_endpoint_bp = Blueprint('scheduler_endpoint', __name__)

# Service instance to be injected
scheduler_service = None


def init_scheduler_service(service):
    """Initialize the scheduler endpoint service"""
    global scheduler_service
    scheduler_service = service


@scheduler_endpoint_bp.route('/api/ai/schedule-character-engagement', methods=['POST'])
def schedule_character_engagement_api():
    """Manually trigger engagement for a specific character"""
    data = request.get_json()
    result, status = scheduler_service.schedule_character_engagement(data)
    return jsonify(result), status


@scheduler_endpoint_bp.route('/api/ai/schedule-all-characters', methods=['POST'])
def schedule_all_characters_api():
    """Trigger engagement for all popular characters"""
    data = request.get_json() or {}
    result, status = scheduler_service.schedule_all_characters(data)
    return jsonify(result), status


@scheduler_endpoint_bp.route('/api/ai/schedule-engagement-auto', methods=['POST'])
def schedule_engagement_auto():
    """Auto-schedule and EXECUTE engagement with simple concurrency protection"""
    data = request.get_json() or {}
    result, status = scheduler_service.schedule_engagement_auto(data)
    return jsonify(result), status


@scheduler_endpoint_bp.route('/api/ai/engagement-status', methods=['GET'])
def get_engagement_status():
    """Get current engagement status and counts"""
    result, status = scheduler_service.get_engagement_status()
    return jsonify(result), status


@scheduler_endpoint_bp.route('/api/ai/dm-auto-responder', methods=['POST'])
def dm_auto_responder():
    """
    SINGLE-CONVERSATION DM RESPONSE: Responds to a specific conversation when Flutter app triggers it.
    Use this when a human sends a message and you want an immediate AI response for that specific conversation.

    Required data: user_id, ai_character_id, message_text, conversation_id (optional)
    """
    data = request.get_json()
    result, status = scheduler_service.dm_auto_responder(data)
    return jsonify(result), status


@scheduler_endpoint_bp.route('/api/ai/monitor-dms', methods=['POST'])
def monitor_and_respond_dms():
    """
    MASS DM MONITORING: Monitors ALL conversations across ALL AI characters and responds automatically.
    Use this for background monitoring to catch any missed messages. Includes notifications.

    No required data - scans everything and responds where needed.
    """
    result, status = scheduler_service.monitor_and_respond_dms()
    return jsonify(result), status
