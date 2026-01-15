# utils/helpers.py
from dependencies import db
import random
import datetime
from firebase_admin import firestore

def get_user_name(user_id):
    """
    Retrieves the username for a given user_id from Firestore.
    Searches in humanUsers first, then aiUsers.
    """
    try:
        # Try humanUsers collection first
        user_ref = db.collection('humanUsers').document(user_id)
        user_doc = user_ref.get()

        if user_doc.exists:
            user_data = user_doc.to_dict()
            username = user_data.get('username') or user_data.get('name')
            if username:
                return username
        
        # Try aiUsers collection
        user_ref = db.collection('aiUsers').document(user_id)
        user_doc = user_ref.get()
        
        if user_doc.exists:
            user_data = user_doc.to_dict()
            username = user_data.get('username') or user_data.get('name')
            if username:
                return username
        
        # If no username found in either collection, return the user_id as fallback
        print(f"Warning: Could not find username for user_id {user_id}")
        return user_id
    except Exception as e:
        print(f"Error retrieving user name for {user_id}: {e}")
        return user_id

def _get_random_character_name():
    """Get a random AI character name for offers"""
    try:
        characters = db.collection('aiCharacters').limit(10).get()
        if characters:
            char = random.choice(characters)
            return char.to_dict().get('name', 'InZone')
        return 'InZone'
    except:
        return 'InZone'

def _get_character_name(character_id):
    """Get character name by ID"""
    try:
        if character_id == 'system' or character_id == 'default':
            return 'InZone'
        
        char_doc = db.collection('aiCharacters').document(character_id).get()
        if char_doc.exists:
            return char_doc.to_dict().get('name', 'AI Friend')
        return 'AI Friend'
    except:
        return 'AI Friend'

def _log_rare_offer(user_id, offer_type, coin_amount):
    """Log rare offer to track limits"""
    try:
        today = datetime.utcnow().strftime('%Y-%m-%d')
        log_data = {
            'userId': user_id,
            'type': offer_type,
            'status': 'sent',
            'coinsAwarded': 0,  # Will be updated when completed
            'coinAmount': coin_amount,
            'timestamp': firestore.SERVER_TIMESTAMP,
            'date': today
        }
        
        db.collection('rareOffersLog').add(log_data)
        
    except Exception as e:
        logger.error(f"Error logging rare offer: {e}")

def _get_rare_offer_eligible_users():
    """Get users eligible for weekly rare offer selection"""
    try:
        # Get users with low coin balance or no recent coin earning
        week_ago = datetime.utcnow() - timedelta(days=7)
        
        # Query users with rare offers enabled
        users_query = (db.collection('humanUsers')
                      .where('notificationPrefs.categories.rareOffers.enabled', '==', True)
                      .limit(500))
        
        users_docs = users_query.get()
        eligible_users = []
        
        for user_doc in users_docs:
            user_data = user_doc.to_dict()
            user_id = user_doc.id
            
            # Check weekly limit
            recent_offers = (db.collection('rareOffersLog')
                           .where('userId', '==', user_id)
                           .where('timestamp', '>', week_ago)
                           .get())
            
            max_per_week = user_data.get('notificationPrefs', {}).get('categories', {}).get('rareOffers', {}).get('maxPerWeek', 2)
            
            if len(recent_offers) < max_per_week:
                # Check if user has low coins or no recent earning
                coin_balance = user_data.get('coinBalance', 0)
                if coin_balance < 100:  # Low balance threshold
                    eligible_users.append(user_id)
        
        return eligible_users[:50]  # Limit to 50 users per week
        
    except Exception as e:
        logger.error(f"Error getting rare offer eligible users: {e}")
        return []
