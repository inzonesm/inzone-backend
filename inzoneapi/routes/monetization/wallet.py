# routes/monetization/wallet.py
from flask import Blueprint, request, jsonify
from services.monetization.wallet_service import WalletService

wallet_bp = Blueprint('wallet', __name__)

@wallet_bp.route('/wallet/balance', methods=['GET'])
def get_balance():
    try:
        user_id = request.args.get('UserDocumentId')
        return WalletService.get_balance(user_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@wallet_bp.route('/wallet/purchase-incash', methods=['POST'])
def purchase_incash():
    try:
        data = request.get_json()
        return WalletService.purchase_incash(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@wallet_bp.route('/wallet/spend-incash', methods=['POST'])
def spend_incash():
    try:
        data = request.get_json()
        return WalletService.spend_incash(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500
