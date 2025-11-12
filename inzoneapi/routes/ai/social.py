# routes/ai/social.py
from flask import Blueprint, request, jsonify
from services.ai.social_service import AISocialService

ai_social_mgmt_bp = Blueprint('ai_social_mgmt', __name__)


@ai_social_mgmt_bp.route('/api/ai/follow', methods=['POST'])
def follow():
    """Follow an AI user"""
    try:
        data = request.get_json()
        return AISocialService.follow(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_social_mgmt_bp.route('/api/ai/unfollow', methods=['POST'])
def unfollow():
    """Unfollow an AI user"""
    try:
        data = request.get_json()
        return AISocialService.unfollow(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_social_mgmt_bp.route('/api/ai/get-followers', methods=['POST'])
def get_followers():
    """Get followers of an AI user"""
    try:
        data = request.get_json()
        user_id = data.get("UserId")
        return AISocialService.get_followers(user_id)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_social_mgmt_bp.route('/api/ai/get-following', methods=['POST'])
def get_following():
    """Get who an AI user is following"""
    try:
        data = request.get_json()
        user_id = data.get("UserId")
        return AISocialService.get_following(user_id)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_social_mgmt_bp.route('/api/ai/remove-from-followers', methods=['POST'])
def remove_follower():
    """Remove a follower from an AI user"""
    try:
        data = request.get_json()
        return AISocialService.remove_follower(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_social_mgmt_bp.route('/api/ai/remove-from-following', methods=['POST'])
def remove_following():
    """Remove someone from following list"""
    try:
        data = request.get_json()
        return AISocialService.remove_following(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
