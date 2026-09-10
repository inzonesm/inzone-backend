# services/monetization/wallet_service.py
from dependencies import db
from typing import Dict, Any
import logging
from flask import jsonify
from google.cloud import firestore
from datetime import datetime

logger = logging.getLogger(__name__)

class WalletService:
    """Service for wallet and InCash operations"""

    @staticmethod
    def get_balance(user_id: str) -> Dict[str, Any]:
        """Get user's InCash balance"""
        try:
            if not user_id:
                return jsonify({"success": False, "error": "User ID is required"}), 400

            @firestore.transactional
            def apply(transaction):
                user_ref = db.collection('humanUsers').document(user_id)
                user_doc = user_ref.get(transaction=transaction)
                if not user_doc.exists:
                    return jsonify({"success": False, "error": "User not found"}), 404

                user_data = user_doc.to_dict()
                balance = user_data.get('balance')

                # If balance field does not exist, set it to the historical 200 in Firestore
                if balance is None:
                    transaction.update(user_ref, {'balance': 200})
                    balance = 200

                return jsonify({
                    "success": True,
                    "data": {
                        "balance": balance,
                    }
                }), 200
            return apply(db.transaction(max_attempts=10))

        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @staticmethod
    def purchase_incash(data: Dict[str, Any]) -> Dict[str, Any]:
        """Process InCash purchase"""
        try:
            logger.info(f"Purchase request received: {data}")
            user_id = data.get("UserDocumentId")
            package_id = data.get("PackageId")
            platform = data.get("Platform")  # "ios" or "android"
            receipt_data = data.get("ReceiptData")

            if not all([user_id, package_id, platform, receipt_data]):
                logger.error(f"Missing required fields - user_id: {user_id}, package_id: {package_id}, platform: {platform}, receipt_data: {'***' if receipt_data else None}")
                return jsonify({"success": False, "error": "Missing required fields"}), 400

            packages = {
                # iOS packages
                "InCashGold": 2500,  # Monthly subscription
                "InCashElite2025": 1500,  # One-time purchase
                "InCashAdvanced2025": 500,
                "InCashBasic2025": 100,
                # Android packages
                "2025incashgold": 2500,  # Monthly subscription
                "2025incashelite": 1500,  # One-time purchase
                "2025incashadvanced": 500,
                "2025incashbasic": 100,
            }
            if package_id not in packages:
                return jsonify({"success": False, "error": "Invalid package"}), 400

            @firestore.transactional
            def apply(transaction):
                user_ref = db.collection("humanUsers").document(user_id)
                user_doc = user_ref.get(transaction=transaction)

                if not user_doc.exists:
                    return jsonify({"success": False, "error": "User not found"}), 404

                # Get current balance
                user_data = user_doc.to_dict()
                current_balance = user_data.get("balance", 200)

                # Get the amount from the packages dictionary
                amount = packages[package_id]

                # Update balance
                new_balance = current_balance + amount

                # Record purchase history
                purchase_history = user_data.get("purchaseHistory", [])
                purchase_history.append(
                    {
                        "packageId": package_id,
                        "platform": platform,
                        "amount": amount,
                        "date": datetime.now().isoformat(),
                        "receiptData": receipt_data,
                    }
                )

                # Check if this is a subscription purchase
                is_subscription = package_id in ["InCashGold", "2025incashgold"]

                # If it's a subscription, update subscription status
                if is_subscription:
                    from datetime import timedelta
                    subscription_data = {
                        "isSubscribed": True,
                        "subscriptionType": "gold",
                        "subscriptionId": package_id,
                        "startDate": datetime.now().isoformat(),
                        "nextRenewalDate": (datetime.now() + timedelta(days=30)).isoformat(),
                    }
                    transaction.update(user_ref,
                        {
                            "balance": new_balance,
                            "purchaseHistory": purchase_history,
                            "subscription": subscription_data,
                        }
                    )
                else:
                    # For one-time purchases
                    transaction.update(user_ref,
                        {"balance": new_balance, "purchaseHistory": purchase_history}
                    )

                return jsonify(
                    {
                        "success": True,
                        "data": {
                            "balance": new_balance,
                            "packageId": package_id,
                            "amountAdded": amount,
                        },
                    }
                ), 200

            return apply(db.transaction(max_attempts=10))

        except Exception as e:
            logger.error(f"Error processing purchase: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @staticmethod
    def spend_incash(data: Dict[str, Any]) -> Dict[str, Any]:
        """Spend InCash on various purposes"""
        try:
            user_id = data.get('UserDocumentId')
            amount = data.get('Amount')
            purpose = data.get('Purpose')  # 'group_access' or other future purposes
            group_id = data.get('GroupId')  # Only required for group_access purpose

            if not all([user_id, amount, purpose]):
                return jsonify({"success": False, "error": "Missing required fields"}), 400

            if type(amount) is not int or amount <= 0:
                return jsonify({'success': False, 'error': 'Amount must be a positive integer'}), 400

            if purpose == 'group_access' and not group_id:
                return jsonify({"success": False, "error": "GroupId is required for group access"}), 400

            # Get user document
            @firestore.transactional
            def apply(transaction):
                user_ref = db.collection('humanUsers').document(user_id)
                user_doc = user_ref.get(transaction=transaction)

                if not user_doc.exists:
                    return jsonify({"success": False, "error": "User not found"}), 404

                # Get current balance
                user_data = user_doc.to_dict()
                current_balance = user_data.get('balance', 200)

                # Check if user has enough balance
                if current_balance < amount:
                    return jsonify({
                        "success": False,
                        "error": f"Insufficient balance. You have {current_balance} InCash, but {amount} is required."
                    }), 400

                group_ref = db.collection('conversations').document(group_id) if purpose == 'group_access' else None
                group_doc = group_ref.get(transaction=transaction) if group_ref else None

                # Update balance
                new_balance = current_balance - amount

                # Record transaction history
                transaction_history = user_data.get('transactionHistory', [])
                transaction_history.append({
                    'type': 'spend',
                    'amount': amount,
                    'purpose': purpose,
                    'groupId': group_id if purpose == 'group_access' else None,
                    'date': datetime.now().isoformat()
                })

                # Update user document
                transaction.update(user_ref, {
                    'balance': new_balance,
                    'transactionHistory': transaction_history
                })

                # If purpose is group_access, add user to group participants if not already there
                if purpose == 'group_access':
                    # Check if group exists in conversations collection

                    if group_doc.exists:
                        group_data = group_doc.to_dict()
                        participants = group_data.get('participants', [])

                        # Add user to participants if not already there
                        if user_id not in participants:
                            participants.append(user_id)
                            transaction.update(group_ref, {
                                'participants': participants,
                                'lastMessageTime': firestore.SERVER_TIMESTAMP,
                                'lastMessage': 'A new user joined the group'
                            })
                    else:
                        # Create group document if it doesn't exist
                        transaction.set(group_ref, {
                            'isGroupChat': True,
                            'participants': [user_id],
                            'lastMessageTime': firestore.SERVER_TIMESTAMP,
                            'lastMessage': 'A new user joined the group'
                        })

                return jsonify({
                    "success": True,
                    "data": {
                        "balance": new_balance,
                        "amountSpent": amount,
                        "purpose": purpose
                    }
                }), 200

            return apply(db.transaction(max_attempts=10))

        except Exception as e:
            logger.error(f"Error spending InCash: {e}")
            return jsonify({"success": False, "error": str(e)}), 500
