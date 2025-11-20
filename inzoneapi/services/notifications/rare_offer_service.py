from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
import logging
import random
from typing import Dict, List
from services.notifications.notification_service import notification_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RareOfferService:
    def __init__(self):
        # Initialize Firebase if not already done
        if not firebase_admin._apps:
            cred = credentials.Certificate('key.json')
            firebase_admin.initialize_app(cred)
        
        self.db = firestore.client()
        
        # Offer configurations
        self.offer_types = {
            'watch_video': {
                'coin_amount': 50,
                'title': '🎬 Watch & Earn',
                'description': 'Watch a short video for +{coin_amount} InCash',
                'cooldown_hours': 72,  # 3 days
            },
            'refer_friend': {
                'coin_amount': 200,
                'title': '👥 Refer & Earn',
                'description': 'Invite 1 friend → +{coin_amount} InCash',
                'cooldown_hours': 168,  # 7 days
            },
            'double_coins': {
                'coin_amount': 100,
                'title': '💎 Double Bonus',
                'description': 'Limited-time double coins for next action!',
                'cooldown_hours': 72,  # 3 days
            }
        }
        
        # Minimum balance thresholds
        self.low_balance_threshold = 100
        self.minimum_store_item_cost = 50
    
    def check_rare_offer_eligibility(self):
        """Check and send rare coin offers to eligible users (run weekly)"""
        try:
            logger.info("Starting rare offer eligibility check...")
            
            # Get all users
            users_query = self.db.collection('humanUsers').limit(500)
            users = users_query.get()
            
            offers_sent = 0
            
            for user_doc in users:
                user_id = user_doc.id
                user_data = user_doc.to_dict()
                
                # Check if user has rare offers enabled
                if not self._is_rare_offers_enabled(user_id):
                    continue
                
                # Check weekly offer limit
                if self._has_reached_weekly_offer_limit(user_id):
                    continue
                
                # Check eligibility criteria
                offer_type = self._check_eligibility_criteria(user_id, user_data)
                if not offer_type:
                    continue
                
                # Check cooldown for this offer type
                if self._is_offer_on_cooldown(user_id, offer_type):
                    continue
                
                # Send the offer
                if self._send_rare_offer(user_id, offer_type):
                    offers_sent += 1
            
            logger.info(f"Sent {offers_sent} rare coin offers")
            
        except Exception as e:
            logger.error(f"Error checking rare offer eligibility: {str(e)}")
    
    def _is_rare_offers_enabled(self, user_id: str) -> bool:
        """Check if user has rare offers enabled"""
        try:
            user_doc = self.db.collection('users').document(user_id).get()
            if not user_doc.exists:
                return True  # Default to enabled
            
            user_data = user_doc.to_dict()
            prefs = user_data.get('notificationPrefs', {})
            categories = prefs.get('categories', {})
            rare_offers = categories.get('rareOffers', {})
            
            return rare_offers.get('enabled', True)
            
        except Exception as e:
            logger.error(f"Error checking rare offers preference: {str(e)}")
            return True
    
    def _has_reached_weekly_offer_limit(self, user_id: str) -> bool:
        """Check if user has reached weekly offer limit"""
        try:
            # Get current week start (Monday)
            now = datetime.utcnow()
            week_start = now - timedelta(days=now.weekday())
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Query offers sent this week
            offers_query = (self.db.collection('rareOffersLog')
                           .document(user_id)
                           .collection('offers')
                           .where('sentAt', '>=', week_start)
                           .where('status', 'in', ['sent', 'opened', 'completed']))
            
            offers = offers_query.get()
            
            # Get user's max per week setting
            user_doc = self.db.collection('users').document(user_id).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                prefs = user_data.get('notificationPrefs', {})
                categories = prefs.get('categories', {})
                rare_offers = categories.get('rareOffers', {})
                max_per_week = rare_offers.get('maxPerWeek', 2)
            else:
                max_per_week = 2
            
            return len(offers) >= max_per_week
            
        except Exception as e:
            logger.error(f"Error checking weekly offer limit: {str(e)}")
            return True  # Err on the safe side
    
    def _check_eligibility_criteria(self, user_id: str, user_data: Dict) -> str:
        """Check if user meets criteria for rare offers and return offer type"""
        try:
            balance = user_data.get('balance', 0)
            last_offer_check = user_data.get('lastOfferCheck')
            
            # Check for low balance
            if balance < self.low_balance_threshold:
                return 'watch_video'
            
            # Check for failed purchase scenario
            failed_purchase = user_data.get('lastFailedPurchase')
            if failed_purchase:
                failed_time = failed_purchase.get('timestamp')
                if failed_time and self._is_recent(failed_time, hours=24):
                    return 'watch_video'
            
            # Check for inactivity (no coin earning in 7+ days)
            if last_offer_check:
                days_since_check = (datetime.utcnow() - last_offer_check.to_datetime()).days
                if days_since_check >= 7:
                    return 'refer_friend'
            
            # Check if balance is too high (suppress offers)
            if balance >= (self.minimum_store_item_cost * 2):  # 200% of cheapest item
                return None
            
            # Random chance for double coins offer (5% chance for active users)
            if random.random() < 0.05 and balance < 300:
                return 'double_coins'
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking eligibility criteria: {str(e)}")
            return None
    
    def _is_recent(self, timestamp, hours: int) -> bool:
        """Check if timestamp is within the last N hours"""
        try:
            if hasattr(timestamp, 'to_datetime'):
                timestamp = timestamp.to_datetime()
            
            time_diff = datetime.utcnow() - timestamp
            return time_diff.total_seconds() < (hours * 3600)
            
        except Exception as e:
            logger.error(f"Error checking if timestamp is recent: {str(e)}")
            return False
    
    def _is_offer_on_cooldown(self, user_id: str, offer_type: str) -> bool:
        """Check if offer type is on cooldown for user"""
        try:
            cooldown_hours = self.offer_types[offer_type]['cooldown_hours']
            cooldown_time = datetime.utcnow() - timedelta(hours=cooldown_hours)
            
            # Query recent offers of this type
            offers_query = (self.db.collection('rareOffersLog')
                           .document(user_id)
                           .collection('offers')
                           .where('type', '==', offer_type)
                           .where('sentAt', '>=', cooldown_time)
                           .limit(1))
            
            offers = offers_query.get()
            
            return len(offers) > 0
            
        except Exception as e:
            logger.error(f"Error checking offer cooldown: {str(e)}")
            return True  # Err on the safe side
    
    def _send_rare_offer(self, user_id: str, offer_type: str) -> bool:
        """Send rare coin offer to user"""
        try:
            offer_config = self.offer_types[offer_type]
            
            # Get a random AI character for personalization
            character_name = self._get_random_character_name()
            
            # Create offer text
            offer_text = offer_config['description'].format(
                coin_amount=offer_config['coin_amount']
            )
            
            # Create notification data
            notification_data = {
                'type': 'rare_offer',
                'userId': user_id,
                'characterName': character_name,
                'offerType': offer_type,
                'offerText': offer_text,
                'coinAmount': offer_config['coin_amount'],
                'timestamp': datetime.utcnow().isoformat(),
            }
            
            # Send notification
            notification_id = notification_service.create_notification_event(notification_data)
            
            # Log the offer
            self._log_rare_offer(user_id, offer_type, notification_id, offer_config['coin_amount'])
            
            logger.info(f"Rare offer sent to user {user_id}: {offer_type}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending rare offer: {str(e)}")
            return False
    
    def _get_random_character_name(self) -> str:
        """Get a random AI character name for offer personalization"""
        try:
            # Query random AI character
            characters_query = self.db.collection('aiCharacters').limit(10)
            characters = characters_query.get()
            
            if characters:
                random_char = random.choice(characters)
                char_data = random_char.to_dict()
                return char_data.get('name', 'Your AI friend')
            
            return 'Your AI friend'
            
        except Exception as e:
            logger.error(f"Error getting random character: {str(e)}")
            return 'Your AI friend'
    
    def _log_rare_offer(self, user_id: str, offer_type: str, notification_id: str, coin_amount: int):
        """Log rare offer to user's offer history"""
        try:
            offer_data = {
                'type': offer_type,
                'status': 'sent',
                'sentAt': firestore.SERVER_TIMESTAMP,
                'notificationId': notification_id,
                'coinAmount': coin_amount,
                'coinsAwarded': 0,  # Will be updated when completed
            }
            
            # Add to user's offer log
            self.db.collection('rareOffersLog').document(user_id).collection('offers').add(offer_data)
            
            # Update user's last offer check timestamp
            self.db.collection('humanUsers').document(user_id).update({
                'lastOfferCheck': firestore.SERVER_TIMESTAMP
            })
            
        except Exception as e:
            logger.error(f"Error logging rare offer: {str(e)}")
    
    def handle_failed_purchase(self, user_id: str, attempted_amount: int):
        """Handle failed purchase scenario - may trigger immediate offer"""
        try:
            # Log the failed purchase
            self.db.collection('humanUsers').document(user_id).update({
                'lastFailedPurchase': {
                    'amount': attempted_amount,
                    'timestamp': firestore.SERVER_TIMESTAMP,
                }
            })
            
            # Check if user should get immediate offer
            user_doc = self.db.collection('humanUsers').document(user_id).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                
                # Check eligibility and send offer if appropriate
                if self._is_rare_offers_enabled(user_id) and not self._has_reached_weekly_offer_limit(user_id):
                    if not self._is_offer_on_cooldown(user_id, 'watch_video'):
                        self._send_rare_offer(user_id, 'watch_video')
            
        except Exception as e:
            logger.error(f"Error handling failed purchase: {str(e)}")
    
    def mark_offer_completed(self, user_id: str, offer_id: str, coins_awarded: int):
        """Mark rare offer as completed and update coins"""
        try:
            # Update offer status
            offer_ref = (self.db.collection('rareOffersLog')
                        .document(user_id)
                        .collection('offers')
                        .document(offer_id))
            
            offer_ref.update({
                'status': 'completed',
                'completedAt': firestore.SERVER_TIMESTAMP,
                'coinsAwarded': coins_awarded,
            })
            
            # Award coins to user
            user_ref = self.db.collection('humanUsers').document(user_id)
            user_ref.update({
                'balance': firestore.Increment(coins_awarded)
            })
            
            logger.info(f"Rare offer completed: {offer_id}, awarded {coins_awarded} coins to {user_id}")
            
        except Exception as e:
            logger.error(f"Error marking offer completed: {str(e)}")

# Global rare offer service instance
rare_offer_service = RareOfferService()