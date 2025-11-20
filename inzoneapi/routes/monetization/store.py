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

    item_ref = db.collection('store_items').document(item_id)
    item = item_ref.get().to_dict()
    user_ref = db.collection('humanUsers').document(user_id)
    user_data = user_ref.get().to_dict()

    if not item:
        return jsonify({'error': 'Item not found'}), 404
    if user_data.get('balance', 200) < item.get('price', 0):
        return jsonify({'error': 'Insufficient funds'}), 400

    # Deduct funds and record purchase in the humanUsers document
    user_ref.update({
        'balance': firestore.Increment(-item.get('price', 0)),
        'purchases': firestore.ArrayUnion([item_id])
    })
    # Save purchased item to the user's inventory (subcollection)
    db.collection('humanUsers').document(user_id).collection('inventory').document(item_id).set(item)
    return jsonify({'message': 'Purchase successful'})

@store_bp.route('/store/inventory', methods=['GET'])
def get_inventory():
    user_id = request.args.get('user_id')
    inventory = [doc.to_dict() for doc in db.collection('humanUsers').document(user_id).collection('inventory').stream()]
    return jsonify({'inventory': inventory})
