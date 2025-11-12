# services/ai/scheduler_service.py
from flask import jsonify
import logging

logger = logging.getLogger(__name__)


class AISchedulerService:
    """Service for AI engagement scheduler control"""

    def __init__(self, scheduler):
        """
        Initialize with the AI engagement scheduler instance

        Args:
            scheduler: The AIEngagementScheduler instance
        """
        self.scheduler = scheduler

    def get_status(self) -> tuple:
        """
        Get AI engagement scheduler status

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            status = {
                "running": self.scheduler.running,
                "thread_alive": self.scheduler.scheduler_thread.is_alive() if self.scheduler.scheduler_thread else False
            }

            return jsonify({"success": True, "data": status}), 200

        except Exception as ex:
            logger.error("Error getting scheduler status: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    def control_scheduler(self, data: dict) -> tuple:
        """
        Start or stop the AI engagement scheduler

        Args:
            data: Dictionary containing action ("start" or "stop")

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            action = data.get("action")

            if action == "start":
                if not self.scheduler.running:
                    self.scheduler.start_scheduler()
                    return jsonify({"success": True, "message": "Scheduler started"}), 200
                else:
                    return jsonify({"success": False, "message": "Scheduler already running"}), 400

            elif action == "stop":
                if self.scheduler.running:
                    self.scheduler.stop_scheduler()
                    return jsonify({"success": True, "message": "Scheduler stopped"}), 200
                else:
                    return jsonify({"success": False, "message": "Scheduler not running"}), 400
            else:
                return jsonify({"success": False, "error": "Invalid action. Use 'start' or 'stop'"}), 400

        except Exception as ex:
            logger.error("Error controlling scheduler: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500
