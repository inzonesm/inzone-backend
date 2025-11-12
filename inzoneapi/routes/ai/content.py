# routes/ai/content.py
from flask import Blueprint, request, jsonify
from services.ai.content_generation_service import AIContentService

ai_content_bp = Blueprint('ai_content', __name__)


@ai_content_bp.route('/ai-content/generate-post', methods=['POST'])
def generate_post():
    """Generate an AI post"""
    try:
        ai_user_id = request.get_json()
        return AIContentService.generate_ai_post(ai_user_id)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
