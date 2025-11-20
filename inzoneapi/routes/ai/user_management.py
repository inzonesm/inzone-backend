# routes/ai/user_management.py
from flask import Blueprint, request, jsonify
from services.ai.user_management_service import AIUserManagementService

ai_user_mgmt_bp = Blueprint('ai_user_mgmt', __name__)


@ai_user_mgmt_bp.route('/api/ai/create-ai-user', methods=['POST'])
def create_ai_user():
    """Create a new AI user"""
    try:
        data = request.get_json()
        return AIUserManagementService.create_ai_user(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_user_mgmt_bp.route('/api/ai/update-ai-user', methods=['POST'])
def update_ai_user():
    """Update an AI user profile"""
    try:
        data = request.get_json()
        return AIUserManagementService.update_ai_user(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_user_mgmt_bp.route('/api/ai/get-ai-user', methods=['GET'])
def get_ai_user():
    """Get an AI user profile"""
    try:
        username = request.args.get('username')
        return AIUserManagementService.get_ai_user(username)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
