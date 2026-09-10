from google.cloud import firestore
# routes/monetization/store.py
from flask import Blueprint, request, jsonify
from dependencies import db

store_bp = Blueprint('store', __name__)

@store_bp.route('/store/items', methods=['GET'])
def get_items():
    items = [doc.to_dict() for doc in db.collection('store_items').stream()]
    return jsonify({'items': items})

@store_bp.route('/store/purchase', methods=['POST'])
def purchase_item():
    data = request.json
    user_id = data['user_id']
    item_id = data['item_id']

    @firestore.transactional
    def apply(transaction):
        item_ref = db.collection('store_items').document(item_id)
        item = item_ref.get(transaction=transaction).to_dict()
        user_ref = db.collection('humanUsers').document(user_id)
        user_data = user_ref.get(transaction=transaction).to_dict()

        if not item:
            return jsonify({'error': 'Item not found'}), 404
        if not user_data:
            return jsonify({'error': 'User not found'}), 404
        if type(item.get('price', 0)) is not int or item.get('price', 0) < 0:
            return jsonify({'error': 'Invalid price'}), 400
        if user_data.get('balance', 200) < item.get('price', 0):
            return jsonify({'error': 'Insufficient funds'}), 400

        # Deduct funds and record purchase in the humanUsers document
        transaction.update(user_ref, {
            'balance': user_data.get('balance', 200) - item.get('price', 0),
            'purchases': firestore.ArrayUnion([item_id])
        })
        # Save purchased item to the user's inventory (subcollection)
        transaction.set(user_ref.collection('inventory').document(item_id), item)
        return jsonify({'message': 'Purchase successful'})
    return apply(db.transaction(max_attempts=10))

@store_bp.route('/store/inventory', methods=['GET'])
def get_inventory():
    user_id = request.args.get('user_id')
    inventory = [doc.to_dict() for doc in db.collection('humanUsers').document(user_id).collection('inventory').stream()]
    return jsonify({'inventory': inventory})
