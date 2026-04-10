from flask import Blueprint, request, jsonify
from services.user.account_lifecycle_service import AccountLifecycleService


user_account_lifecycle_bp = Blueprint('user_account_lifecycle', __name__)


def _extract_uid_from_request() -> str:
    payload = request.get_json(silent=True) or {}
    uid = payload.get('UID') or request.args.get('uid')
    if not uid:
        raise ValueError('UID is required')
    return uid


@user_account_lifecycle_bp.route('/user/request-account-deletion', methods=['POST'])
def request_account_deletion():
    try:
        uid = _extract_uid_from_request()
        return AccountLifecycleService.request_deletion(uid)
    except ValueError as ex:
        return jsonify({'success': False, 'error': str(ex)}), 400
    except Exception as ex:
        return jsonify({'success': False, 'error': str(ex)}), 500


@user_account_lifecycle_bp.route('/user/account-deletion-status', methods=['GET'])
def account_deletion_status():
    try:
        uid = _extract_uid_from_request()
        return AccountLifecycleService.get_deletion_status(uid)
    except ValueError as ex:
        return jsonify({'success': False, 'error': str(ex)}), 400
    except Exception as ex:
        return jsonify({'success': False, 'error': str(ex)}), 500


@user_account_lifecycle_bp.route('/user/deactivate-account', methods=['POST'])
def deactivate_account():
    try:
        uid = _extract_uid_from_request()
        return AccountLifecycleService.deactivate_account(uid)
    except ValueError as ex:
        return jsonify({'success': False, 'error': str(ex)}), 400
    except Exception as ex:
        return jsonify({'success': False, 'error': str(ex)}), 500


@user_account_lifecycle_bp.route('/user/reactivate-account', methods=['POST'])
def reactivate_account():
    try:
        uid = _extract_uid_from_request()
        payload = request.get_json(silent=True) or {}
        cancel_pending_deletion = bool(payload.get('cancelPendingDeletion', True))
        return AccountLifecycleService.reactivate_account(uid, cancel_pending_deletion)
    except ValueError as ex:
        return jsonify({'success': False, 'error': str(ex)}), 400
    except Exception as ex:
        return jsonify({'success': False, 'error': str(ex)}), 500


@user_account_lifecycle_bp.route('/admin/process-account-deletions', methods=['POST'])
def process_account_deletions():
    try:
        data = request.get_json(silent=True) or {}

        uid = data.get('UID')
        force = bool(data.get('force', False))
        limit = int(data.get('limit', 25))

        return AccountLifecycleService.process_pending_jobs(uid=uid, force=force, limit=limit)
    except ValueError as ex:
        return jsonify({'success': False, 'error': str(ex)}), 400
    except Exception as ex:
        return jsonify({'success': False, 'error': str(ex)}), 500


@user_account_lifecycle_bp.route('/user/delete-account-data', methods=['POST'])
def legacy_delete_account_data_alias():
    """Legacy alias maintained for compatibility: now queues deletion instead of immediate purge."""
    return request_account_deletion()
