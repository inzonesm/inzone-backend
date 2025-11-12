# routes/api/chat.py
from flask import Blueprint, request, jsonify
from services.ai.chat_service import ChatService

api_chat_bp = Blueprint('api_chat', __name__)

@api_chat_bp.route('/api/main-ai-chat', methods=['POST'])
def main_ai_chat():
    """Main AI chat endpoint"""
    try:
        message = request.get_json()
        return ChatService.main_ai_chat(message)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500
