"""Additive, owner-only draft catalog. Existing coin checkout is untouched."""
import re
from flask import Blueprint, jsonify, request

ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


def validate_offers(body):
    if not isinstance(body, dict) or set(body) != {"offers"}:
        raise ValueError('Expected only an offers array')
    offers = body['offers']
    if not isinstance(offers, list) or len(offers) > 100:
        raise ValueError('offers must be an array of at most 100 entries')
    seen = set()
    clean = []
    for offer in offers:
        if not isinstance(offer, dict) or set(offer) != {'id', 'title', 'kind', 'coins', 'quantity'}:
            raise ValueError('Each offer requires id, title, kind, coins, quantity only')
        offer_id = offer['id']
        if not isinstance(offer_id, str) or not ID.fullmatch(offer_id) or offer_id in seen:
            raise ValueError('Offer IDs must be unique safe identifiers')
        seen.add(offer_id)
        if not isinstance(offer['title'], str) or not 1 <= len(offer['title'].strip()) <= 120:
            raise ValueError('title must contain 1–120 characters')
        if offer['kind'] not in ('durable', 'consumable'):
            raise ValueError('kind must be durable or consumable')
        if type(offer['coins']) is not int or not 1 <= offer['coins'] <= 1_000_000:
            raise ValueError('coins must be an integer from 1 to 1000000')
        if type(offer['quantity']) is not int or not 1 <= offer['quantity'] <= 10000:
            raise ValueError('quantity must be an integer from 1 to 10000')
        if offer['kind'] == 'durable' and offer['quantity'] != 1:
            raise ValueError('durable quantity must be 1')
        clean.append({**offer, 'title': offer['title'].strip()})
    return clean


def create_game_offers_blueprint(db, verify_token, enabled):
    bp = Blueprint('game_offer_catalog', __name__)

    @bp.route('/api/game-sdk/games/<game_id>/offers', methods=['GET', 'PUT'])
    def catalog(game_id):
        def error(code, status):
            return jsonify(success=False, code=code), status
        if not enabled():
            return error('CATALOG_DISABLED', 404)
        if not ID.fullmatch(game_id):
            return error('INVALID_GAME_ID', 400)
        token = request.headers.get('Authorization', '')
        if not token.startswith('Bearer ') or not token[7:].strip():
            return error('UNAUTHENTICATED', 401)
        try:
            identity = verify_token(token[7:].strip())
        except Exception:
            return error('UNAUTHENTICATED', 401)
        uid = identity.get('uid')
        if not uid:
            return error('UNAUTHENTICATED', 401)
        try:
            game = db.collection('html_games').document(game_id).get()
            if not game.exists:
                return error('GAME_NOT_FOUND', 404)
            # Only the verified web upload owner field is accepted. A legacy
            # developer_id or gameKey does not establish a Firebase UID binding.
            if (game.to_dict() or {}).get('uploaderId') != uid:
                return error('NOT_GAME_OWNER', 403)
            ref = db.collection('game_offer_drafts').document(game_id)
            if request.method == 'PUT':
                if request.content_length is None or request.content_length > 65536:
                    return error('INVALID_BODY_SIZE', 413)
                try:
                    offers = validate_offers(request.get_json(silent=True))
                except ValueError as exc:
                    return jsonify(success=False, code='INVALID_OFFERS', error=str(exc)), 400
                # One atomic document replacement; draft edits are last-write-wins.
                ref.set({'gameId': game_id, 'ownerUid': uid, 'offers': offers})
            else:
                snapshot = ref.get()
                offers = (snapshot.to_dict() or {}).get('offers', []) if snapshot.exists else []
            return jsonify(success=True, gameId=game_id, offers=offers,
                           status='draft', purchaseSupported=False)
        except Exception:
            return error('CATALOG_UNAVAILABLE', 503)
    return bp
