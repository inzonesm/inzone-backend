# routes/groups/access.py
from flask import Blueprint, request, jsonify
from services.groups.access_service import GroupAccessService

groups_access_bp = Blueprint('groups_access', __name__)


@groups_access_bp.route('/groups/available', methods=['GET'])
def available_groups():
    """Get all available groups"""
    try:
        return GroupAccessService.get_available_groups()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@groups_access_bp.route('/groups/join', methods=['POST'])
def join_group():
    """Join a group with a subscription tier"""
    try:
        data = request.json
        return GroupAccessService.join_group(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@groups_access_bp.route('/groups/user-access', methods=['GET'])
def user_access():
    """Get all groups a user has access to"""
    try:
        user_id = request.args.get('user_id')
        return GroupAccessService.get_user_access(user_id)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
