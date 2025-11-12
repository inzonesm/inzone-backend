# routes/admin/feed_config.py
from flask import Blueprint, request, jsonify
from services.admin.feed_config_service import FeedConfigService

admin_feed_config_bp = Blueprint('admin_feed_config', __name__)


@admin_feed_config_bp.route('/admin/feed-config', methods=['GET'])
def get_feed_config():
    """Get current feed recommendation configuration"""
    try:
        return FeedConfigService.get_config()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin_feed_config_bp.route('/admin/feed-config', methods=['POST'])
def update_feed_config():
    """Update feed recommendation configuration in real-time"""
    try:
        data = request.get_json()
        return FeedConfigService.update_config(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin_feed_config_bp.route('/admin/feed-config/reset', methods=['POST'])
def reset_feed_config():
    """Reset feed recommendation configuration to defaults"""
    try:
        return FeedConfigService.reset_config()
    except Exception as e:
        return jsonify({'error': str(e)}), 500
