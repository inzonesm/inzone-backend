# routes/content/posts.py
from flask import Blueprint, request, jsonify
from services.content.post_service import PostService

posts_bp = Blueprint('posts', __name__)

@posts_bp.route('/get_post/<post_id>', methods=['GET'])
def get_post(post_id):
    try:
        return PostService.get_post(post_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@posts_bp.route('/delete_post', methods=['POST'])
def delete_post():
    try:
        data = request.get_json()
        post_id = data.get('PostId')
        user_id = data.get('UserId')
        return PostService.delete_post(post_id, user_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500
