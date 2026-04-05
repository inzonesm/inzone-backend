# routes/user/referral.py
from flask import Blueprint, request, jsonify
from services.user.referral_service import ReferralService

user_referral_bp = Blueprint('user_referral', __name__)


@user_referral_bp.route('/user/referral/track-accepted', methods=['POST'])
def track_accepted_referral():
	try:
		data = request.get_json() or {}
		return ReferralService.track_accepted_referral(data)
	except ValueError as e:
		return jsonify({'success': False, 'error': str(e)}), 400
	except Exception:
		return jsonify({'success': False, 'error': 'Internal server error'}), 500


@user_referral_bp.route('/user/referral/accepted', methods=['GET'])
def get_accepted_referrals():
	try:
		user_document_id = request.args.get('UserDocumentId')
		limit = request.args.get('Limit', default=50, type=int)
		return ReferralService.get_accepted_referrals(user_document_id, limit)
	except ValueError as e:
		return jsonify({'success': False, 'error': str(e)}), 400
	except Exception:
		return jsonify({'success': False, 'error': 'Internal server error'}), 500
