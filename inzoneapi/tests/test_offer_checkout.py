"""Real Firestore emulator transaction tests; no production credentials accepted."""
import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from unittest.mock import patch

from flask import Flask
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from routes.api.offer_checkout import create_offer_checkout_blueprint
from services.minigames.offer_checkout import OfferCheckout, CheckoutError, key


@unittest.skipUnless(os.environ.get('FIRESTORE_EMULATOR_HOST'), 'Requires Firestore emulator')
class CheckoutTests(unittest.TestCase):
    def setUp(self):
        self.db = firestore.Client(project='demo-inzone-checkout', credentials=AnonymousCredentials())
        self.game = 'game-' + uuid.uuid4().hex
        self.player = 'player-' + uuid.uuid4().hex
        self.owner = 'owner-' + uuid.uuid4().hex
        self.service = OfferCheckout(self.db)
        self.offers = [dict(id='unlock', title='Full game', kind='durable', coins=37, quantity=1),
                       dict(id='lives', title='Five lives', kind='consumable', coins=23, quantity=5)]
        self.service.ref('html_games',self.game).set(dict(uploaderId=self.owner,status='approved'))
        self.service.ref('humanUsers',self.player).set(dict(balance=200))
        self.save_draft(self.offers)
        self.version = self.service.publish(self.game,self.owner,key(self.offers))['version']
        self.enabled = True
        app = Flask(__name__)
        def verify(token):
            if token == 'invalid': raise ValueError('Invalid')
            return {'uid': token}
        app.register_blueprint(create_offer_checkout_blueprint(self.service,verify,lambda:self.enabled))
        self.client=app.test_client()
        self.path='/api/game-sdk/v2/games/'+self.game
        self.headers={'Authorization':'Bearer '+self.player}

    def tearDown(self): self.db.close()
    def save_draft(self, offers):
        self.service.ref('game_offer_drafts',self.game).set(dict(ownerUid=self.owner,offers=offers))
    def buy(self, offer='lives', request_id='request-1', version=None):
        return self.service.purchase(self.game,self.player,offer,version or self.version,request_id)
    def balance(self): return self.service.ref('humanUsers',self.player).get().to_dict()['balance']
    def summary(self): return self.service.ref('game_revenue_summary',self.game).get().to_dict()
    def assert_code(self, code, operation):
        with self.assertRaises(CheckoutError) as caught: operation()
        self.assertEqual(caught.exception.code,code)

    def test_consumable_accounting_and_request_recovery(self):
        receipt=self.buy()
        self.assertEqual(receipt['coins'],23)
        self.assertEqual(self.balance(),177)
        self.assertEqual(self.service.inventory(self.game,self.player,'lives')['quantity'],5)
        self.assertEqual(self.summary()['gross_coins'],23)
        self.assertEqual(self.summary()['developer_payout_coins'],21)
        self.assertEqual(self.summary()['commission_coins'],2)
        self.assertEqual(self.buy(),receipt)
        self.assertEqual(self.service.receipt(self.game,self.player,'request-1'),receipt)
        self.assertEqual(self.summary()['transaction_count'],1)
        self.assertEqual(self.balance(),177)

    def test_durable_restore_new_request_no_charge_and_binding(self):
        first=self.buy('unlock')
        again=self.buy('unlock','another-request')
        self.assertEqual(first,again)
        self.assertEqual(self.balance(),163)
        self.assertEqual(self.summary()['transaction_count'],1)
        self.assertEqual(self.service.receipt(self.game,self.player,'another-request'),first)
        self.assert_code('IDEMPOTENCY_CONFLICT',lambda:self.buy('lives','another-request'))

    def test_catalog_price_change_requires_new_confirmation(self):
        self.offers[1]['coins']=71
        self.save_draft(self.offers)
        current=self.service.publish(self.game,self.owner,key(self.offers))['version']
        self.assert_code('OFFER_CHANGED',lambda:self.buy())
        self.assertEqual(self.balance(),200)
        self.assertEqual(self.buy(version=current)['coins'],71)

    def test_retry_after_removal_and_cross_user_recovery(self):
        first=self.buy()
        self.service.ref('game_offer_catalogs',self.game).delete()
        self.service.ref('html_games',self.game).delete()
        self.assertEqual(self.buy(),first)
        self.assertEqual(self.service.inventory(self.game,self.player,'lives')['quantity'],5)
        self.assert_code('RECEIPT_NOT_FOUND',lambda:self.service.receipt(self.game,'other','request-1'))

    def test_simultaneous_same_request_debits_once(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            receipts=list(pool.map(lambda _:self.buy(),range(4)))
        self.assertTrue(all(r==receipts[0] for r in receipts))
        self.assertEqual(self.balance(),177)
        self.assertEqual(self.summary()['transaction_count'],1)
        self.assertEqual(self.service.inventory(self.game,self.player,'lives')['quantity'],5)

    def test_simultaneous_durable_requests_debit_once(self):
        with ThreadPoolExecutor(max_workers=3) as pool:
            receipts=list(pool.map(lambda i:self.buy('unlock','request-'+str(i)),range(3)))
        self.assertTrue(all(r==receipts[0] for r in receipts))
        self.assertEqual(self.balance(),163)
        self.assertEqual(self.summary()['transaction_count'],1)

    def test_simultaneous_distinct_requests_cannot_overspend(self):
        self.service.ref('humanUsers',self.player).update({'balance':30})
        def attempt(i):
            try: return self.buy(request_id='request-'+str(i))
            except CheckoutError as exc: return exc.code
        with ThreadPoolExecutor(max_workers=3) as pool: results=list(pool.map(attempt,range(3)))
        self.assertEqual(sum(isinstance(r,dict) for r in results),1)
        self.assertEqual(results.count('INSUFFICIENT_BALANCE'),2)
        self.assertEqual(self.balance(),7)
        self.assertEqual(self.summary()['transaction_count'],1)

    def test_abort_after_buffered_debit_has_no_partial_writes(self):
        tx=self.db.transaction(); original=tx.set
        def fail(ref,*args,**kwargs):
            if ref.parent.id=='game_revenue_summary': raise RuntimeError('Injected failure before commit')
            return original(ref,*args,**kwargs)
        with patch.object(self.db,'transaction',return_value=tx),patch.object(tx,'set',side_effect=fail):
            with self.assertRaises(RuntimeError):self.buy()
        self.assertEqual(self.balance(),200)
        self.assertIsNone(self.summary())
        self.assert_code('RECEIPT_NOT_FOUND',lambda:self.service.receipt(self.game,self.player,'request-1'))
        self.assertEqual(self.service.inventory(self.game,self.player,'lives')['quantity'],0)

    def test_invalid_balance_does_not_create_default_money(self):
        self.service.ref('humanUsers',self.player).set({})
        self.assert_code('INSUFFICIENT_BALANCE',lambda:self.buy())
        self.service.ref('humanUsers',self.player).set({'balance':True})
        self.assert_code('INVALID_BALANCE',lambda:self.buy())

    def test_owner_transfer_blocks_stale_catalog(self):
        self.service.ref('html_games',self.game).update({'uploaderId':'new-owner'})
        self.assert_code('CATALOG_UNAVAILABLE',lambda:self.buy())
        self.assert_code('NOT_GAME_OWNER',lambda:self.service.publish(self.game,self.owner,key(self.offers)))

    def test_publish_checks_owner_exact_draft_and_stable_kind(self):
        self.assert_code('NOT_GAME_OWNER',lambda:self.service.publish(self.game,self.player,key(self.offers)))
        self.assert_code('DRAFT_CHANGED',lambda:self.service.publish(self.game,self.owner,'stale'))
        self.offers[0]['kind']='consumable'
        self.save_draft(self.offers)
        self.assert_code('PRODUCT_KIND_IMMUTABLE',lambda:self.service.publish(self.game,self.owner,key(self.offers)))

    def test_rate_limit_does_not_block_retries(self):
        first=self.buy()
        self.service.ref('game_checkout_limits',key(self.player,self.game)).set({
            'minute':int(datetime.now(timezone.utc).timestamp())//60,'count':30})
        self.assertEqual(self.buy(),first)
        self.assert_code('RATE_LIMITED',lambda:self.buy(request_id='new-request'))

    def test_http_auth_input_and_real_transaction(self):
        payload=dict(offerId='lives',catalogVersion=self.version,requestId='http-request')
        for headers in ({},{'Authorization':'Bearer invalid'}):
            self.assertEqual(self.client.post(self.path+'/purchases',json=payload,headers=headers).status_code,401)
        for extra in ({'coins':1},{'userId':self.owner},{'quantity':100}):
            self.assertEqual(self.client.post(self.path+'/purchases',json={**payload,**extra},headers=self.headers).status_code,400)
        response=self.client.post(self.path+'/purchases',json=payload,headers=self.headers)
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(response.json['data']['coins'],23)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        recovered=self.client.get(self.path+'/purchases/http-request',headers=self.headers)
        self.assertEqual(recovered.json,response.json)
        self.assertEqual(self.client.get(self.path+'/inventory/lives',headers=self.headers).json['data']['quantity'],5)

    def test_disabled_and_unpublished_drafts(self):
        self.enabled=False
        self.assertEqual(self.client.get(self.path+'/catalog').status_code,404)
        self.assertEqual(self.client.post(self.path+'/purchases',json={},headers=self.headers).status_code,404)
        self.enabled=True
        self.offers[1]['coins']=1
        self.save_draft(self.offers)
        self.assertEqual(self.client.get(self.path+'/catalog').json['data']['offers'][1]['coins'],23)
        self.assertEqual(self.buy()['coins'],23)

if __name__=='__main__':unittest.main()
