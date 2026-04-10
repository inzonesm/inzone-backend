from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
import logging
from urllib.parse import unquote, urlparse

from firebase_admin import auth, firestore
from flask import jsonify

from dependencies import db, storage

logger = logging.getLogger(__name__)


class AccountLifecycleService:
    """Queued, resumable account deletion workflow with a soft-delete waiting window."""

    DELETE_BATCH_SIZE = 300
    PURGE_WINDOW_DAYS = 30

    @staticmethod
    def _batch_update_documents(doc_refs: Iterable[Any], update_data: Dict[str, Any]) -> int:
        refs = AccountLifecycleService._dedupe_doc_refs(doc_refs)
        if not refs:
            return 0

        updated = 0
        for i in range(0, len(refs), AccountLifecycleService.DELETE_BATCH_SIZE):
            chunk = refs[i:i + AccountLifecycleService.DELETE_BATCH_SIZE]
            batch = db.batch()
            for ref in chunk:
                batch.update(ref, update_data)
            batch.commit()
            updated += len(chunk)
        return updated

    @staticmethod
    def _job_ref(uid: str):
        return db.collection('deletionRequests').document(uid)

    @staticmethod
    def _now_utc() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _to_aware_datetime(value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        return None

    @staticmethod
    def _write_log(job_ref: Any, level: str, message: str, step: Optional[str] = None) -> None:
        try:
            payload = {
                'level': level,
                'message': message,
                'timestamp': firestore.SERVER_TIMESTAMP,
            }
            if step:
                payload['step'] = step
            job_ref.collection('logs').add(payload)
        except Exception as log_ex:
            logger.warning('Failed to write deletion log: %s', log_ex)

    @staticmethod
    def _dedupe_doc_refs(doc_refs: Iterable[Any]) -> List[Any]:
        deduped: List[Any] = []
        seen_paths = set()
        for ref in doc_refs:
            path = getattr(ref, 'path', None)
            if not path:
                continue
            if path in seen_paths:
                continue
            seen_paths.add(path)
            deduped.append(ref)
        return deduped

    @staticmethod
    def _delete_documents(doc_refs: Iterable[Any]) -> int:
        refs = AccountLifecycleService._dedupe_doc_refs(doc_refs)
        if not refs:
            return 0

        deleted = 0
        for i in range(0, len(refs), AccountLifecycleService.DELETE_BATCH_SIZE):
            chunk = refs[i:i + AccountLifecycleService.DELETE_BATCH_SIZE]
            batch = db.batch()
            for ref in chunk:
                batch.delete(ref)
            batch.commit()
            deleted += len(chunk)
        return deleted

    @staticmethod
    def _query_doc_refs(collection_path: str, field: str, op: str, value: Any) -> List[Any]:
        query = db.collection(collection_path).where(field, op, value)
        return [doc.reference for doc in query.stream()]

    @staticmethod
    def _delete_query_docs(collection_path: str, field: str, op: str, value: Any) -> int:
        refs = AccountLifecycleService._query_doc_refs(collection_path, field, op, value)
        return AccountLifecycleService._delete_documents(refs)

    @staticmethod
    def _delete_all_subcollection_docs(parent_doc_ref: Any, subcollection_name: str) -> int:
        refs = [doc.reference for doc in parent_doc_ref.collection(subcollection_name).stream()]
        return AccountLifecycleService._delete_documents(refs)

    @staticmethod
    def _delete_collection_docs_for_user(collection_path: str, uid: str) -> int:
        user_doc = db.collection('humanUsers').document(uid).get()
        usernames = set()
        if user_doc.exists:
            user_data = user_doc.to_dict() or {}
            for value in [user_data.get('username'), user_data.get('name')]:
                if isinstance(value, str) and value.strip():
                    usernames.add(value.strip())

        candidate_fields = [
            'user_document_id',
            'user_id',
            'userId',
            'author_id',
            'authorId',
            'owner_id',
            'ownerId',
            'reposting_user_id',
            'user_name',
            'username',
            'author',
            'original_post_author',
        ]

        refs: List[Any] = []
        for doc in db.collection(collection_path).stream():
            data = doc.to_dict() or {}
            should_delete = False

            for field_name in candidate_fields:
                value = data.get(field_name)
                if isinstance(value, str) and (value == uid or value in usernames):
                    should_delete = True
                    break
                if isinstance(value, list) and any(
                    isinstance(item, str) and (item == uid or item in usernames)
                    for item in value
                ):
                    should_delete = True
                    break

            if should_delete:
                refs.append(doc.reference)

        return AccountLifecycleService._delete_documents(refs)

    @staticmethod
    def _extract_related_user_ids(entries: Any) -> List[str]:
        related_ids: List[str] = []
        if not isinstance(entries, list):
            return related_ids

        for entry in entries:
            if isinstance(entry, str):
                value = entry.strip()
                if value:
                    related_ids.append(value)
                continue

            if isinstance(entry, dict):
                entry_type = str(entry.get('type', 'human')).lower()
                if entry_type not in {'human', 'ai'}:
                    continue
                entry_id = entry.get('id') or entry.get('uid') or entry.get('userId') or entry.get('_id')
                if entry_id:
                    related_ids.append(str(entry_id).strip())

        deduped: List[str] = []
        seen = set()
        for value in related_ids:
            if not value or value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        return deduped

    @staticmethod
    def _remove_uid_from_user_arrays(user_ref: Any, uid: str) -> bool:
        user_doc = user_ref.get()
        if not user_doc.exists:
            return False

        data = user_doc.to_dict() or {}
        current_followers = data.get('followers', []) or []
        current_following = data.get('following', []) or []

        def _prune(entries: Any) -> List[Any]:
            if not isinstance(entries, list):
                return []

            pruned: List[Any] = []
            for entry in entries:
                if isinstance(entry, str):
                    if entry != uid:
                        pruned.append(entry)
                    continue

                if isinstance(entry, dict):
                    entry_id = entry.get('id') or entry.get('uid') or entry.get('userId') or entry.get('_id')
                    if entry_id == uid:
                        continue
                    pruned.append(entry)
                    continue

                pruned.append(entry)

            return pruned

        updated_followers = _prune(current_followers)
        updated_following = _prune(current_following)

        if updated_followers == current_followers and updated_following == current_following:
            return False

        user_ref.update({
            'followers': updated_followers,
            'following': updated_following,
            'followers_count': len(updated_followers),
            'following_count': len(updated_following),
        })
        return True

    @staticmethod
    def _extract_storage_blob_path(raw_value: str, bucket_name: Optional[str]) -> Optional[str]:
        if not raw_value or not isinstance(raw_value, str):
            return None

        value = raw_value.strip()
        if not value:
            return None

        if value.startswith('gs://'):
            parsed = urlparse(value)
            if bucket_name and parsed.netloc and parsed.netloc != bucket_name:
                return None
            return parsed.path.lstrip('/') or None

        if value.startswith('http://') or value.startswith('https://'):
            parsed = urlparse(value)
            if '/o/' not in parsed.path:
                return None
            encoded_path = parsed.path.split('/o/', 1)[1]
            decoded = unquote(encoded_path)
            return decoded or None

        if '/' in value and not value.lower().startswith('data:'):
            return value

        return None

    @staticmethod
    def _collect_string_values(payload: Any, output: set) -> None:
        if payload is None:
            return
        if isinstance(payload, str):
            output.add(payload)
            return
        if isinstance(payload, list):
            for item in payload:
                AccountLifecycleService._collect_string_values(item, output)
            return
        if isinstance(payload, dict):
            for item in payload.values():
                AccountLifecycleService._collect_string_values(item, output)

    @staticmethod
    def _delete_storage_files(uid: str) -> Dict[str, int]:
        if storage is None:
            return {'storage.deleted': 0, 'storage.skipped_no_bucket': 1}

        bucket_name = getattr(storage, 'name', None)
        candidate_paths = set()

        user_doc = db.collection('humanUsers').document(uid).get()
        if user_doc.exists:
            values = set()
            AccountLifecycleService._collect_string_values(user_doc.to_dict() or {}, values)
            for value in values:
                blob_path = AccountLifecycleService._extract_storage_blob_path(value, bucket_name)
                if blob_path:
                    candidate_paths.add(blob_path)

        post_docs = []
        post_docs.extend(db.collection('humanPosts').where('user_document_id', '==', uid).stream())
        post_docs.extend(db.collection('humanPosts').where('user_id', '==', uid).stream())
        for post_doc in post_docs:
            values = set()
            AccountLifecycleService._collect_string_values(post_doc.to_dict() or {}, values)
            for value in values:
                blob_path = AccountLifecycleService._extract_storage_blob_path(value, bucket_name)
                if blob_path:
                    candidate_paths.add(blob_path)

        prefix_candidates = [
            f'users/{uid}/',
            f'humanUsers/{uid}/',
            f'profilePictures/{uid}/',
            f'posts/{uid}/',
            f'uploads/{uid}/',
            f'conversations/{uid}/',
        ]

        blob_names = set(candidate_paths)
        for prefix in prefix_candidates:
            try:
                for blob in storage.list_blobs(prefix=prefix):
                    blob_names.add(blob.name)
            except Exception as list_ex:
                logger.warning('Unable to list blobs for prefix %s: %s', prefix, list_ex)

        deleted_count = 0
        for blob_name in blob_names:
            try:
                storage.blob(blob_name).delete()
                deleted_count += 1
            except Exception:
                continue

        return {'storage.deleted': deleted_count}

    @staticmethod
    def _remove_uid_from_follow_arrays(uid: str) -> Dict[str, int]:
        updated_followers = 0
        updated_following = 0

        deleted_user_doc = db.collection('humanUsers').document(uid).get()
        if not deleted_user_doc.exists:
            return {
                'humanUsers.followers_arrays_updated': 0,
                'humanUsers.following_arrays_updated': 0,
            }

        user_data = deleted_user_doc.to_dict() or {}
        related_user_ids = AccountLifecycleService._extract_related_user_ids(
            (user_data.get('followers', []) or []) + (user_data.get('following', []) or [])
        )

        for related_user_id in related_user_ids:
            related_user_ref = db.collection('humanUsers').document(related_user_id)
            if AccountLifecycleService._remove_uid_from_user_arrays(related_user_ref, uid):
                updated_followers += 1
                updated_following += 1

        return {
            'humanUsers.followers_arrays_updated': updated_followers,
            'humanUsers.following_arrays_updated': updated_following,
        }

    @staticmethod
    def _remove_nested_post_comments(uid: str) -> int:
        updated_docs = 0
        for post_comment_doc in db.collection('postComments').stream():
            data = post_comment_doc.to_dict() or {}
            comments = data.get('comments')
            if not isinstance(comments, list):
                continue

            filtered = []
            removed_any = False
            for comment in comments:
                if not isinstance(comment, dict):
                    filtered.append(comment)
                    continue

                comment_uid = comment.get('userId') or comment.get('uid')
                if comment_uid == uid:
                    removed_any = True
                    continue
                filtered.append(comment)

            if removed_any:
                updated_docs += 1
                post_comment_doc.reference.update({'comments': filtered})

        return updated_docs

    @staticmethod
    def _entry_has_user_reference(entry: Any, uid: str) -> bool:
        if not isinstance(entry, dict):
            return False

        for key in ['uid', 'user_document_id', 'userId', 'user_id', 'id', '_id']:
            value = entry.get(key)
            if isinstance(value, str) and value.strip() == uid:
                return True
        return False

    @staticmethod
    def _remove_uid_from_liked_by_arrays(uid: str) -> Dict[str, int]:
        collections_updated = 0
        entries_removed = 0

        for collection_name in ['humanPosts', 'reposts']:
            for doc in db.collection(collection_name).stream():
                data = doc.to_dict() or {}
                liked_by = data.get('likedBy')
                if not isinstance(liked_by, list):
                    continue

                filtered = []
                removed_here = 0
                for entry in liked_by:
                    if AccountLifecycleService._entry_has_user_reference(entry, uid):
                        removed_here += 1
                        continue
                    filtered.append(entry)

                if removed_here > 0:
                    doc.reference.update({'likedBy': filtered})
                    collections_updated += 1
                    entries_removed += removed_here

        return {
            'likedBy.docs_updated': collections_updated,
            'likedBy.entries_removed': entries_removed,
        }

    @staticmethod
    def _delete_or_prune_post_comments(uid: str) -> Dict[str, int]:
        docs_deleted = 0
        docs_updated = 0
        comment_maps_removed = 0
        reaction_maps_removed = 0

        for post_comment_doc in db.collection('postComments').stream():
            data = post_comment_doc.to_dict() or {}

            root_user_refs = [
                data.get('uid'),
                data.get('user_document_id'),
                data.get('userId'),
                data.get('user_id'),
            ]
            if any(isinstance(value, str) and value.strip() == uid for value in root_user_refs):
                post_comment_doc.reference.delete()
                docs_deleted += 1
                continue

            comments = data.get('comments')
            if not isinstance(comments, list):
                continue

            filtered_comments = []
            removed_comments_here = 0
            updated_comment_entries = False

            for comment in comments:
                if not isinstance(comment, dict):
                    filtered_comments.append(comment)
                    continue

                if AccountLifecycleService._entry_has_user_reference(comment, uid):
                    removed_comments_here += 1
                    continue

                updated_comment = dict(comment)
                for reaction_field in ['likedBy', 'dislikedBy']:
                    reactions = updated_comment.get(reaction_field)
                    if not isinstance(reactions, list):
                        continue

                    filtered_reactions = []
                    removed_reactions_here = 0
                    for reaction_entry in reactions:
                        if AccountLifecycleService._entry_has_user_reference(reaction_entry, uid):
                            removed_reactions_here += 1
                            continue
                        filtered_reactions.append(reaction_entry)

                    if removed_reactions_here > 0:
                        updated_comment[reaction_field] = filtered_reactions
                        reaction_maps_removed += removed_reactions_here
                        updated_comment_entries = True

                filtered_comments.append(updated_comment)

            if removed_comments_here > 0 or updated_comment_entries:
                post_comment_doc.reference.update({'comments': filtered_comments})
                docs_updated += 1
                comment_maps_removed += removed_comments_here

        return {
            'postComments.docs_deleted': docs_deleted,
            'postComments.docs_updated': docs_updated,
            'postComments.comment_maps_removed': comment_maps_removed,
            'postComments.reaction_maps_removed': reaction_maps_removed,
        }

    @staticmethod
    def _payload_contains_uid_reference(payload: Any, uid: str) -> bool:
        if payload is None:
            return False

        if isinstance(payload, list):
            return any(AccountLifecycleService._payload_contains_uid_reference(item, uid) for item in payload)

        if isinstance(payload, dict):
            user_reference_keys = {
                'uid', 'user_document_id', 'userId', 'user_id',
                'senderId', 'followerId', 'followedUserId', 'postAuthorId',
                'author_id', 'authorId', 'owner_id', 'ownerId'
            }

            for key, value in payload.items():
                if key in user_reference_keys and isinstance(value, str) and value.strip() == uid:
                    return True
                if AccountLifecycleService._payload_contains_uid_reference(value, uid):
                    return True

        return False

    @staticmethod
    def _delete_notifications_holding_user_reference(uid: str) -> Dict[str, int]:
        refs_to_delete = []

        for notif_doc in db.collection('notifications').stream():
            data = notif_doc.to_dict() or {}
            if AccountLifecycleService._payload_contains_uid_reference(data, uid):
                refs_to_delete.append(notif_doc.reference)

        deleted = AccountLifecycleService._delete_documents(refs_to_delete)
        return {
            'notifications.reference_deleted': deleted,
        }

    @staticmethod
    def _delete_conversation_messages_by_sender(conversation_ref: Any, uid: str) -> int:
        candidate_fields = ['senderId', 'userId', 'uid', 'senderUID']
        refs = []

        for field_name in candidate_fields:
            refs.extend(AccountLifecycleService._query_doc_refs(
                f'conversations/{conversation_ref.id}/messages',
                field_name,
                '==',
                uid,
            ))

        return AccountLifecycleService._delete_documents(refs)

    @staticmethod
    def _purge_user_from_conversations(uid: str) -> Dict[str, int]:
        conversations_processed = 0
        conversations_deleted = 0
        messages_deleted = 0

        for conv_doc in db.collection('conversations').where('participants', 'array_contains', uid).stream():
            conversations_processed += 1
            conv_data = conv_doc.to_dict() or {}
            participants = conv_data.get('participants', []) or []
            if len(participants) != 2:
                logger.info('Skipping non-DM conversation %s while deleting user %s', conv_doc.id, uid)
                continue

            messages_deleted += AccountLifecycleService._delete_all_subcollection_docs(
                conv_doc.reference,
                'messages',
            )
            conv_doc.reference.delete()
            conversations_deleted += 1

        return {
            'conversations.processed': conversations_processed,
            'conversations.deleted': conversations_deleted,
            'conversations.messages_deleted': messages_deleted,
        }

    @staticmethod
    def _delete_user_feedback_root(uid: str) -> Dict[str, int]:
        user_feedback_ref = db.collection('userFeedback').document(uid)
        interactions_deleted = AccountLifecycleService._delete_all_subcollection_docs(
            user_feedback_ref,
            'interactions',
        )

        root_deleted = 0
        if user_feedback_ref.get().exists:
            user_feedback_ref.delete()
            root_deleted = 1

        return {
            'userFeedback.interactions_deleted': interactions_deleted,
            'userFeedback.root_deleted': root_deleted,
        }

    @staticmethod
    def _delete_human_user_root(uid: str) -> Dict[str, int]:
        user_ref = db.collection('humanUsers').document(uid)
        inventory_deleted = AccountLifecycleService._delete_all_subcollection_docs(user_ref, 'inventory')
        groups_deleted = AccountLifecycleService._delete_all_subcollection_docs(user_ref, 'groups')

        root_deleted = 0
        if user_ref.get().exists:
            user_ref.delete()
            root_deleted = 1

        return {
            'humanUsers.inventory_deleted': inventory_deleted,
            'humanUsers.groups_deleted': groups_deleted,
            'humanUsers.root_deleted': root_deleted,
        }

    @staticmethod
    def _build_purge_steps(uid: str) -> List[Tuple[str, Callable[[], Dict[str, int]]]]:
        return [
            ('delete_storage_files', lambda: AccountLifecycleService._delete_storage_files(uid)),
            ('delete_human_posts', lambda: {
                'humanPosts.matched_deleted': AccountLifecycleService._delete_collection_docs_for_user('humanPosts', uid),
            }),
            ('delete_reposts', lambda: {
                'reposts.matched_deleted': AccountLifecycleService._delete_collection_docs_for_user('reposts', uid),
            }),
            ('cleanup_liked_by_arrays', lambda: AccountLifecycleService._remove_uid_from_liked_by_arrays(uid)),
            ('delete_post_likes', lambda: {
                'postLikes.user_id': AccountLifecycleService._delete_query_docs('postLikes', 'user_id', '==', uid),
                'post_likes.user_id': AccountLifecycleService._delete_query_docs('post_likes', 'user_id', '==', uid),
            }),
            ('delete_post_comments', lambda: AccountLifecycleService._delete_or_prune_post_comments(uid)),
            ('purge_conversations', lambda: AccountLifecycleService._purge_user_from_conversations(uid)),
            ('delete_notifications', lambda: {
                'notifications.userId': AccountLifecycleService._delete_query_docs('notifications', 'userId', '==', uid),
                'notifications.user_document_id': AccountLifecycleService._delete_query_docs('notifications', 'user_document_id', '==', uid),
                **AccountLifecycleService._delete_notifications_holding_user_reference(uid),
                'notificationsQueue.uid': AccountLifecycleService._delete_query_docs('notificationsQueue', 'uid', '==', uid),
                'feedbacks.userId': AccountLifecycleService._delete_query_docs('feedbacks', 'userId', '==', uid),
            }),
            ('delete_referrals', lambda: {
                'referrals.referrerId': AccountLifecycleService._delete_query_docs('referrals', 'referrerId', '==', uid),
                'referrals.referrer_id': AccountLifecycleService._delete_query_docs('referrals', 'referrer_id', '==', uid),
                'referrals.installerId': AccountLifecycleService._delete_query_docs('referrals', 'installerId', '==', uid),
                'referrals.referee_id': AccountLifecycleService._delete_query_docs('referrals', 'referee_id', '==', uid),
                'referral_rewards.referrer_id': AccountLifecycleService._delete_query_docs('referral_rewards', 'referrer_id', '==', uid),
                'referral_rewards.referee_id': AccountLifecycleService._delete_query_docs('referral_rewards', 'referee_id', '==', uid),
            }),
            ('delete_user_feedback', lambda: AccountLifecycleService._delete_user_feedback_root(uid)),
            ('cleanup_follow_arrays', lambda: AccountLifecycleService._remove_uid_from_follow_arrays(uid)),
            ('delete_human_user_root', lambda: AccountLifecycleService._delete_human_user_root(uid)),
            ('delete_firebase_auth_user', lambda: AccountLifecycleService._delete_auth_user(uid)),
        ]

    @staticmethod
    def _delete_auth_user(uid: str) -> Dict[str, int]:
        try:
            auth.delete_user(uid)
            return {'firebaseAuth.deleted': 1}
        except Exception as auth_ex:
            # If user is already deleted, treat as idempotent success
            if 'No user record found' in str(auth_ex):
                return {'firebaseAuth.deleted': 0}
            raise

    @staticmethod
    def request_deletion(uid: str) -> Tuple[Any, int]:
        try:
            job_ref = AccountLifecycleService._job_ref(uid)
            existing = job_ref.get()
            if existing.exists:
                data = existing.to_dict() or {}
                status = data.get('status')
                if status == 'completed':
                    return jsonify({'success': True, 'uid': uid, 'status': 'completed', 'job': data}), 200
                return jsonify({'success': True, 'uid': uid, 'status': status, 'job': data}), 200

            now = AccountLifecycleService._now_utc()
            purge_after = now + timedelta(days=AccountLifecycleService.PURGE_WINDOW_DAYS)
            payload = {
                'uid': uid,
                'status': 'pending_window',
                'requestedAt': firestore.SERVER_TIMESTAMP,
                'purgeAfter': purge_after,
                'purgeWindowDays': AccountLifecycleService.PURGE_WINDOW_DAYS,
                'updatedAt': firestore.SERVER_TIMESTAMP,
                'attempts': 0,
                'lastError': None,
                'progress': {
                    'completedSteps': {},
                    'stepsTotal': 11,
                    'stepsDone': 0,
                    'currentStep': None,
                    'counters': {},
                },
            }
            job_ref.set(payload, merge=True)

            db.collection('humanUsers').document(uid).set({
                'is_deactivated': True,
                'account_status': 'deactivated',
                'deactivatedAt': firestore.SERVER_TIMESTAMP,
                'is_searchable': False,
                'deletionRequestedAt': firestore.SERVER_TIMESTAMP,
                'deletionStatus': 'pending_window',
                'deletionPurgeAfter': purge_after,
            }, merge=True)

            post_refs = []
            post_refs.extend(AccountLifecycleService._query_doc_refs('humanPosts', 'user_document_id', '==', uid))
            post_refs.extend(AccountLifecycleService._query_doc_refs('humanPosts', 'user_id', '==', uid))
            AccountLifecycleService._batch_update_documents(post_refs, {
                'deactivated': True,
            })

            repost_refs = AccountLifecycleService._query_doc_refs('reposts', 'user_document_id', '==', uid)
            AccountLifecycleService._batch_update_documents(repost_refs, {
                'deactivated': True,
            })

            AccountLifecycleService._write_log(
                job_ref,
                'info',
                'Account deletion requested. Waiting window started.'
            )

            return jsonify({
                'success': True,
                'uid': uid,
                'status': 'pending_window',
                'purgeAfter': purge_after.isoformat(),
                'purgeWindowDays': AccountLifecycleService.PURGE_WINDOW_DAYS,
            }), 200
        except Exception as ex:
            logger.exception('Error creating deletion request')
            return jsonify({'success': False, 'error': str(ex)}), 500

    @staticmethod
    def deactivate_account(uid: str) -> Tuple[Any, int]:
        """Deactivate account without deleting Firebase Auth record."""
        try:
            user_ref = db.collection('humanUsers').document(uid)
            user_doc = user_ref.get()
            if not user_doc.exists:
                return jsonify({'success': False, 'error': 'User not found'}), 404

            user_ref.set({
                'is_deactivated': True,
                'account_status': 'deactivated',
                'deactivatedAt': firestore.SERVER_TIMESTAMP,
                'is_searchable': False,
            }, merge=True)

            post_refs = []
            post_refs.extend(AccountLifecycleService._query_doc_refs('humanPosts', 'user_document_id', '==', uid))
            post_refs.extend(AccountLifecycleService._query_doc_refs('humanPosts', 'user_id', '==', uid))
            human_posts_updated = AccountLifecycleService._batch_update_documents(post_refs, {
                'deactivated': True,
            })

            repost_refs = AccountLifecycleService._query_doc_refs('reposts', 'user_document_id', '==', uid)
            reposts_updated = AccountLifecycleService._batch_update_documents(repost_refs, {
                'deactivated': True,
            })

            return jsonify({
                'success': True,
                'uid': uid,
                'firebaseAuthDeleted': False,
                'deactivationSummary': {
                    'humanPosts.updated': human_posts_updated,
                    'reposts.updated': reposts_updated,
                }
            }), 200
        except Exception as ex:
            logger.exception('Error deactivating account')
            return jsonify({'success': False, 'error': str(ex)}), 500

    @staticmethod
    def reactivate_account(uid: str, cancel_pending_deletion: bool = True) -> Tuple[Any, int]:
        """Reactivate a previously deactivated account and restore content visibility."""
        try:
            user_ref = db.collection('humanUsers').document(uid)
            user_doc = user_ref.get()
            if not user_doc.exists:
                return jsonify({'success': False, 'error': 'User not found'}), 404

            user_ref.set({
                'is_deactivated': False,
                'account_status': 'active',
                'is_searchable': True,
                'reactivatedAt': firestore.SERVER_TIMESTAMP,
                'deletionStatus': firestore.DELETE_FIELD,
                'deletionRequestedAt': firestore.DELETE_FIELD,
                'deletionPurgeAfter': firestore.DELETE_FIELD,
            }, merge=True)

            post_refs = []
            post_refs.extend(AccountLifecycleService._query_doc_refs('humanPosts', 'user_document_id', '==', uid))
            post_refs.extend(AccountLifecycleService._query_doc_refs('humanPosts', 'user_id', '==', uid))
            human_posts_updated = AccountLifecycleService._batch_update_documents(post_refs, {
                'deactivated': False,
            })

            repost_refs = AccountLifecycleService._query_doc_refs('reposts', 'user_document_id', '==', uid)
            reposts_updated = AccountLifecycleService._batch_update_documents(repost_refs, {
                'deactivated': False,
            })

            deletion_job_deleted = False
            if cancel_pending_deletion:
                deletion_job_ref = AccountLifecycleService._job_ref(uid)
                if deletion_job_ref.get().exists:
                    logs_refs = [d.reference for d in deletion_job_ref.collection('logs').stream()]
                    AccountLifecycleService._delete_documents(logs_refs)
                    deletion_job_ref.delete()
                    deletion_job_deleted = True

            return jsonify({
                'success': True,
                'uid': uid,
                'reactivationSummary': {
                    'humanPosts.updated': human_posts_updated,
                    'reposts.updated': reposts_updated,
                    'pendingDeletionCancelled': deletion_job_deleted,
                }
            }), 200
        except Exception as ex:
            logger.exception('Error reactivating account')
            return jsonify({'success': False, 'error': str(ex)}), 500

    @staticmethod
    def get_deletion_status(uid: str) -> Tuple[Any, int]:
        try:
            job_doc = AccountLifecycleService._job_ref(uid).get()
            if not job_doc.exists:
                return jsonify({'success': True, 'uid': uid, 'status': 'none'}), 200

            data = job_doc.to_dict() or {}
            recent_logs = []
            for log_doc in AccountLifecycleService._job_ref(uid).collection('logs').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(20).stream():
                recent_logs.append(log_doc.to_dict() or {})

            return jsonify({'success': True, 'uid': uid, 'job': data, 'recentLogs': recent_logs}), 200
        except Exception as ex:
            logger.exception('Error reading deletion status')
            return jsonify({'success': False, 'error': str(ex)}), 500

    @staticmethod
    def process_pending_jobs(uid: Optional[str] = None, force: bool = False, limit: int = 25) -> Tuple[Any, int]:
        try:
            summaries = []
            processed = 0

            if uid:
                summary = AccountLifecycleService._process_single_job(uid, force=force)
                summaries.append(summary)
                processed = 1
            else:
                capped_limit = max(1, min(limit, 100))
                now = AccountLifecycleService._now_utc()
                for doc in db.collection('deletionRequests').stream():
                    if processed >= capped_limit:
                        break
                    data = doc.to_dict() or {}
                    status = data.get('status')
                    if status == 'completed':
                        continue

                    purge_after = AccountLifecycleService._to_aware_datetime(data.get('purgeAfter'))
                    if not force and status == 'pending_window' and purge_after and purge_after > now:
                        continue

                    summaries.append(AccountLifecycleService._process_single_job(doc.id, force=force))
                    processed += 1

            return jsonify({'success': True, 'processed': processed, 'summaries': summaries}), 200
        except Exception as ex:
            logger.exception('Error processing deletion jobs')
            return jsonify({'success': False, 'error': str(ex)}), 500

    @staticmethod
    def _process_single_job(uid: str, force: bool = False) -> Dict[str, Any]:
        job_ref = AccountLifecycleService._job_ref(uid)
        job_doc = job_ref.get()
        if not job_doc.exists:
            return {'uid': uid, 'status': 'missing'}

        job_data = job_doc.to_dict() or {}
        status = job_data.get('status')
        if status == 'completed':
            return {'uid': uid, 'status': 'completed', 'skipped': True}

        now = AccountLifecycleService._now_utc()
        purge_after = AccountLifecycleService._to_aware_datetime(job_data.get('purgeAfter'))
        if not force and status == 'pending_window' and purge_after and purge_after > now:
            return {
                'uid': uid,
                'status': 'pending_window',
                'skipped': True,
                'reason': 'purge_window_not_elapsed',
                'purgeAfter': purge_after.isoformat(),
            }

        progress = dict(job_data.get('progress') or {})
        completed_steps = dict(progress.get('completedSteps') or {})
        counters = dict(progress.get('counters') or {})

        attempts = int(job_data.get('attempts') or 0) + 1
        job_ref.set({
            'status': 'processing',
            'attempts': attempts,
            'startedAt': job_data.get('startedAt') or firestore.SERVER_TIMESTAMP,
            'updatedAt': firestore.SERVER_TIMESTAMP,
            'lastError': None,
        }, merge=True)
        db.collection('humanUsers').document(uid).set({'deletionStatus': 'processing'}, merge=True)

        AccountLifecycleService._write_log(job_ref, 'info', 'Started deletion processing')

        steps = AccountLifecycleService._build_purge_steps(uid)

        for step_key, step_func in steps:
            if completed_steps.get(step_key):
                continue

            try:
                AccountLifecycleService._write_log(job_ref, 'info', f'Running step: {step_key}', step=step_key)
                step_result = step_func() or {}
                counters.update(step_result)
                completed_steps[step_key] = True
                steps_done = len([k for k, done in completed_steps.items() if done])

                job_ref.set({
                    'updatedAt': firestore.SERVER_TIMESTAMP,
                    'progress': {
                        'completedSteps': completed_steps,
                        'stepsTotal': len(steps),
                        'stepsDone': steps_done,
                        'currentStep': step_key,
                        'counters': counters,
                    },
                }, merge=True)
                AccountLifecycleService._write_log(job_ref, 'info', f'Step complete: {step_key}', step=step_key)
            except Exception as step_ex:
                error_message = f'{step_key} failed: {step_ex}'
                logger.exception('Deletion step failed for %s at %s', uid, step_key)
                job_ref.set({
                    'status': 'failed',
                    'updatedAt': firestore.SERVER_TIMESTAMP,
                    'lastError': error_message,
                    'progress': {
                        'completedSteps': completed_steps,
                        'stepsTotal': len(steps),
                        'stepsDone': len([k for k, done in completed_steps.items() if done]),
                        'currentStep': step_key,
                        'counters': counters,
                    },
                }, merge=True)
                db.collection('humanUsers').document(uid).set({'deletionStatus': 'failed'}, merge=True)
                AccountLifecycleService._write_log(job_ref, 'error', error_message, step=step_key)
                return {'uid': uid, 'status': 'failed', 'error': error_message}

        job_ref.set({
            'status': 'completed',
            'updatedAt': firestore.SERVER_TIMESTAMP,
            'completedAt': firestore.SERVER_TIMESTAMP,
            'lastError': None,
            'progress': {
                'completedSteps': completed_steps,
                'stepsTotal': len(steps),
                'stepsDone': len([k for k, done in completed_steps.items() if done]),
                'currentStep': None,
                'counters': counters,
            },
        }, merge=True)

        AccountLifecycleService._write_log(job_ref, 'info', 'Deletion completed successfully')
        return {'uid': uid, 'status': 'completed', 'counters': counters}
