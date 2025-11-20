# routes/monetization/subscription.py
from flask import Blueprint, request, jsonify
from services.monetization.subscription_service import SubscriptionService

subscription_bp = Blueprint('subscription', __name__)

@subscription_bp.route('/wallet/update-subscription', methods=['POST'])
def update_subscription():
    try:
        data = request.json
        return SubscriptionService.update_subscription(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@subscription_bp.route('/wallet/subscription-status', methods=['GET'])
def subscription_status():
    try:
        user_id = request.args.get('UserDocumentId')
        verify = request.args.get('verify', 'false').lower() == 'true'
        return SubscriptionService.get_subscription_status(user_id, verify)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@subscription_bp.route('/wallet/process-subscription-rewards', methods=['POST'])
def process_subscription_rewards():
    try:
        return SubscriptionService.process_subscription_rewards()
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500
