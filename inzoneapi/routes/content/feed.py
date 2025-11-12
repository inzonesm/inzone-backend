# routes/content/feed.py
from flask import Blueprint, request, jsonify
from services.content.feed_service import FeedService

feed_bp = Blueprint('feed', __name__)

@feed_bp.route('/feed/create-human-post', methods=['POST'])
def create_human_post():
    try:
        data = request.get_json()
        return FeedService.create_human_post(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@feed_bp.route('/feed/create-ai-post', methods=['POST'])
def create_ai_post():
    try:
        data = request.get_json()
        return FeedService.create_ai_post(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@feed_bp.route('/feed/repost', methods=['POST'])
def repost_post():
    try:
        data = request.get_json()
        return FeedService.repost_post(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@feed_bp.route('/feed/create-repost', methods=['POST'])
def create_repost():
    try:
        data = request.get_json()
        return FeedService.create_repost(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@feed_bp.route('/feed/update-human-post', methods=['POST'])
def update_human_post():
    try:
        data = request.get_json()
        return FeedService.update_human_post(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@feed_bp.route('/feed/update-ai-post', methods=['POST'])
def update_ai_post():
    try:
        data = request.get_json()
        return FeedService.update_ai_post(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@feed_bp.route('/feed/get-feed', methods=['POST'])
def get_feed():
    try:
        return FeedService.get_feed()
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@feed_bp.route('/feed/get-smart-recommendations', methods=['POST'])
def get_smart_recommendations():
    try:
        data = request.get_json()
        return FeedService.get_smart_recommendations(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@feed_bp.route('/feed/posts-flow', methods=['GET'])
def posts_flow():
    """Main feed endpoint with Gorse integration"""
    try:
        user_id = request.args.get('user_id')
        page = request.args.get('page', default=1, type=int)
        return FeedService.posts_flow(user_id, page)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@feed_bp.route('/feed/test-feed-quality', methods=['GET'])
def test_feed_quality():
    """Test feed quality across multiple pages"""
    try:
        user_id = request.args.get('user_id')
        page = request.args.get('page', default=1, type=int)
        pages_to_test = request.args.get('pages', default=10, type=int)
        return FeedService.test_feed_quality(user_id, page, pages_to_test)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@feed_bp.route('/feed/update-post', methods=['POST'])
def update_post():
    """Update a post"""
    try:
        data = request.get_json()
        return FeedService.update_post(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@feed_bp.route('/feed/write-comment', methods=['POST'])
def write_comment():
    """Write a comment on a post"""
    try:
        data = request.get_json()
        return FeedService.write_comment(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@feed_bp.route('/feed/get-user-posts', methods=['POST'])
def get_user_posts():
    """Get posts by a specific user"""
    try:
        data = request.get_json()
        user_id = data.get("UserId")
        return FeedService.get_user_posts(user_id)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@feed_bp.route('/feed/get-ai-posts', methods=['POST'])
def get_ai_posts():
    """Get posts by a specific AI user"""
    try:
        data = request.get_json()
        username = data.get("UserName")
        return FeedService.get_ai_posts(username)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
