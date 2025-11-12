# routes/admin/groups.py
from flask import Blueprint, request, jsonify
from services.admin.group_service import AdminGroupService

admin_groups_bp = Blueprint('admin_groups', __name__)


@admin_groups_bp.route('/admin/groups/create', methods=['POST'])
def create_group():
    """Create a new group"""
    try:
        data = request.json
        return AdminGroupService.create_group(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
