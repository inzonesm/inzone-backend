# routes/ai/characters.py
from flask import Blueprint, request, jsonify
from services.ai.character_service import AICharacterService

ai_characters_bp = Blueprint('ai_characters', __name__)


@ai_characters_bp.route('/api/ai/chat', methods=['POST'])
def chat():
    """Simple AI chat endpoint"""
    try:
        data = request.get_json()
        return AICharacterService.chat(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_characters_bp.route('/api/ai/popular-character-name', methods=['POST'])
def update_popular_character_name():
    """Update popular character name"""
    try:
        doc_id = request.args.get('docId')
        name = request.json.get('name')
        return AICharacterService.update_character_name(doc_id, name)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_characters_bp.route('/api/ai/upvote', methods=['POST'])
def upvote():
    """Upvote a character"""
    try:
        name = request.json.get('Name')
        return AICharacterService.upvote(name)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_characters_bp.route('/api/ai/downvote', methods=['POST'])
def downvote():
    """Downvote a character"""
    try:
        name = request.json.get('Name')
        return AICharacterService.downvote(name)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_characters_bp.route('/api/ai/chat-counter', methods=['GET'])
def chat_counter():
    """Get chat counter for a character"""
    try:
        name = request.args.get('Name')
        return AICharacterService.get_chat_counter(name)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_characters_bp.route('/api/ai/carousel/characters', methods=['GET'])
def get_carousel_characters():
    """Get characters for carousel display"""
    try:
        show_popular_first = request.args.get('showPopularFirst', 'false').lower() == 'true'
        return AICharacterService.get_carousel_characters(show_popular_first)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_characters_bp.route('/api/ai/generate-image', methods=['POST'])
def generate_image():
    """Generate image (placeholder)"""
    try:
        return AICharacterService.generate_image()
    except Exception as e:
        return jsonify({'error': str(e)}), 500
