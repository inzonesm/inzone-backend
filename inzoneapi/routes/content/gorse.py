# routes/content/gorse.py
from flask import Blueprint, request, jsonify
from services.content.gorse_service import GorseService

gorse_bp = Blueprint('gorse', __name__)


@gorse_bp.route('/feed/track-view', methods=['POST'])
def track_post_view():
    """Track when a user views a post"""
    try:
        data = request.json
        return GorseService.track_view(data)
    except Exception as e:
        print(f"Error tracking view: {e}")
        return jsonify({'error': str(e)}), 500


@gorse_bp.route('/feed/track-like', methods=['POST'])
def track_post_like():
    """Track when a user likes a post"""
    try:
        data = request.json
        return GorseService.track_like(data)
    except Exception as e:
        print(f"Error tracking like: {e}")
        return jsonify({'error': str(e)}), 500


@gorse_bp.route('/feed/track-comment', methods=['POST'])
def track_post_comment():
    """Track when a user comments on a post"""
    try:
        data = request.json
        return GorseService.track_comment(data)
    except Exception as e:
        print(f"Error tracking comment: {e}")
        return jsonify({'error': str(e)}), 500


@gorse_bp.route('/feed/track-share', methods=['POST'])
def track_post_share():
    """Track when a user shares a post"""
    try:
        data = request.json
        return GorseService.track_share(data)
    except Exception as e:
        print(f"Error tracking share: {e}")
        return jsonify({'error': str(e)}), 500


@gorse_bp.route('/feed/similar-posts/<post_id>', methods=['GET'])
def get_similar_posts_endpoint(post_id):
    """Get similar posts for 'You may also like' section"""
    try:
        limit = int(request.args.get('limit', 5))
        return GorseService.get_similar_posts(post_id, limit=limit)
    except Exception as e:
        print(f"Error getting similar posts: {e}")
        return jsonify({'error': str(e)}), 500
