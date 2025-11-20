# routes/groups/recommendations.py
"""
API routes for group chat recommendations
"""

from flask import Blueprint, request, jsonify
from services.groups.recommendation_service import GroupChatRecommendationService
import logging

logger = logging.getLogger(__name__)

groups_recommendations_bp = Blueprint('groups_recommendations', __name__)


@groups_recommendations_bp.route('/group/recommendations', methods=['POST'])
def get_recommendations():
    """
    Get personalized group chat recommendations for a user

    Request body:
    {
        "user_id": "string",
        "limit": 20,  // optional, default 20
        "exclude_joined": true,  // optional, default true
        "page": 1  // optional, default 1
    }

    Response:
    {
        "success": true,
        "recommendations": [group_chat_objects],
        "data": {
            "user_categories": ["category1", "category2"],
            "total": 10,
            "method": "smart_category_ranked",
            "page": 1,
            "pool_size": 50
        }
    }
    """
    try:
        data = request.json
        user_id = data.get('user_id')

        if not user_id:
            return jsonify({"error": "user_id is required"}), 400

        limit = data.get('limit', 20)
        exclude_joined = data.get('exclude_joined', True)
        page = data.get('page', 1)

        result = GroupChatRecommendationService.get_smart_recommendations(
            user_id=user_id,
            limit=limit,
            exclude_joined=exclude_joined,
            page=page
        )

        if result.get('success'):
            return jsonify(result), 200
        else:
            return jsonify(result), 400

    except Exception as e:
        logger.error(f"Error getting group chat recommendations: {e}")
        return jsonify({'error': str(e)}), 500


@groups_recommendations_bp.route('/group/popular', methods=['GET'])
def get_popular():
    """
    Get popular/trending group chats

    Query params:
    - limit: Number of group chats to return (default: 10)

    Response:
    {
        "success": true,
        "groupchats": [group_chat_objects]
    }
    """
    try:
        limit = request.args.get('limit', 10, type=int)

        groupchats = GroupChatRecommendationService.get_popular_groupchats(limit=limit)

        return jsonify({
            "success": True,
            "groupchats": groupchats
        }), 200

    except Exception as e:
        logger.error(f"Error getting popular group chats: {e}")
        return jsonify({'error': str(e)}), 500


@groups_recommendations_bp.route('/group/track-view', methods=['POST'])
def track_view():
    """
    Track when a user views a group chat

    Request body:
    {
        "user_id": "string",
        "groupchat_id": "string"
    }
    """
    try:
        data = request.json
        user_id = data.get('user_id')
        groupchat_id = data.get('groupchat_id')

        if not all([user_id, groupchat_id]):
            return jsonify({"error": "user_id and groupchat_id are required"}), 400

        GroupChatRecommendationService.record_interaction(
            user_id=user_id,
            groupchat_id=groupchat_id,
            feedback_type='view'
        )

        return jsonify({"success": True, "message": "View tracked"}), 200

    except Exception as e:
        logger.error(f"Error tracking group chat view: {e}")
        return jsonify({'error': str(e)}), 500


@groups_recommendations_bp.route('/group/track-join', methods=['POST'])
def track_join():
    """
    Track when a user joins a group chat

    Request body:
    {
        "user_id": "string",
        "groupchat_id": "string"
    }
    """
    try:
        data = request.json
        user_id = data.get('user_id')
        groupchat_id = data.get('groupchat_id')

        if not all([user_id, groupchat_id]):
            return jsonify({"error": "user_id and groupchat_id are required"}), 400

        GroupChatRecommendationService.record_interaction(
            user_id=user_id,
            groupchat_id=groupchat_id,
            feedback_type='join'
        )

        return jsonify({"success": True, "message": "Join tracked"}), 200

    except Exception as e:
        logger.error(f"Error tracking group chat join: {e}")
        return jsonify({'error': str(e)}), 500


@groups_recommendations_bp.route('/group/track-leave', methods=['POST'])
def track_leave():
    """
    Track when a user leaves a group chat

    Request body:
    {
        "user_id": "string",
        "groupchat_id": "string"
    }
    """
    try:
        data = request.json
        user_id = data.get('user_id')
        groupchat_id = data.get('groupchat_id')

        if not all([user_id, groupchat_id]):
            return jsonify({"error": "user_id and groupchat_id are required"}), 400

        GroupChatRecommendationService.record_interaction(
            user_id=user_id,
            groupchat_id=groupchat_id,
            feedback_type='leave'
        )

        return jsonify({"success": True, "message": "Leave tracked"}), 200

    except Exception as e:
        logger.error(f"Error tracking group chat leave: {e}")
        return jsonify({'error': str(e)}), 500
