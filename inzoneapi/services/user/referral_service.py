from datetime import datetime, timezone
from typing import Any, Dict, List
import logging

from flask import jsonify
from firebase_admin import firestore

from dependencies import db

logger = logging.getLogger(__name__)


class ReferralService:
	@staticmethod
	def track_accepted_referral(data: Dict[str, Any]):
		try:
			referrer_id = data.get('ReferrerId') or data.get('referrerId')
			installer_id = data.get('InstallerId') or data.get('installerId')

			if not referrer_id or not installer_id:
				return jsonify({
					'success': False,
					'error': 'ReferrerId and InstallerId are required',
				}), 400

			if referrer_id == installer_id:
				return jsonify({
					'success': False,
					'error': 'Referrer and referee cannot be the same user',
				}), 400

			profile = ReferralService._load_human_user_profile(installer_id)
			installer_display_name = (
				data.get('InstallerDisplayName')
				or data.get('installerDisplayName')
				or (data.get('AttributionData') or {}).get('installerDisplayName')
				or profile.get('name')
				or profile.get('Name')
				or profile.get('username')
				or profile.get('Username')
			)
			installer_photo_url = (
				data.get('InstallerPhotoURL')
				or data.get('installerPhotoURL')
				or (data.get('AttributionData') or {}).get('installerPhotoURL')
				or profile.get('profilePicture')
				or profile.get('ProfilePicture')
				or profile.get('profile_picture_url')
			)

			referral_doc_id = ReferralService._build_referral_doc_id(referrer_id, installer_id)

			existing_doc = db.collection('referrals').document(referral_doc_id).get()
			if existing_doc.exists:
				update_payload = {
					'referrerId': referrer_id,
					'installerId': installer_id,
					'referralKey': referral_doc_id,
				}
				if installer_display_name:
					update_payload['installerDisplayName'] = installer_display_name
				if installer_photo_url:
					update_payload['installerPhotoURL'] = installer_photo_url
				existing_doc.reference.set(update_payload, merge=True)
				return jsonify({
					'success': True,
					'message': 'Referral already tracked',
					'data': {'referral_id': existing_doc.id, 'already_exists': True},
				}), 200

			existing_legacy_doc = ReferralService._find_existing_referral_doc(referrer_id, installer_id)
			if existing_legacy_doc is not None:
				update_payload = {
					'referrerId': referrer_id,
					'installerId': installer_id,
					'referralKey': referral_doc_id,
				}
				if installer_display_name:
					update_payload['installerDisplayName'] = installer_display_name
				if installer_photo_url:
					update_payload['installerPhotoURL'] = installer_photo_url
				existing_legacy_doc.reference.set(update_payload, merge=True)

				db.collection('referrals').document(referral_doc_id).set(
					{**(existing_legacy_doc.to_dict() or {}), **update_payload},
					merge=True,
				)

				return jsonify({
					'success': True,
					'message': 'Referral already tracked',
					'data': {'referral_id': referral_doc_id, 'already_exists': True},
				}), 200

			referral_data = {
				'referralKey': referral_doc_id,
				'referrerId': referrer_id,
				'installerId': installer_id,
				'installerDisplayName': installer_display_name,
				'installerPhotoURL': installer_photo_url,
				'status': 'accepted',
				'source': data.get('Source') or data.get('source') or 'app_referral',
				'platform': data.get('Platform') or data.get('platform'),
				'attributionData': data.get('AttributionData') or data.get('attributionData') or {},
				'installTimestamp': firestore.SERVER_TIMESTAMP,
				'accepted_at': firestore.SERVER_TIMESTAMP,
			}

			ref_doc = db.collection('referrals').document(referral_doc_id)
			ref_doc.set(referral_data)

			installer_ref = db.collection('humanUsers').document(installer_id)
			installer_doc = installer_ref.get()
			if installer_doc.exists:
				installer_ref.set({'referred_by': referrer_id}, merge=True)

			db.collection('humanUsers').document(referrer_id).set({
				'referral_count': firestore.Increment(1),
				'totalReferrals': firestore.Increment(1),
			}, merge=True)

			return jsonify({
				'success': True,
				'message': 'Referral accepted tracked successfully',
				'data': {'referral_id': ref_doc.id, 'already_exists': False},
			}), 200
		except Exception as e:
			logger.error('Error tracking accepted referral: %s', e)
			return jsonify({'success': False, 'error': str(e)}), 500

	@staticmethod
	def get_accepted_referrals(user_document_id: str, limit: int = 50):
		try:
			if not user_document_id:
				return jsonify({'success': False, 'error': 'UserDocumentId is required'}), 400

			safe_limit = max(1, min(limit or 50, 200))

			refs: List[Dict[str, Any]] = []
			seen_ids = set()

			query_new = db.collection('referrals').where('referrerId', '==', user_document_id).stream()
			for doc in query_new:
				if doc.id in seen_ids:
					continue
				seen_ids.add(doc.id)
				refs.append({'_id': doc.id, **(doc.to_dict() or {})})

			query_legacy = db.collection('referrals').where('referrer_id', '==', user_document_id).stream()
			for doc in query_legacy:
				if doc.id in seen_ids:
					continue
				seen_ids.add(doc.id)
				refs.append({'_id': doc.id, **(doc.to_dict() or {})})

			# Fallback source: accepted installs tracked on user docs via referred_by
			referred_users = db.collection('humanUsers').where('referred_by', '==', user_document_id).stream()
			for user_doc in referred_users:
				user_data = user_doc.to_dict() or {}
				pseudo_id = f'humanUsers:{user_doc.id}'
				if pseudo_id in seen_ids:
					continue
				seen_ids.add(pseudo_id)
				refs.append({
					'_id': pseudo_id,
					'installerId': user_doc.id,
					'status': 'accepted',
					'installerDisplayName': user_data.get('name') or user_data.get('username'),
					'installerPhotoURL': user_data.get('profilePicture', ''),
					'installTimestamp': user_data.get('date_created'),
					'source': 'humanUsers.referred_by',
				})

			def _timestamp_value(item: Dict[str, Any]) -> float:
				raw = item.get('installTimestamp') or item.get('accepted_at') or item.get('date_created')
				if isinstance(raw, datetime):
					return raw.replace(tzinfo=timezone.utc).timestamp()
				return 0.0

			refs.sort(key=_timestamp_value, reverse=True)
			profile_cache: Dict[str, Dict[str, Any]] = {}

			items = []
			seen_installers = set()
			for item in refs:
				installer_id = ReferralService._resolve_installer_id(item)
				if installer_id:
					installer_key = str(installer_id)
					if installer_key in seen_installers:
						continue
					seen_installers.add(installer_key)
				display_name = (
					item.get('installerDisplayName')
					or item.get('installer_display_name')
					or item.get('name')
				)
				photo_url = (
					item.get('installerPhotoURL')
					or item.get('installer_photo_url')
					or item.get('photo_url')
					or ''
				)
				ts = item.get('installTimestamp') or item.get('accepted_at') or item.get('date_created')

				if installer_id and (not display_name or not str(display_name).strip()):
					profile = profile_cache.get(str(installer_id))
					if profile is None:
						profile = ReferralService._load_human_user_profile(str(installer_id))
						profile_cache[str(installer_id)] = profile

					display_name = (
						profile.get('name')
						or profile.get('Name')
						or profile.get('username')
						or profile.get('Username')
						or ReferralService._email_local_part(item.get('installerEmail') or profile.get('email'))
						or display_name
					)

					photo_url = (
						photo_url
						or profile.get('profilePicture')
						or profile.get('ProfilePicture')
						or profile.get('profile_picture_url')
						or ''
					)

					item_id = item.get('_id')
					if item_id and not str(item_id).startswith('humanUsers:'):
						update_payload = {}
						if display_name:
							update_payload['installerDisplayName'] = display_name
						if photo_url:
							update_payload['installerPhotoURL'] = photo_url
						if update_payload:
							db.collection('referrals').document(str(item_id)).set(update_payload, merge=True)

				items.append({
					'id': item.get('_id'),
					'referee_id': installer_id,
					'name': display_name or 'User',
					'photo_url': photo_url,
					'date': ReferralService._to_iso8601(ts),
					'status': item.get('status') or 'accepted',
					'source': item.get('source') or 'referrals',
				})

			items = items[:safe_limit]

			return jsonify({
				'success': True,
				'data': {
					'count': len(items),
					'accepted_referrals': items,
				},
			}), 200
		except Exception as e:
			logger.error('Error loading accepted referrals: %s', e)
			return jsonify({'success': False, 'error': str(e)}), 500

	@staticmethod
	def _to_iso8601(value: Any) -> str:
		if isinstance(value, datetime):
			return value.replace(tzinfo=timezone.utc).isoformat()
		return ''

	@staticmethod
	def _load_human_user_profile(user_id: str) -> Dict[str, Any]:
		if not user_id:
			return {}
		try:
			snapshot = db.collection('humanUsers').document(user_id).get()
			if snapshot.exists:
				return snapshot.to_dict() or {}
		except Exception as e:
			logger.warning('Unable to load humanUsers profile for %s: %s', user_id, e)
		return {}

	@staticmethod
	def _resolve_installer_id(item: Dict[str, Any]) -> str:
		installer_id = item.get('installerId')
		return str(installer_id) if installer_id else ''

	@staticmethod
	def _email_local_part(email: Any) -> str:
		if not email:
			return ''
		value = str(email).strip()
		if not value:
			return ''
		if '@' in value:
			local = value.split('@', 1)[0].strip()
			return local or value
		return value

	@staticmethod
	def _build_referral_doc_id(referrer_id: str, referee_id: str) -> str:
		return f'{referrer_id}_{referee_id}'

	@staticmethod
	def _find_existing_referral_doc(referrer_id: str, referee_id: str):
		for doc in db.collection('referrals').where('referrerId', '==', referrer_id).stream():
			payload = doc.to_dict() or {}
			installer_id = payload.get('installerId')
			if str(installer_id or '') == referee_id:
				return doc

		return None
