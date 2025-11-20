# routes/ai/voice.py
from flask import Blueprint, request, jsonify
from services.ai.voice_service import AIVoiceService
from services.ai.voice_chat_service import AIVoiceChatService

ai_voice_bp = Blueprint('ai_voice', __name__)


@ai_voice_bp.route('/api/ai/voice/debug-character', methods=['GET'])
def debug_character_voice():
    """Debug endpoint to test popularCharacters collection access"""
    try:
        character_id = request.args.get('character_id', 'test_character')
        return AIVoiceService.debug_character(character_id)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_voice_bp.route('/api/ai/voice/test', methods=['POST'])
def test_voice_endpoint():
    """Simple test endpoint to verify JSON processing"""
    try:
        data = request.get_json()
        return AIVoiceService.test_voice_endpoint(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_voice_bp.route('/api/ai/voice/ensure', methods=['POST'])
def ensure_voice_for_character():
    """Ensure voice exists for a character"""
    try:
        data = request.get_json(force=True) or {}
        return AIVoiceService.ensure_voice_endpoint(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_voice_bp.route('/api/ai/voice/chat', methods=['POST'])
def voice_chat():
    """Complete voice chat workflow with TTS"""
    try:
        data = request.get_json(force=True) or {}
        return AIVoiceChatService.voice_chat(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_voice_bp.route('/api/ai/voice/batch-setup-voices', methods=['POST'])
def batch_setup_voices():
    """Batch setup voice settings for multiple characters"""
    try:
        data = request.get_json()
        return AIVoiceService.batch_setup_voices(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
