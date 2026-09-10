import copy
import unittest
from flask import Flask
from routes.api.game_offers import create_game_offers_blueprint

class Ref:
    def __init__(self, store, path): self.store, self.path = store, path
    def document(self, key): return Ref(self.store, self.path + '/' + key)
    def get(self): return self
    @property
    def exists(self): return self.path in self.store
    def to_dict(self): return copy.deepcopy(self.store.get(self.path))
    def set(self, value): self.store[self.path] = copy.deepcopy(value)
class DB:
    def __init__(self): self.store = {'html_games/demo': {'uploaderId': 'owner'}}
    def collection(self, name): return Ref(self.store, name)

class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.db = DB(); self.enabled = True
        app = Flask(__name__)
        def verify(token):
            if token == 'bad': raise ValueError('bad token')
            return {'uid': token}
        app.register_blueprint(create_game_offers_blueprint(self.db, verify, lambda: self.enabled))
        self.client = app.test_client(); self.url = '/api/game-sdk/games/demo/offers'
        self.headers = {'Authorization': 'Bearer owner'}
        self.offer = dict(id='full-game', title='Full game', kind='durable', coins=37, quantity=1)
    def put(self, offers, **kwargs):
        return self.client.put(self.url, json={'offers': offers}, headers=kwargs.get('headers', self.headers))
    def test_custom_prices_and_kinds_roundtrip_without_charging(self):
        before = copy.deepcopy(self.db.store)
        result = self.put([self.offer, dict(id='lives',title='Lives',kind='consumable',coins=23,quantity=5)])
        self.assertEqual(result.status_code, 200)
        self.assertFalse(result.json['purchaseSupported'])
        self.assertEqual(self.client.get(self.url,headers=self.headers).json['offers'],result.json['offers'])
        self.assertEqual(set(self.db.store)-set(before), {'game_offer_drafts/demo'})
        self.assertEqual(self.db.store['html_games/demo'],before['html_games/demo'])
    def test_auth_and_ownership(self):
        for headers, status in [({},401),({'Authorization':'Bearer bad'},401),({'Authorization':'Bearer other'},403)]:
            self.assertEqual(self.put([self.offer],headers=headers).status_code,status)
        self.assertNotIn('game_offer_drafts/demo',self.db.store)
    def test_legacy_developer_id_is_not_owner_identity(self):
        self.db.store['html_games/demo']={'developer_id':'owner'}
        self.assertEqual(self.put([self.offer]).status_code,403)
    def test_invalid_values_never_persist(self):
        for field, value in [('coins',True),('coins',-1),('coins',1.5),('kind','subscription'),('quantity',2),('id','../x')]:
            self.assertEqual(self.put([{**self.offer,field:value}]).status_code,400)
        self.assertEqual(self.put([self.offer,self.offer]).status_code,400)
        self.assertNotIn('game_offer_drafts/demo',self.db.store)
    def test_disabled(self):
        self.enabled=False
        self.assertEqual(self.put([self.offer]).status_code,404)
    def test_clear_and_missing_game(self):
        self.put([self.offer]); self.assertEqual(self.put([]).json['offers'],[])
        self.db.store.pop('html_games/demo')
        self.assertEqual(self.put([self.offer]).status_code,404)

if __name__ == '__main__': unittest.main()
