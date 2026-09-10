"""Versioned offer checkout. All funds and fulfillment writes share one transaction."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import uuid

from google.cloud import firestore
from routes.api.game_offers import validate_offers


class CheckoutError(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code, self.status = code, status


def key(*parts):
    return sha256(json.dumps(parts, separators=(',', ':'), sort_keys=True).encode()).hexdigest()


def read(ref, tx):
    snapshot = ref.get(transaction=tx)
    return snapshot.to_dict() if snapshot.exists else None


def approved(game):
    if not game or game.get('status') != 'approved':
        raise CheckoutError('GAME_UNAVAILABLE', 404)


class OfferCheckout:
    def __init__(self, db, commission_rate=0.10):
        self.db = db
        self.commission_rate = commission_rate

    def ref(self, collection, doc):
        return self.db.collection(collection).document(doc)

    def publish(self, game_id, uid, expected_draft):
        """Owner explicitly approves the exact draft content they inspected."""
        version = uuid.uuid4().hex
        @firestore.transactional
        def apply(tx):
            game = read(self.ref('html_games', game_id), tx)
            approved(game)
            if game.get('uploaderId') != uid:
                raise CheckoutError('NOT_GAME_OWNER', 403)
            draft = read(self.ref('game_offer_drafts', game_id), tx)
            if not draft or draft.get('ownerUid') != uid:
                raise CheckoutError('DRAFT_NOT_FOUND', 404)
            try:
                offers = validate_offers({'offers': draft.get('offers')})
            except ValueError:
                raise CheckoutError('INVALID_DRAFT', 409)
            if key(offers) != expected_draft:
                raise CheckoutError('DRAFT_CHANGED', 409)
            catalog_ref = self.ref('game_offer_catalogs', game_id)
            previous = read(catalog_ref, tx) or {}
            # Retain product kinds even when an offer is removed. Reusing an ID
            # for a different kind would reinterpret an existing entitlement.
            kinds = dict(previous.get('productKinds', {}))
            for offer in offers:
                if offer['id'] in kinds and kinds[offer['id']] != offer['kind']:
                    raise CheckoutError('PRODUCT_KIND_IMMUTABLE', 409)
                kinds[offer['id']] = offer['kind']
            if len(kinds) > 1000:
                raise CheckoutError('PRODUCT_LIMIT', 409)
            catalog = dict(gameId=game_id, ownerUid=uid, version=version,
                           offers=offers, productKinds=kinds)
            tx.set(catalog_ref, catalog)
            return dict(gameId=game_id, version=version, offers=offers)
        return apply(self.db.transaction())

    def catalog(self, game_id):
        @firestore.transactional
        def get(tx):
            game = read(self.ref('html_games', game_id), tx)
            approved(game)
            catalog = read(self.ref('game_offer_catalogs', game_id), tx)
            if not catalog or catalog.get('ownerUid') != game.get('uploaderId'):
                raise CheckoutError('CATALOG_UNAVAILABLE', 404)
            return {k: catalog[k] for k in ('gameId', 'version', 'offers')}
        return get(self.db.transaction())

    def purchase(self, game_id, uid, offer_id, version, request_id):
        receipt_id = 'offer_' + key(uid, game_id, request_id)
        receipt_ref = self.ref('game_coin_transactions', receipt_id)
        request_ref = self.ref('game_offer_requests', key(uid, game_id, request_id))
        item_ref = self.ref('game_product_inventory', key(uid, game_id, offer_id))
        now = datetime.now(timezone.utc)
        @firestore.transactional
        def apply(tx):
            prior = read(request_ref, tx)
            if prior:
                if prior.get('offer_id') != offer_id or prior.get('catalog_version') != version:
                    raise CheckoutError('IDEMPOTENCY_CONFLICT', 409)
                saved = read(self.ref('game_coin_transactions', prior['transactionId']), tx)
                if not saved:
                    raise CheckoutError('RECEIPT_UNAVAILABLE', 503)
                return saved['response']
            game = read(self.ref('html_games', game_id), tx)
            approved(game)
            item = read(item_ref, tx)
            # Durable ownership survives catalog edits/removal. Restore returns
            # the original purchase result and does not debit another coin.
            if item and item.get('kind') == 'durable':
                original = read(self.ref('game_coin_transactions', item['transactionId']), tx)
                if not original:
                    raise CheckoutError('RECEIPT_UNAVAILABLE', 503)
                tx.create(request_ref, dict(offer_id=offer_id, catalog_version=version,
                                            transactionId=item['transactionId']))
                return original['response']
            catalog = read(self.ref('game_offer_catalogs', game_id), tx)
            if not catalog or catalog.get('ownerUid') != game.get('uploaderId'):
                raise CheckoutError('CATALOG_UNAVAILABLE', 404)
            if catalog.get('version') != version:
                raise CheckoutError('OFFER_CHANGED', 409)
            offer = next((x for x in catalog['offers'] if x['id'] == offer_id), None)
            if offer is None:
                raise CheckoutError('OFFER_UNAVAILABLE', 404)
            try:
                validate_offers({'offers': [offer]})
            except ValueError:
                raise CheckoutError('INVALID_CATALOG', 503)
            wallet_ref = self.ref('humanUsers', uid)
            wallet = read(wallet_ref, tx)
            if wallet is None:
                raise CheckoutError('USER_NOT_FOUND', 404)
            balance = wallet.get('balance', 0)
            if type(balance) is not int or balance < 0:
                raise CheckoutError('INVALID_BALANCE', 409)
            coins = offer['coins']
            if balance < coins:
                raise CheckoutError('INSUFFICIENT_BALANCE', 400)
            quantity = (item or {}).get('quantity', 0)
            if type(quantity) is not int or quantity < 0 or (item and item['kind'] != offer['kind']):
                raise CheckoutError('INVALID_INVENTORY', 409)
            quantity += offer['quantity']
            if quantity > 2**53 - 1:
                raise CheckoutError('INVENTORY_LIMIT', 409)
            limit_ref = self.ref('game_checkout_limits', key(uid, game_id))
            limit = read(limit_ref, tx) or {}
            minute = int(now.timestamp()) // 60
            count = limit.get('count', 0) if limit.get('minute') == minute else 0
            if count >= 30:
                raise CheckoutError('RATE_LIMITED', 429)
            commission = int(round(coins * self.commission_rate))
            entitlement = dict(gameId=game_id, offerId=offer_id, kind=offer['kind'],
                               quantity=quantity, transactionId=receipt_id)
            response = dict(transactionId=receipt_id, gameId=game_id, offerId=offer_id,
                            catalogVersion=version, coins=coins, currency='Coin',
                            commissionCoins=commission, developerCoins=coins-commission,
                            newBalance=balance-coins, entitlement=entitlement)
            # Existing accounting field names keep receipts/dashboard queries usable.
            receipt = dict(transaction_id=receipt_id, user_id=uid, game_id=game_id,
                           offer_id=offer_id, catalog_version=version,
                           title=offer['title'], description=offer['title'], coins=coins,
                           commission_coins=commission, developer_coins=coins-commission,
                           commission_rate=self.commission_rate, status='confirmed',
                           currency='Coin', created_at=now, created_at_local=now.isoformat(),
                           source='offer-checkout-v1', response=response)
            tx.update(wallet_ref, {'balance': balance-coins})
            tx.create(receipt_ref, receipt)
            tx.create(request_ref, dict(offer_id=offer_id, catalog_version=version, transactionId=receipt_id))
            tx.set(item_ref, {**entitlement, 'userId': uid})
            tx.set(limit_ref, dict(minute=minute, count=count+1))
            tx.set(self.ref('game_revenue_summary', game_id), {
                'game_id': game_id, 'transaction_count': firestore.Increment(1),
                'gross_coins': firestore.Increment(coins),
                'commission_coins': firestore.Increment(commission),
                'developer_payout_coins': firestore.Increment(coins-commission),
                'offer_breakdown': {offer_id: firestore.Increment(1)},
                'last_transaction_title': offer['title'],
                'last_transaction_description': offer['title'],
                'last_transaction_at': now, 'updated_at': now,
                'commission_rate': self.commission_rate,
            }, merge=True)
            return response
        return apply(self.db.transaction(max_attempts=10))

    def inventory(self, game_id, uid, offer_id):
        # Recovery must also work if the game is removed or catalog is unpublished.
        snapshot = self.ref('game_product_inventory', key(uid, game_id, offer_id)).get()
        if not snapshot.exists:
            return dict(gameId=game_id, offerId=offer_id, owned=False, quantity=0)
        data = snapshot.to_dict()
        return {**{k: data[k] for k in ('gameId', 'offerId', 'kind', 'quantity', 'transactionId')},
                'owned': data['quantity'] > 0}

    def receipt(self, game_id, uid, request_id):
        request = self.ref('game_offer_requests', key(uid, game_id, request_id)).get()
        if not request.exists:
            raise CheckoutError('RECEIPT_NOT_FOUND', 404)
        snapshot = self.ref('game_coin_transactions', request.to_dict()['transactionId']).get()
        if not snapshot.exists:
            raise CheckoutError('RECEIPT_UNAVAILABLE', 503)
        return snapshot.to_dict()['response']
