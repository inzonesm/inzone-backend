"""Transactional persistence for the existing tier API; no route/auth changes."""
from datetime import datetime, timezone
import uuid
from google.cloud import firestore


class LegacyPurchaseError(Exception):
    def __init__(self, code, message, status=400, details=None):
        super().__init__(message)
        self.code, self.status, self.details = code, status, details


def purchase_legacy_coins(db, *, user_id, game_id, title, description, coins,
                          commission_rate, transaction_id=None):
    receipt_id = transaction_id or uuid.uuid4().hex
    if not isinstance(receipt_id, str) or '/' in receipt_id or not receipt_id or len(receipt_id.encode()) > 1400:
        raise LegacyPurchaseError('INVALID_TRANSACTION_ID', 'Invalid transactionId')
    receipt_ref = db.collection('game_coin_transactions').document(receipt_id)
    wallet_ref = db.collection('humanUsers').document(user_id)
    summary_ref = db.collection('game_revenue_summary').document(game_id)
    now = datetime.now(timezone.utc)
    description = description or title

    @firestore.transactional
    def apply(tx):
        previous = receipt_ref.get(transaction=tx)
        if previous.exists:
            receipt = previous.to_dict()
            expected = dict(user_id=user_id, game_id=game_id, title=title,
                            description=description, coins=coins)
            if any(receipt.get(k) != v for k, v in expected.items()):
                raise LegacyPurchaseError('IDEMPOTENCY_CONFLICT', 'transactionId already used', 409)
            if receipt.get('source') != 'legacy-tier-atomic-v1' or not receipt.get('response'):
                raise LegacyPurchaseError('LEGACY_RECEIPT_REQUIRES_RECONCILIATION',
                                          'Existing receipt cannot be safely replayed; do not charge again', 409)
            return receipt['response'], True, None
        wallet = wallet_ref.get(transaction=tx)
        if not wallet.exists:
            raise LegacyPurchaseError('USER_NOT_FOUND', 'User not found', 404)
        # Preserve the historical legacy default; reads now participate in the tx.
        balance = int((wallet.to_dict() or {}).get('balance', 200))
        if balance < coins:
            raise LegacyPurchaseError('INSUFFICIENT_BALANCE', 'Insufficient balance',
                                      details=dict(currentBalance=balance, required=coins))
        summary = summary_ref.get(transaction=tx)
        previous_session = (summary.to_dict() or {}).get('last_session_id') if summary.exists else None
        commission = int(round(coins * commission_rate))
        response = dict(transactionId=receipt_id, userId=user_id, gameId=game_id,
                        title=title, description=description, coins=coins,
                        commissionCoins=commission, developerCoins=coins-commission,
                        commissionRate=commission_rate, newBalance=balance-coins,
                        currency='Coin', confirmation='Coin transaction confirmed')
        tx.update(wallet_ref, {'balance': balance-coins})
        tx.create(receipt_ref, dict(transaction_id=receipt_id, user_id=user_id, game_id=game_id,
                                   title=title, description=description, coins=coins,
                                   commission_coins=commission, developer_coins=coins-commission,
                                   commission_rate=commission_rate, status='confirmed', currency='Coin',
                                   created_at=firestore.SERVER_TIMESTAMP, created_at_local=now.isoformat(),
                                   source='legacy-tier-atomic-v1', response=response))
        tx.set(summary_ref, dict(game_id=game_id, transaction_count=firestore.Increment(1),
                                gross_coins=firestore.Increment(coins),
                                commission_coins=firestore.Increment(commission),
                                developer_payout_coins=firestore.Increment(coins-commission),
                                tier_breakdown={str(coins): firestore.Increment(1)},
                                last_transaction_title=title, last_transaction_description=description,
                                last_transaction_at=firestore.SERVER_TIMESTAMP,
                                commission_rate=commission_rate, updated_at=firestore.SERVER_TIMESTAMP), merge=True)
        return response, False, previous_session
    return apply(db.transaction(max_attempts=10))
