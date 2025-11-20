# routes/admin/store.py
from flask import Blueprint, request, jsonify
from services.admin.store_service import AdminStoreService

admin_store_bp = Blueprint('admin_store', __name__)


@admin_store_bp.route('/admin/store/add-item', methods=['POST'])
def add_item():
    """Add an item to the store"""
    try:
        data = request.json
        return AdminStoreService.add_item(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
