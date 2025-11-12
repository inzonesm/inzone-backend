# routes/ai/engagement.py
from flask import Blueprint, request, jsonify

ai_engagement_bp = Blueprint('ai_engagement', __name__)

# Service instances will be injected via init functions
engagement_service = None
bulk_engagement_service = None
scheduling_service = None


def init_engagement_services(eng_service, bulk_service, sched_service):
    """Initialize the engagement service instances"""
    global engagement_service, bulk_engagement_service, scheduling_service
    engagement_service = eng_service
    bulk_engagement_service = bulk_service
    scheduling_service = sched_service


@ai_engagement_bp.route('/api/ai/send-dm', methods=['POST'])
def ai_send_dm():
    """AI user sends a DM"""
    try:
        if engagement_service is None:
            return jsonify({"success": False, "error": "Engagement service not initialized"}), 500
        data = request.get_json()
        return engagement_service.send_dm(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_engagement_bp.route('/api/ai/like-post', methods=['POST'])
def ai_like_post():
    """AI user likes a post"""
    try:
        if engagement_service is None:
            return jsonify({"success": False, "error": "Engagement service not initialized"}), 500
        data = request.get_json()
        return engagement_service.like_post(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_engagement_bp.route('/api/ai/comment-on-post', methods=['POST'])
def ai_comment_on_post():
    """AI user comments on a post"""
    try:
        if engagement_service is None:
            return jsonify({"success": False, "error": "Engagement service not initialized"}), 500
        data = request.get_json()
        return engagement_service.comment_on_post(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_engagement_bp.route('/api/ai/bulk-engage', methods=['POST'])
def ai_bulk_engage():
    """AI users perform bulk engagement"""
    try:
        if bulk_engagement_service is None:
            return jsonify({"success": False, "error": "Bulk engagement service not initialized"}), 500
        data = request.get_json()
        return bulk_engagement_service.bulk_engage(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_engagement_bp.route('/api/ai/engagement-stats', methods=['GET'])
def get_ai_engagement_stats():
    """Get AI engagement statistics"""
    try:
        if engagement_service is None:
            return jsonify({"success": False, "error": "Engagement service not initialized"}), 500
        ai_user_id = request.args.get('ai_user_id')
        days = int(request.args.get('days', 7))
        return engagement_service.get_engagement_stats(ai_user_id, days)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_engagement_bp.route('/api/ai/get-popular-characters', methods=['GET'])
def get_popular_characters_for_dm():
    """Get available popular characters"""
    try:
        if engagement_service is None:
            return jsonify({"success": False, "error": "Engagement service not initialized"}), 500
        limit = int(request.args.get('limit', 50))
        return engagement_service.get_popular_characters(limit)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_engagement_bp.route('/api/ai/schedule-character-engagement', methods=['POST'])
def schedule_character_engagement():
    """Schedule AI engagement for a specific character"""
    try:
        if scheduling_service is None:
            return jsonify({"success": False, "error": "Scheduling service not initialized"}), 500
        data = request.get_json()
        return scheduling_service.schedule_character_engagement(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_engagement_bp.route('/api/ai/schedule-all-characters', methods=['POST'])
def schedule_all_characters():
    """Schedule AI engagement for all characters"""
    try:
        if scheduling_service is None:
            return jsonify({"success": False, "error": "Scheduling service not initialized"}), 500
        data = request.get_json() or {}
        return scheduling_service.schedule_all_characters(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_engagement_bp.route('/api/ai/execute-scheduled-engagement', methods=['POST'])
def execute_scheduled_engagement():
    """Execute scheduled AI engagement"""
    try:
        if scheduling_service is None:
            return jsonify({"success": False, "error": "Scheduling service not initialized"}), 500
        data = request.get_json() or {}
        return scheduling_service.execute_scheduled_engagement(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
