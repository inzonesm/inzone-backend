# routes/ai/scheduler.py
from flask import Blueprint, request, jsonify

ai_scheduler_bp = Blueprint('ai_scheduler', __name__)

# This will be initialized in app.py with the scheduler instance
scheduler_service = None


def init_scheduler_service(service):
    """Initialize the scheduler service instance"""
    global scheduler_service
    scheduler_service = service


@ai_scheduler_bp.route('/api/ai/engagement/scheduler/status', methods=['GET'])
def get_scheduler_status():
    """Get AI engagement scheduler status"""
    try:
        if scheduler_service is None:
            return jsonify({"success": False, "error": "Scheduler service not initialized"}), 500
        return scheduler_service.get_status()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_scheduler_bp.route('/api/ai/engagement/scheduler/control', methods=['POST'])
def control_scheduler():
    """Start or stop the AI engagement scheduler"""
    try:
        if scheduler_service is None:
            return jsonify({"success": False, "error": "Scheduler service not initialized"}), 500
        data = request.get_json()
        return scheduler_service.control_scheduler(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
