"""Trusted-host API. Never inject Firebase account tokens into uploaded games."""
import logging
from flask import Blueprint, jsonify, request
from routes.api.game_offers import ID, validate_offers
from services.minigames.offer_checkout import CheckoutError, key

logger = logging.getLogger(__name__)


def create_offer_checkout_blueprint(service, verify_token, enabled):
    bp = Blueprint('offer_checkout_v1', __name__)

    def body(required, limit=4096):
        if request.content_length is None or request.content_length > limit:
            raise CheckoutError('INVALID_BODY_SIZE', 413)
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or set(data) != set(required):
            raise CheckoutError('INVALID_REQUEST', 400)
        return data

    def identifier(value):
        if not isinstance(value, str) or not ID.fullmatch(value):
            raise CheckoutError('INVALID_IDENTIFIER', 400)
        return value

    def uid():
        token = request.headers.get('Authorization', '')
        if not token.startswith('Bearer ') or not token[7:].strip():
            raise CheckoutError('UNAUTHENTICATED', 401)
        try:
            claims = verify_token(token[7:].strip())
            value = claims.get('uid')
            if not isinstance(value, str) or not value or '/' in value:
                raise ValueError('Missing UID')
            return value
        except Exception:
            raise CheckoutError('UNAUTHENTICATED', 401)

    @bp.before_request
    def guard():
        if not enabled():
            return jsonify(success=False, code='CHECKOUT_DISABLED'), 404

    @bp.after_request
    def private(response):
        response.headers['Cache-Control'] = 'no-store'
        return response

    @bp.errorhandler(CheckoutError)
    def expected(error):
        return jsonify(success=False, code=error.code), error.status

    @bp.errorhandler(Exception)
    def unexpected(error):
        # Avoid logging auth headers, payloads or exception text containing data.
        logger.error('Offer checkout failed (%s)', type(error).__name__)
        return jsonify(success=False, code='CHECKOUT_UNAVAILABLE'), 503

    prefix = '/api/game-sdk/v2/games/<game_id>'

    @bp.get(prefix + '/catalog')
    def catalog(game_id):
        return jsonify(success=True, data=service.catalog(identifier(game_id)))

    @bp.post(prefix + '/catalog/publish')
    def publish(game_id):
        owner = uid()
        data = body(['offers'], 65536)
        try:
            offers = validate_offers(data)
        except ValueError:
            raise CheckoutError('INVALID_OFFERS', 400)
        return jsonify(success=True, data=service.publish(identifier(game_id), owner, key(offers)))

    @bp.post(prefix + '/purchases')
    def purchase(game_id):
        player = uid()
        data = body(['offerId', 'catalogVersion', 'requestId'])
        result = service.purchase(identifier(game_id), player,
                                  identifier(data['offerId']), identifier(data['catalogVersion']),
                                  identifier(data['requestId']))
        return jsonify(success=True, data=result)

    @bp.get(prefix + '/purchases/<request_id>')
    def receipt(game_id, request_id):
        player = uid()
        return jsonify(success=True, data=service.receipt(identifier(game_id), player, identifier(request_id)))

    @bp.get(prefix + '/inventory/<offer_id>')
    def inventory(game_id, offer_id):
        player = uid()
        return jsonify(success=True, data=service.inventory(identifier(game_id), player, identifier(offer_id)))

    return bp
