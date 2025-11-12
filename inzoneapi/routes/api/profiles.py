# routes/api/profiles.py
from flask import Blueprint, request, jsonify
from services.ai.ai_profile_service import AIProfileService

api_profiles_bp = Blueprint('api_profiles', __name__)

@api_profiles_bp.route('/api/get-all-ai-profiles', methods=['POST'])
def get_all_ai_profiles():
    """Get all AI character profiles"""
    try:
        return AIProfileService.get_all_profiles()
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@api_profiles_bp.route('/api/create-ai-profile', methods=['POST'])
def create_ai_profile():
    """Create a new AI character profile"""
    try:
        data = request.get_json()
        return AIProfileService.create_profile(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500
