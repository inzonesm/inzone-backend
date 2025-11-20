# services/monetization/tipping_service.py
from dependencies import db
from typing import Dict, Any
import logging
from flask import jsonify
from google.cloud import firestore
from datetime import datetime, timezone
import uuid

logger = logging.getLogger(__name__)

class TippingService:
    """Service for tipping operations"""

    @staticmethod
    def send_tip(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send a tip from one user to another
        """
        try:
            required_fields = ['sender_id', 'recipient_handle', 'amount']

            if not all(field in data for field in required_fields):
                return jsonify({"error": "Missing required fields"}), 400

            amount = int(data['amount'])
            if amount <= 0:
                return jsonify({"error": "Tip amount must be positive"}), 400

            # Get sender's current balance from humanUsers collection
            sender_ref = db.collection('humanUsers').document(data['sender_id'])
            sender_doc = sender_ref.get()

            if not sender_doc.exists:
                return jsonify({"error": "Sender not found"}), 404

            sender_data = sender_doc.to_dict()
            current_balance = sender_data.get('balance', 200)

            if current_balance < amount:
                return jsonify({"error": "Insufficient balance"}), 400

            # Find recipient by handle (remove @ if present)
            recipient_handle = data['recipient_handle'].lstrip('@')
            recipient_query = db.collection('humanUsers').where('username', '==', recipient_handle).limit(1).stream()
            recipient_doc = next(recipient_query, None)

            if not recipient_doc:
                return jsonify({"error": "Recipient not found"}), 404

            # Generate a unique tip ID
            tip_id = str(uuid.uuid4())
            timestamp = datetime.now(timezone.utc)

            # Create tip data
            tip_data = {
                'id': tip_id,
                'sender_id': data['sender_id'],
                'recipient_id': recipient_doc.id,
                'amount': amount,
                'status': 'completed',
                'createdAt': timestamp
            }

            # Start transaction
            transaction = db.transaction()

            # Update sender's balance and add to sent tips
            transaction.update(sender_ref, {
                'balance': firestore.Increment(-amount),
                'tips_sent': firestore.ArrayUnion([tip_data])
            })

            # Update recipient's received tips
            recipient_ref = db.collection('humanUsers').document(recipient_doc.id)
            transaction.update(recipient_ref, {
                'balance': firestore.Increment(amount),
                'tips_received': firestore.ArrayUnion([tip_data])
            })

            # Commit transaction
            transaction.commit()

            return jsonify({
                "message": "Tip sent successfully",
                "new_balance": current_balance - amount,
                "tip_id": tip_id
            }), 200

        except Exception as e:
            logger.error(f"Error sending tip: {e}")
            return jsonify({"error": str(e)}), 500

    @staticmethod
    def get_tip_transactions(user_id: str) -> Dict[str, Any]:
        """Get user's tipping history"""
        try:
            # Get user document from humanUsers
            user_ref = db.collection('humanUsers').document(user_id)
            user_doc = user_ref.get()

            if not user_doc.exists:
                return jsonify({"error": "User not found"}), 404

            user_data = user_doc.to_dict()

            # Get sent and received tips
            sent_tips = user_data.get('tips_sent', [])
            received_tips = user_data.get('tips_received', [])

            # Process sent tips
            for tip in sent_tips:
                tip['type'] = 'sent'

            # Process received tips
            for tip in received_tips:
                tip['type'] = 'received'

            # Combine and sort all transactions by timestamp (newest first)
            all_transactions = sent_tips + received_tips
            all_transactions.sort(key=lambda x: x.get('createdAt', ''), reverse=True)

            return jsonify({
                "transactions": all_transactions
            }), 200

        except Exception as e:
            logger.error(f"Error getting tip transactions: {e}")
            return jsonify({"error": str(e)}), 500
