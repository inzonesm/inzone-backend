# services/monetization/subscription_service.py
from dependencies import db
from typing import Dict, Any
import logging
from flask import jsonify
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)

class SubscriptionService:
    """Service for subscription management and verification"""

    @staticmethod
    def verify_ios_subscription(receipt_data: str, user_id: str) -> Dict[str, Any]:
        """Verify iOS subscription with Apple"""
        try:
            # Note: This requires functions_client which should be injected or configured
            # For now, keeping the same logic structure as app.py
            # You may need to import and configure functions_client properly
            from google.cloud import functions_v1

            functions_client = functions_v1.CloudFunctionsServiceClient()
            function_path = functions_client.function_path('inzone-project', 'us-central1', 'verifyIosSubscription')

            request_data = {
                'receiptData': receipt_data,
                'userId': user_id
            }

            response = functions_client.call_function(
                name=function_path,
                data=json.dumps(request_data).encode()
            )

            result = json.loads(response.result)

            if result.get('success'):
                subscription_info = result.get('data', {})
                return {
                    'is_valid': True,
                    'expiry_date': subscription_info.get('expiryDate'),
                    'product_id': subscription_info.get('productId'),
                    'is_trial_period': subscription_info.get('isTrialPeriod', False),
                    'original_transaction_id': subscription_info.get('originalTransactionId')
                }
            else:
                logger.error(f"iOS subscription verification failed: {result.get('error')}")
                return {'is_valid': False}
        except Exception as e:
            logger.error(f"Error verifying iOS subscription: {e}")
            return {'is_valid': False}

    @staticmethod
    def verify_android_subscription(subscription_id: str, purchase_token: str) -> Dict[str, Any]:
        """Verify Android subscription using Google Play Developer API"""
        try:
            # Note: This requires get_android_publisher_api and PACKAGE_NAME
            # These should be configured properly in your environment
            from googleapiclient.discovery import build

            # You'll need to implement get_android_publisher_api
            # For now, keeping the structure
            android_publisher = SubscriptionService._get_android_publisher_api()
            if not android_publisher:
                return {'is_valid': False}

            PACKAGE_NAME = 'com.inzone.app'  # Configure this properly

            # Call the API to verify the subscription
            purchases_service = android_publisher.purchases().subscriptions()
            result = purchases_service.get(
                packageName=PACKAGE_NAME,
                subscriptionId=subscription_id,
                token=purchase_token
            ).execute()

            # Check if the subscription is active
            if result.get('paymentState') == 1:  # 1 means payment received
                expiry_time_millis = int(result.get('expiryTimeMillis', 0))
                expiry_date = datetime.fromtimestamp(expiry_time_millis / 1000).isoformat()

                return {
                    'is_valid': True,
                    'expiry_date': expiry_date,
                    'auto_renewing': result.get('autoRenewing', False),
                    'purchase_token': purchase_token,
                    'order_id': result.get('orderId')
                }
            else:
                return {'is_valid': False}
        except Exception as e:
            logger.error(f"Error verifying Android subscription: {e}")
            return {'is_valid': False}

    @staticmethod
    def _get_android_publisher_api():
        """Helper to get Android Publisher API client"""
        # TODO: Implement this based on your credentials setup
        # This is a placeholder
        return None

    @staticmethod
    def update_subscription(data: Dict[str, Any]) -> Dict[str, Any]:
        """Update subscription status"""
        try:
            user_id = data.get('UserDocumentId')
            platform = data.get('Platform', '').lower()  # 'ios' or 'android'
            subscription_id = data.get('SubscriptionId')
            receipt_data = data.get('ReceiptData')  # For iOS: receipt data, For Android: purchase token

            if not user_id or not platform or not subscription_id or not receipt_data:
                return jsonify({
                    'success': False,
                    'error': 'Missing required fields'
                }), 400

            # Get user document
            user_ref = db.collection('humanUsers').document(user_id)
            user_doc = user_ref.get()

            if not user_doc.exists:
                return jsonify({
                    'success': False,
                    'error': 'User not found'
                }), 404

            # Verify subscription based on platform
            if platform == 'ios':
                verification_result = SubscriptionService.verify_ios_subscription(receipt_data, user_id)
            elif platform == 'android':
                verification_result = SubscriptionService.verify_android_subscription(subscription_id, receipt_data)
            else:
                return jsonify({
                    'success': False,
                    'error': 'Invalid platform'
                }), 400

            # Update subscription status based on verification result
            if verification_result.get('is_valid'):
                expiry_date = verification_result.get('expiry_date')
                expiry_datetime = datetime.fromisoformat(expiry_date) if expiry_date else (datetime.now() + timedelta(days=30))

                subscription_data = {
                    'isSubscribed': True,
                    'subscriptionType': 'gold',
                    'subscriptionId': subscription_id,
                    'platform': platform,
                    'startDate': datetime.now().isoformat(),
                    'expiryDate': expiry_date,
                    'nextRenewalDate': expiry_date,
                    'verificationDetails': verification_result
                }

                user_ref.update({
                    'subscription': subscription_data
                })

                return jsonify({
                    'success': True,
                    'data': {
                        'isSubscribed': True,
                        'subscriptionType': 'gold',
                        'expiryDate': expiry_date
                    }
                }), 200
            else:
                # Subscription is not valid
                subscription_data = {
                    'isSubscribed': False,
                    'cancelDate': datetime.now().isoformat(),
                    'verificationDetails': verification_result
                }

                user_ref.update({
                    'subscription': subscription_data
                })

                return jsonify({
                    'success': False,
                    'error': 'Subscription verification failed',
                    'data': {
                        'isSubscribed': False
                    }
                }), 200

        except Exception as e:
            logger.error(f"Error updating subscription: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @staticmethod
    def get_subscription_status(user_id: str, verify: bool = False) -> Dict[str, Any]:
        """Check subscription status"""
        try:
            if not user_id:
                return jsonify({
                    'success': False,
                    'error': 'Missing user ID'
                }), 400

            # Get user document
            user_ref = db.collection('humanUsers').document(user_id)
            user_doc = user_ref.get()

            if not user_doc.exists:
                return jsonify({
                    'success': False,
                    'error': 'User not found'
                }), 404

            # Get subscription data
            user_data = user_doc.to_dict()
            subscription_data = user_data.get('subscription', {})
            is_subscribed = subscription_data.get('isSubscribed', False)

            # If verify flag is true, verify the subscription with the platform
            if verify and is_subscribed:
                platform = subscription_data.get('platform')
                subscription_id = subscription_data.get('subscriptionId')

                # For iOS, we need the original receipt data which should be stored
                if platform == 'ios':
                    receipt_data = subscription_data.get('verificationDetails', {}).get('original_transaction_id')
                    if receipt_data:
                        verification_result = SubscriptionService.verify_ios_subscription(receipt_data, user_id)
                        is_subscribed = verification_result.get('is_valid', False)

                # For Android, we need the purchase token
                elif platform == 'android':
                    purchase_token = subscription_data.get('verificationDetails', {}).get('purchase_token')
                    if purchase_token and subscription_id:
                        verification_result = SubscriptionService.verify_android_subscription(subscription_id, purchase_token)
                        is_subscribed = verification_result.get('is_valid', False)

                # Update subscription status if verification failed
                if not is_subscribed:
                    subscription_data['isSubscribed'] = False
                    subscription_data['cancelDate'] = datetime.now().isoformat()
                    user_ref.update({
                        'subscription': subscription_data
                    })

            return jsonify({
                'success': True,
                'data': {
                    'isSubscribed': is_subscribed,
                    'subscriptionData': subscription_data
                }
            }), 200

        except Exception as e:
            logger.error(f"Error getting subscription status: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @staticmethod
    def process_subscription_rewards() -> Dict[str, Any]:
        """Process monthly subscription rewards (called by scheduled job/cron)"""
        try:
            # Get all subscribed users
            subscribed_users = db.collection('humanUsers').where('subscription.isSubscribed', '==', True).stream()

            processed_count = 0
            verified_count = 0
            failed_count = 0

            for user_doc in subscribed_users:
                user_id = user_doc.id
                user_data = user_doc.to_dict()

                # Check if subscription is still active
                subscription_data = user_data.get('subscription', {})
                next_renewal_date = subscription_data.get('nextRenewalDate')
                platform = subscription_data.get('platform')
                subscription_id = subscription_data.get('subscriptionId')

                # Verify subscription with the platform
                is_valid = False

                if platform == 'ios':
                    # For iOS, verify with Apple through Firebase Functions
                    receipt_data = subscription_data.get('verificationDetails', {}).get('original_transaction_id')
                    if receipt_data:
                        verification_result = SubscriptionService.verify_ios_subscription(receipt_data, user_id)
                        is_valid = verification_result.get('is_valid', False)
                        verified_count += 1

                elif platform == 'android':
                    # For Android, verify with Google Play Developer API
                    purchase_token = subscription_data.get('verificationDetails', {}).get('purchase_token')
                    if purchase_token and subscription_id:
                        verification_result = SubscriptionService.verify_android_subscription(subscription_id, purchase_token)
                        is_valid = verification_result.get('is_valid', False)
                        verified_count += 1

                # If subscription is not valid, update status and skip reward
                if not is_valid:
                    user_ref = db.collection('humanUsers').document(user_id)
                    user_ref.update({
                        'subscription.isSubscribed': False,
                        'subscription.cancelDate': datetime.now().isoformat()
                    })
                    failed_count += 1
                    continue

                # If subscription is valid and renewal date has passed, add the monthly reward
                if next_renewal_date and is_valid:
                    next_renewal = datetime.fromisoformat(next_renewal_date)

                    # If the renewal date has passed, add the monthly reward
                    if datetime.now() >= next_renewal:
                        # Get current balance
                        current_balance = user_data.get('balance', 200)

                        # Add 2500 InCash
                        new_balance = current_balance + 2500

                        # Update next renewal date (30 days from now)
                        new_next_renewal = (datetime.now() + timedelta(days=30)).isoformat()

                        # Record subscription reward
                        reward_history = user_data.get('subscriptionRewards', [])
                        reward_history.append({
                            'amount': 2500,
                            'date': datetime.now().isoformat(),
                            'type': 'monthly_subscription'
                        })

                        # Update user document
                        user_ref = db.collection('humanUsers').document(user_id)
                        user_ref.update({
                            'balance': new_balance,
                            'subscriptionRewards': reward_history,
                            'subscription.nextRenewalDate': new_next_renewal
                        })

                        processed_count += 1

            return jsonify({
                'success': True,
                'data': {
                    'processedCount': processed_count,
                    'verifiedCount': verified_count,
                    'failedCount': failed_count
                }
            }), 200

        except Exception as e:
            logger.error(f"Error processing subscription rewards: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
