"""Mixed production service code against Firestore emulator; external startup is stubbed."""
import importlib
import sys
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from unittest.mock import patch

from flask import Flask
from google.cloud import firestore
import test_offer_checkout as checkout_tests
from services.minigames.legacy_coin_purchase import purchase_legacy_coins, LegacyPurchaseError
from services.monetization.balance_updates import debit_balance, credit_subscription_reward, create_wallet_profile


class WalletCompatibilityTests(checkout_tests.CheckoutTests):
    # Inherit all 14 new-checkout regression tests and the emulator setup/teardown.
    def setUp(self):
        super().setUp()
        self.app=Flask('wallet-tests')
        # Only replace startup dependency initialization. Service modules and all
        # database operations below are the real modified implementation.
        with patch.dict(sys.modules, {'dependencies': types.SimpleNamespace(db=self.db)}):
            self.wallet=importlib.import_module('services.monetization.wallet_service')
            self.tips=importlib.import_module('services.monetization.tipping_service')
            self.groups=importlib.import_module('services.groups.access_service')
            self.store=importlib.import_module('routes.monetization.store')
            self.social=importlib.import_module('services.minigames.social_loop_service')
        for module in (self.wallet,self.tips,self.groups,self.store,self.social):module.db=self.db
        self.app.register_blueprint(self.store.store_bp)

    def legacy(self, request_id='legacy-1', coins=10):
        return purchase_legacy_coins(self.db,user_id=self.player,game_id=self.game,
                                    title='Retry',description='Retry',coins=coins,
                                    commission_rate=.10,transaction_id=self.player+'-'+request_id)[0]

    def call(self, function, *args):
        with self.app.app_context():
            result,status=function(*args)
            return result.get_json(),status

    def test_mixed_tier_offer_preserve_balance_receipts_and_summaries(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            old=pool.submit(self.legacy)
            new=pool.submit(self.buy)
            old,new=old.result(),new.result()
        self.assertEqual(self.balance(),167)
        summary=self.summary()
        self.assertEqual(summary['transaction_count'],2)
        self.assertEqual(summary['gross_coins'],33)
        self.assertEqual(summary['commission_coins'],3)
        self.assertEqual(summary['developer_payout_coins'],30)
        self.assertEqual(summary['tier_breakdown'],{'10':1})
        self.assertEqual(summary['offer_breakdown'],{'lives':1})
        self.assertTrue(self.service.ref('game_coin_transactions',old['transactionId']).get().exists)
        self.assertTrue(self.service.ref('game_coin_transactions',new['transactionId']).get().exists)

    def test_mixed_tier_offer_cannot_overspend(self):
        self.service.ref('humanUsers',self.player).update({'balance':25})
        def attempt(fn):
            try:return fn()
            except (LegacyPurchaseError, checkout_tests.CheckoutError) as exc:return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,[self.legacy,self.buy]))
        self.assertEqual(sum(isinstance(r,dict) for r in results),1)
        self.assertEqual(results.count('INSUFFICIENT_BALANCE'),1)
        self.assertEqual(self.balance(),25-self.summary()['gross_coins'])

    def test_legacy_retry_same_request_debits_once(self):
        with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(lambda _:self.legacy(),range(3)))
        self.assertTrue(all(r==results[0] for r in results))
        self.assertEqual(self.balance(),190)
        self.assertEqual(self.summary()['transaction_count'],1)
        with self.assertRaises(LegacyPurchaseError) as exc:self.legacy(coins=50)
        self.assertEqual(exc.exception.code,'IDEMPOTENCY_CONFLICT')

    def test_historical_receipt_cannot_be_charged_again(self):
        self.service.ref('game_coin_transactions',self.player+'-legacy-1').set(dict(user_id=self.player,
            game_id=self.game,title='Retry',description='Retry',coins=10,status='confirmed'))
        with self.assertRaises(LegacyPurchaseError) as exc:self.legacy()
        self.assertEqual(exc.exception.code,'LEGACY_RECEIPT_REQUIRES_RECONCILIATION')
        self.assertEqual(self.balance(),200)

    def test_legacy_api_response_and_activity_failure(self):
        payload=dict(userId=self.player,gameId=self.game,title='Retry',transactionId='api-request')
        with patch.object(self.social,'_record_game_activity',side_effect=RuntimeError('telemetry unavailable')):
            response,status=self.call(self.social.SocialLoopService.purchase_coin_tier,payload,10)
            replay,replay_status=self.call(self.social.SocialLoopService.purchase_coin_tier,payload,10)
        self.assertEqual(status,200);self.assertEqual(replay_status,200)
        self.assertEqual(response['data'],replay['data'])
        self.assertEqual(set(response),{'success','data','tier','sdk','payment'})
        self.assertEqual(set(response['data']),{'transactionId','userId','gameId','title','description',
            'coins','commissionCoins','developerCoins','commissionRate','newBalance','currency','confirmation'})
        self.assertEqual(response['tier']['tier'],'tier-10')
        self.assertEqual(self.balance(),190)

    def test_legacy_abort_rolls_back_all_financial_writes(self):
        tx=self.db.transaction();original=tx.set
        def fail(ref,*args,**kwargs):
            if ref.parent.id=='game_revenue_summary':raise RuntimeError('Injected failure')
            return original(ref,*args,**kwargs)
        with patch.object(self.db,'transaction',return_value=tx),patch.object(tx,'set',side_effect=fail):
            with self.assertRaises(RuntimeError):self.legacy()
        self.assertEqual(self.balance(),200)
        self.assertFalse(self.service.ref('game_coin_transactions',self.player+'-legacy-1').get().exists)
        self.assertIsNone(self.summary())

    def test_topup_and_offer_keep_both_changes(self):
        payload=dict(UserDocumentId=self.player,PackageId='InCashBasic2025',Platform='ios',ReceiptData='test-only')
        with ThreadPoolExecutor(max_workers=2) as pool:
            credit=pool.submit(self.call,self.wallet.WalletService.purchase_incash,payload)
            debit=pool.submit(self.buy)
            self.assertEqual(credit.result()[1],200);debit.result()
        self.assertEqual(self.balance(),277)
        self.assertEqual(len(self.service.ref('humanUsers',self.player).get().to_dict()['purchaseHistory']),1)

    def test_general_spend_and_offer_cannot_overspend(self):
        self.service.ref('humanUsers',self.player).update({'balance':30})
        payload=dict(UserDocumentId=self.player,Amount=20,Purpose='group_access',GroupId='group-'+self.game)
        def buy():
            try:return self.buy()
            except checkout_tests.CheckoutError as exc:return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            spend=pool.submit(self.call,self.wallet.WalletService.spend_incash,payload)
            offer=pool.submit(buy)
            result,status=spend.result();other=offer.result()
        self.assertEqual(self.balance(),10 if status==200 else 7)
        if status==200:
            self.assertEqual(other,'INSUFFICIENT_BALANCE')
            self.assertIn(self.player,self.service.ref('conversations','group-'+self.game).get().to_dict()['participants'])
        else:self.assertEqual(status,400)
        self.assertEqual(self.call(self.wallet.WalletService.spend_incash,{**payload,'Amount':-10})[1],400)

    def test_store_and_offer_share_debit_guard(self):
        item='item-'+self.game
        self.service.ref('store_items',item).set({'price':20,'title':'Item'})
        self.service.ref('humanUsers',self.player).update({'balance':30})
        def store():
            with self.app.test_client() as client:
                return client.post('/store/purchase',json={'user_id':self.player,'item_id':item}).status_code
        def buy():
            try:return self.buy()
            except checkout_tests.CheckoutError as exc:return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            old=pool.submit(store);new=pool.submit(buy);status=old.result();new.result()
        self.assertIn(status,(200,400));self.assertEqual(self.balance(),10 if status==200 else 7)
        self.assertEqual(self.service.ref('humanUsers',self.player).collection('inventory').document(item).get().exists,status==200)

    def test_group_access_and_offer_share_debit_guard(self):
        group='group-'+self.game
        self.service.ref('groups',group).set({'pass_price':20,'pass_duration':1})
        self.service.ref('humanUsers',self.player).update({'balance':30})
        def buy():
            try:return self.buy()
            except checkout_tests.CheckoutError as exc:return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            old=pool.submit(self.call,self.groups.GroupAccessService.join_group,dict(user_id=self.player,group_id=group,tier='pass'))
            new=pool.submit(buy);result,status=old.result();new.result()
        self.assertIn(status,(200,400));self.assertEqual(self.balance(),10 if status==200 else 7)
        self.assertEqual(self.service.ref('humanUsers',self.player).collection('groups').document(group).get().exists,status==200)

    def test_tip_and_offer_preserve_total_funds(self):
        recipient='recipient-'+self.game
        self.service.ref('humanUsers',recipient).set({'balance':0,'username':recipient})
        self.service.ref('humanUsers',self.player).update({'balance':30})
        def buy():
            try:return self.buy()
            except checkout_tests.CheckoutError as exc:return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            tip=pool.submit(self.call,self.tips.TippingService.send_tip,dict(sender_id=self.player,recipient_handle=recipient,amount=20))
            offer=pool.submit(buy);_,status=tip.result();offer.result()
        self.assertIn(status,(200,400))
        self.assertEqual(self.balance(),10 if status==200 else 7)
        self.assertEqual(self.service.ref('humanUsers',recipient).get().to_dict()['balance'],20 if status==200 else 0)

    def test_self_tip_does_not_mint_or_destroy_money(self):
        self.service.ref('humanUsers',self.player).update({'username':self.player})
        result,status=self.call(self.tips.TippingService.send_tip,dict(sender_id=self.player,recipient_handle=self.player,amount=20))
        self.assertEqual(status,200);self.assertEqual(result['new_balance'],200);self.assertEqual(self.balance(),200)

    def test_voice_debit_and_offer_cannot_overspend(self):
        self.service.ref('humanUsers',self.player).update({'balance':30})
        from services.monetization.balance_updates import BalanceError
        def attempt(fn):
            try:return fn()
            except (BalanceError,checkout_tests.CheckoutError) as exc:return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(attempt,[lambda:debit_balance(self.db,self.player,20),self.buy]))
        self.assertEqual(results.count('INSUFFICIENT_BALANCE'),1)
        self.assertIn(self.balance(),(7,10))

    def test_subscription_reward_duplicate_and_offer(self):
        renewal=(datetime.now()-timedelta(days=1)).isoformat()
        self.service.ref('humanUsers',self.player).update({'subscription':{'isSubscribed':True,'nextRenewalDate':renewal}})
        now=datetime.now()
        with ThreadPoolExecutor(max_workers=3) as pool:
            first=pool.submit(credit_subscription_reward,self.db,self.player,renewal,now)
            second=pool.submit(credit_subscription_reward,self.db,self.player,renewal,now)
            purchase=pool.submit(self.buy)
            self.assertEqual(int(first.result())+int(second.result()),1);purchase.result()
        self.assertEqual(self.balance(),2677)
        self.assertEqual(len(self.service.ref('humanUsers',self.player).get().to_dict()['subscriptionRewards']),1)

    def test_signup_cannot_reset_existing_wallet(self):
        self.buy()
        self.assertFalse(create_wallet_profile(self.db,self.player,{'balance':200}))
        self.assertEqual(self.balance(),177)

    def test_missing_balance_initialization_and_topup(self):
        self.service.ref('humanUsers',self.player).set({})
        payload=dict(UserDocumentId=self.player,PackageId='InCashBasic2025',Platform='ios',ReceiptData='test-only')
        with ThreadPoolExecutor(max_workers=2) as pool:
            init=pool.submit(self.call,self.wallet.WalletService.get_balance,self.player)
            topup=pool.submit(self.call,self.wallet.WalletService.purchase_incash,payload)
            self.assertEqual(init.result()[1],200);self.assertEqual(topup.result()[1],200)
        self.assertEqual(self.balance(),300)

if __name__=='__main__':unittest.main()
