# routes/admin/maintenance.py
from flask import Blueprint, jsonify
from services.admin.maintenance_service import AdminMaintenanceService
from dependencies import db

admin_maintenance_bp = Blueprint('admin_maintenance', __name__)


@admin_maintenance_bp.route('/api/admin/fix-missing-uid', methods=['POST'])
def fix_missing_uid():
    """Fix humanUsers documents that are missing the 'uid' field"""
    result, status = AdminMaintenanceService.fix_missing_uid(db)
    return jsonify(result), status
