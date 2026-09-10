"""Small atomic balance operations for existing non-game callers."""
from datetime import timedelta
from google.cloud import firestore


class BalanceError(Exception):
    def __init__(self, code, balance=None):
        super().__init__(code)
        self.code, self.balance = code, balance


def debit_balance(db, user_id, amount, default_balance=0):
    if type(amount) is not int or amount <= 0:
        raise ValueError('Amount must be a positive integer')
    ref = db.collection('humanUsers').document(user_id)
    @firestore.transactional
    def apply(tx):
        user = ref.get(transaction=tx)
        if not user.exists:
            raise BalanceError('USER_NOT_FOUND')
        balance = int((user.to_dict() or {}).get('balance', default_balance))
        if balance < amount:
            raise BalanceError('INSUFFICIENT_BALANCE', balance)
        tx.update(ref, {'balance': balance-amount})
        return balance-amount
    return apply(db.transaction(max_attempts=10))


def credit_subscription_reward(db, user_id, expected_renewal, now):
    """Verification happens before this call; recheck entitlement/date in the tx."""
    ref = db.collection('humanUsers').document(user_id)
    @firestore.transactional
    def apply(tx):
        user = ref.get(transaction=tx)
        if not user.exists:
            return False
        data = user.to_dict() or {}
        subscription = data.get('subscription') or {}
        if not subscription.get('isSubscribed') or subscription.get('nextRenewalDate') != expected_renewal:
            return False
        history = list(data.get('subscriptionRewards', []))
        history.append({'amount': 2500, 'date': now.isoformat(), 'type': 'monthly_subscription'})
        tx.update(ref, {'balance': data.get('balance', 200)+2500,
                        'subscriptionRewards': history,
                        'subscription.nextRenewalDate': (now+timedelta(days=30)).isoformat()})
        return True
    return apply(db.transaction(max_attempts=10))


def create_wallet_profile(db, user_id, data):
    """Create-only signup cannot overwrite an existing wallet on a repeated UID."""
    from google.api_core.exceptions import AlreadyExists
    try:
        db.collection('humanUsers').document(user_id).create(data)
    except AlreadyExists:
        return False
    return True
