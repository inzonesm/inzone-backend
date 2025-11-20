# routes/admin/feed_config.py
from flask import Blueprint, request, jsonify, send_from_directory
import os
import logging
from services.admin.feed_config_service import FeedConfigService

logger = logging.getLogger(__name__)

admin_feed_config_bp = Blueprint('admin_feed_config', __name__)


@admin_feed_config_bp.route('/admin/feed-config-panel', methods=['GET'])
def serve_feed_config_panel():
    """Serve the feed configuration panel HTML page"""
    try:
        # Get the static directory path
        static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'static')
        return send_from_directory(static_dir, 'feed-config-panel.html')
    except Exception as e:
        return jsonify({'error': f'Panel not found: {str(e)}'}), 404


@admin_feed_config_bp.route('/admin/feed-config', methods=['GET'])
def get_feed_config():
    """Get current feed recommendation configuration"""
    logger.info("========================================")
    logger.info("[FEED CONFIG] GET request received")
    logger.info("========================================")
    try:
        return FeedConfigService.get_config()
    except Exception as e:
        logger.error(f"[FEED CONFIG] Error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@admin_feed_config_bp.route('/admin/feed-config', methods=['POST'])
def update_feed_config():
    """Update feed recommendation configuration in real-time"""
    logger.info("========================================")
    logger.info("[FEED CONFIG] POST request received")
    logger.info(f"[FEED CONFIG] Request data: {request.get_json()}")
    logger.info("========================================")
    try:
        data = request.get_json()
        result = FeedConfigService.update_config(data)
        logger.info("[FEED CONFIG] Update completed successfully")
        return result
    except Exception as e:
        logger.error(f"[FEED CONFIG] Error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@admin_feed_config_bp.route('/admin/feed-config/reset', methods=['POST'])
def reset_feed_config():
    """Reset feed recommendation configuration to defaults"""
    logger.info("========================================")
    logger.info("[FEED CONFIG] RESET request received")
    logger.info("========================================")
    try:
        result = FeedConfigService.reset_config()
        logger.info("[FEED CONFIG] Reset completed successfully")
        return result
    except Exception as e:
        logger.error(f"[FEED CONFIG] Error: {str(e)}")
        return jsonify({'error': str(e)}), 500
