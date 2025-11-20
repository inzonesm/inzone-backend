# routes/api/users.py
from flask import Blueprint, request, jsonify
from services.user.user_service import UserService

api_users_bp = Blueprint('api_users', __name__)

@api_users_bp.route('/api/add-user', methods=['POST'])
def add_user():
    """Add a new user"""
    try:
        data = request.get_json()
        return UserService.add_user(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@api_users_bp.route('/api/get-avatars', methods=['GET'])
def get_avatars():
    """Get all avatars"""
    try:
        return UserService.get_avatars()
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500
