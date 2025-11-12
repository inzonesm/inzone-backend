# routes/scheduler/notifications.py
from flask import Blueprint, request, jsonify
from services.notifications.scheduler_service import NotificationSchedulerService

scheduler_notif_bp = Blueprint('scheduler_notif', __name__)


@scheduler_notif_bp.route('/api/scheduler/daily-nudges', methods=['POST'])
def trigger_daily_nudges():
    """Cloud Scheduler endpoint for daily AI nudges"""
    try:
        return NotificationSchedulerService.trigger_daily_nudges()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@scheduler_notif_bp.route('/api/scheduler/rare-offers', methods=['POST'])
def trigger_weekly_rare_offers():
    """Cloud Scheduler endpoint for weekly rare offer selection"""
    try:
        return NotificationSchedulerService.trigger_weekly_rare_offers()
    except Exception as e:
        return jsonify({'error': str(e)}), 500
