# routes/monetization/tipping.py
from flask import Blueprint, request, jsonify
from services.monetization.tipping_service import TippingService

tipping_bp = Blueprint('tipping', __name__)

@tipping_bp.route('/user/tip/send', methods=['POST'])
def send_tip():
    """Send a tip from one user to another"""
    try:
        data = request.get_json()
        return TippingService.send_tip(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@tipping_bp.route('/user/tip/transactions/<user_id>', methods=['GET'])
def get_tip_transactions(user_id):
    """Get user's tipping history"""
    try:
        return TippingService.get_tip_transactions(user_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500
