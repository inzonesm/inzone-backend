# routes/admin/users.py
from flask import Blueprint, request, jsonify
from services.admin.user_service import AdminUserService

admin_users_bp = Blueprint('admin_users', __name__)


@admin_users_bp.route('/api/admin/search-user', methods=['GET'])
def search_human_user():
    """Search for human users by name"""
    try:
        search_term = request.args.get('name', '')
        return AdminUserService.search_user(search_term)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
