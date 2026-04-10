# services/user/profile_service.py
from dependencies import db
from typing import Dict, Any, Optional, Tuple
import logging
from datetime import datetime
from flask import jsonify, request
from firebase_admin import firestore
from services.content.category_service import CategoryService
from services.recommendation.gorse_client import gorse_client

logger = logging.getLogger(__name__)

class ProfileService:
    """Service for user profile operations"""

    @staticmethod
    def _resolve_username(user_data: Dict[str, Any], fallback: str = '') -> str:
        username = (
            user_data.get('username')
            or user_data.get('Username')
            or user_data.get('name')
            or fallback
        )
        return str(username or '').strip()

    @staticmethod
    def _is_user_inactive(user_data: Dict[str, Any]) -> bool:
        if not user_data:
            return False
        if user_data.get('is_deactivated') is True:
            return True
        if user_data.get('account_status') == 'deactivated':
            return True
        if user_data.get('deletionStatus') in {'pending_window', 'processing'}:
            return True
        return False

    @staticmethod
    def _get_user_name(user_id: str, user_type: str = 'human') -> str:
        if not user_id:
            return ''
        try:
            preferred_collection = 'aiUsers' if user_type == 'ai' else 'humanUsers'
            doc = db.collection(preferred_collection).document(user_id).get()
            if doc.exists:
                return ProfileService._resolve_username(doc.to_dict() or {}, user_id)

            alternate_collection = 'humanUsers' if preferred_collection == 'aiUsers' else 'aiUsers'
            alt_doc = db.collection(alternate_collection).document(user_id).get()
            if alt_doc.exists:
                return ProfileService._resolve_username(alt_doc.to_dict() or {}, user_id)
        except Exception:
            pass
        return user_id

    @staticmethod
    def _resolve_user_ref_and_doc(user_id: str, user_type: str) -> Tuple[Optional[Any], Optional[Any]]:
        normalized_id = str(user_id or '').strip()
        if not normalized_id:
            return None, None

        preferred_collection_name = 'aiUsers' if user_type == 'ai' else 'humanUsers'
        fallback_collection_name = 'humanUsers' if preferred_collection_name == 'aiUsers' else 'aiUsers'

        def _resolve_in_collection(collection_name: str) -> Tuple[Optional[Any], Optional[Any]]:
            collection = db.collection(collection_name)

            direct_ref = collection.document(normalized_id)
            direct_doc = direct_ref.get()
            if direct_doc.exists:
                return direct_ref, direct_doc

            for field_name in ['uid', 'id', 'userId', 'username', 'Username', 'name']:
                try:
                    matches = list(collection.where(field_name, '==', normalized_id).limit(1).stream())
                    if matches:
                        doc = matches[0]
                        return doc.reference, doc
                except Exception:
                    continue

            return None, None

        ref, doc = _resolve_in_collection(preferred_collection_name)
        if ref is not None and doc is not None:
            return ref, doc

        return _resolve_in_collection(fallback_collection_name)

    @staticmethod
    def _resolve_actor_identity(user_id: str) -> Tuple[Optional[Any], Optional[Any], str, str]:
        ref, doc = ProfileService._resolve_user_ref_and_doc(user_id, 'human')
        if ref is None or doc is None:
            return None, None, 'human', ''

        data = doc.to_dict() or {}
        username = ProfileService._resolve_username(data, '').strip()
        user_type = 'ai' if str(getattr(ref, 'path', '')).startswith('aiUsers/') else 'human'
        return ref, doc, user_type, username

    @staticmethod
    def _resolve_likeable_post(post_id: str) -> Tuple[Optional[Any], Optional[Dict[str, Any]], Optional[str]]:
        normalized_post_id = str(post_id or '').strip()
        if not normalized_post_id:
            return None, None, None

        for collection_name in ['humanPosts', 'reposts']:
            post_ref = db.collection(collection_name).document(normalized_post_id)
            post_doc = post_ref.get()
            if post_doc.exists:
                return post_ref, post_doc.to_dict() or {}, collection_name

        return None, None, None

    @staticmethod
    def create_profile(user_id: str, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new user profile"""
        try:
            # Extract from create_profile() route
            user_ref = db.collection('users').document(user_id)
            user_ref.set(profile_data)
            return {'success': True, 'message': 'Profile created'}
        except Exception as e:
            logger.error(f"Error creating profile: {e}")
            raise

    @staticmethod
    def update_name(user_id: str, name: str) -> Dict[str, Any]:
        """Update user's name"""
        try:
            # Extract logic from update_name() route
            if not name or len(name) < 2:
                raise ValueError("Name must be at least 2 characters")

            user_ref = db.collection('users').document(user_id)
            user_ref.update({'name': name})
            return {'success': True, 'message': 'Name updated'}
        except Exception as e:
            logger.error(f"Error updating name: {e}")
            raise

    @staticmethod
    def create_profile(data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            
            if not data:
                return jsonify({"success": False, "error": "Post content is required", "code": "INVALID_POST_CONTENT"}), 400

            # Check if email already exists
            email = data.get("Email")
            if email:
                existing_user = db.collection('humanUsers').where("email", "==", email).limit(1).get()
                if existing_user:
                    return jsonify({
                        "success": False, 
                        "error": "Email already exists",
                        "code": "DUPLICATE_EMAIL"
                    }), 400


            user_data = {
                "name": data.get("Name"),
                "age": data.get("Age"),
                "bio": data.get("Bio"),
                "blockout": [],
                "user_interests": data.get("UserInterests", []),
                "email": email,
                "liked_posts": [],
                "balance": 200,
                "followers": [],
                "following": [],
                "gender": data.get("Gender"),
                "profilePicture": data.get("ProfilePicture"),
                "date_created": firestore.SERVER_TIMESTAMP,
                "uid": data.get("UID"),
                "username": data.get("UserName"),
                "is_influencer": db.collection('influencers').document(uid).get().exists if uid else False
            }

            doc_ref = db.collection('humanUsers').document(data.get("UID")).set(user_data)
            
            # Update Gorse with new user
            try:
                user_interests = data.get("UserInterests", [])
                gorse_client.insert_user(data.get("UID"), labels=user_interests)
                print(f"✓ Synced user {data.get('UID')} to Gorse")
            except Exception as e:
                print(f"⚠ Failed to sync user to Gorse: {e}")
        
            response = {
                "success": True,
                "data": {
                    "UserId": data.get("UID")
                }
            }
            return jsonify(response), 200
        except Exception as ex:
            logger.error("Error creating user profile: %s", ex)
            response = {
                "success": False,
                "error": {
                    "message": "Failed to create user profile",
                    "code": "PROFILE_CREATE_ERROR"
                }
            }
            return jsonify(response), 500

    @staticmethod
    def update_name(data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            
            user_id = data.get("UID")
            name = data.get("Name")
            
            if not user_id or not name:
                return jsonify({"success": False, "error": "User Id and Name are required"}), 400

            # Update the document in Firestore
            db.collection('humanUsers').document(user_id).update({"name": name})
            
            # Sync updated user to Gorse
            try:
                user_doc = db.collection('humanUsers').document(user_id).get()
                if user_doc.exists:
                    user_data = user_doc.to_dict()
                    user_interests = user_data.get("user_interests", [])
                    gorse_client.insert_user(user_id, labels=user_interests)
                    print(f"✓ Synced user {user_id} name update to Gorse")
            except Exception as e:
                print(f"⚠ Failed to sync user update to Gorse: {e}")
            
            return jsonify({"success": True}), 200
        except Exception as ex:
            logger.error("Error updating name: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    @staticmethod
    def update_username(data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            
            user_id = data.get("UID")
            username = data.get("Username")
            
            if not user_id or not username:
                return jsonify({"success": False, "error": "User Id and Username are required"}), 400

            # Check if username already exists
            existing_user = db.collection('humanUsers').where("username", "==", username).limit(1).get()
            if existing_user and existing_user[0].id != user_id:
                return jsonify({"success": False, "error": "Username already exists"}), 400

            # Get the old username for reference
            user_doc = db.collection('humanUsers').document(user_id).get()
            old_username = None
            if user_doc.exists:
                old_username = user_doc.to_dict().get('username')

            # Use batch writes for atomic updates across multiple collections
            batch = db.batch()
            
            # Update the main user document
            user_ref = db.collection('humanUsers').document(user_id)
            batch.update(user_ref, {"username": username})
            
            # Update username in humanPosts collection
            posts_query = db.collection('humanPosts').where('user_document_id', '==', user_id)
            posts = posts_query.stream()
            
            updated_posts = 0
            for post in posts:
                post_ref = db.collection('humanPosts').document(post.id)
                # Update both username and user_name fields if they exist
                post_data = post.to_dict()
                update_data = {}
                
                if 'username' in post_data:
                    update_data['username'] = username
                if 'user_name' in post_data and post_data.get('user_name') == old_username:
                    update_data['user_name'] = username
                    
                if update_data:
                    batch.update(post_ref, update_data)
                    updated_posts += 1
            
            # Update username in postComments collection (in the nested comments array)
            # Note: This is more complex due to the nested structure, so we'll handle it separately
            
            # Update username in conversations collection (participantNames)
            conversations_query = db.collection('conversations')
            conversations = conversations_query.stream()
            
            updated_conversations = 0
            for conversation in conversations:
                conv_data = conversation.to_dict()
                participants = conv_data.get('participants', [])
                participant_names = conv_data.get('participantNames', {})
                
                if user_id in participants and user_id in participant_names:
                    conv_ref = db.collection('conversations').document(conversation.id)
                    batch.update(conv_ref, {f'participantNames.{user_id}': username})
                    updated_conversations += 1
            
            # Update username in any notification collections that might reference the user
            notifications_query = db.collection('notifications').where('userId', '==', user_id)
            notifications = notifications_query.stream()
            
            updated_notifications = 0
            for notification in notifications:
                notif_data = notification.to_dict()
                data_field = notif_data.get('data', {})
                
                # Update any username references in notification data
                update_needed = False
                if data_field.get('senderName') == old_username:
                    data_field['senderName'] = username
                    update_needed = True
                if data_field.get('username') == old_username:
                    data_field['username'] = username
                    update_needed = True
                
                if update_needed:
                    notif_ref = db.collection('notifications').document(notification.id)
                    batch.update(notif_ref, {'data': data_field})
                    updated_notifications += 1
            
            # Commit all updates
            batch.commit()
            
            # Handle postComments separately due to nested structure
            updated_comments = 0
            try:
                post_comments_query = db.collection('postComments')
                post_comments = post_comments_query.stream()
                
                for post_comment_doc in post_comments:
                    post_comment_data = post_comment_doc.to_dict()
                    comments = post_comment_data.get('comments', [])
                    
                    updated_this_post = False
                    for comment in comments:
                        if comment.get('userId') == user_id and comment.get('author') == old_username:
                            comment['author'] = username
                            updated_this_post = True
                            updated_comments += 1
                    
                    if updated_this_post:
                        # Update the entire comments array
                        db.collection('postComments').document(post_comment_doc.id).update({'comments': comments})
                        
            except Exception as comment_error:
                logger.error(f"Error updating comments: {comment_error}")
                # Don't fail the entire operation for comments

            # Update username in other users' followers and following arrays
            updated_followers_arrays = 0
            updated_following_arrays = 0
            
            try:
                # Get all human users to check their followers/following arrays
                all_users_query = db.collection('humanUsers')
                all_users = all_users_query.stream()
                
                for other_user_doc in all_users:
                    if other_user_doc.id == user_id:
                        continue  # Skip the user whose username we're updating
                    
                    other_user_data = other_user_doc.to_dict()
                    other_user_ref = db.collection('humanUsers').document(other_user_doc.id)
                    user_updated = False
                    
                    # Check and update followers array
                    followers = other_user_data.get('followers', [])
                    updated_followers = []
                    followers_changed = False
                    
                    for follower in followers:
                        if isinstance(follower, dict):
                            # New format: {"id": user_id, "username": username, "type": "human"}
                            if follower.get('id') == user_id:
                                follower['username'] = username
                                followers_changed = True
                            updated_followers.append(follower)
                        elif isinstance(follower, str) and follower == user_id:
                            # Legacy format: just user ID - convert to new format with updated username
                            updated_followers.append({
                                "id": user_id,
                                "username": username,
                                "type": "human"
                            })
                            followers_changed = True
                        else:
                            updated_followers.append(follower)
                    
                    if followers_changed:
                        other_user_ref.update({'followers': updated_followers})
                        updated_followers_arrays += 1
                        user_updated = True
                    
                    # Check and update following array
                    following = other_user_data.get('following', [])
                    updated_following = []
                    following_changed = False
                    
                    for followed in following:
                        if isinstance(followed, dict):
                            # New format: {"id": user_id, "username": username, "type": "human"}
                            if followed.get('id') == user_id:
                                followed['username'] = username
                                following_changed = True
                            updated_following.append(followed)
                        elif isinstance(followed, str) and followed == user_id:
                            # Legacy format: just user ID - convert to new format with updated username
                            updated_following.append({
                                "id": user_id,
                                "username": username,
                                "type": "human"
                            })
                            following_changed = True
                        else:
                            updated_following.append(followed)
                    
                    if following_changed:
                        other_user_ref.update({'following': updated_following})
                        updated_following_arrays += 1
                        user_updated = True
                    
            except Exception as followers_following_error:
                logger.error(f"Error updating followers/following arrays: {followers_following_error}")
            
            logger.info(f"Username updated from '{old_username}' to '{username}' for user {user_id}")
            logger.info(f"Updated {updated_posts} posts, {updated_conversations} conversations, {updated_notifications} notifications, {updated_comments} comments, {updated_followers_arrays} followers arrays, {updated_following_arrays} following arrays")
            
            return jsonify({
                "success": True, 
                "message": f"Username updated successfully across all collections",
                "stats": {
                    "posts_updated": updated_posts,
                    "conversations_updated": updated_conversations, 
                    "notifications_updated": updated_notifications,
                    "comments_updated": updated_comments,
                    "followers_arrays_updated": updated_followers_arrays,
                    "following_arrays_updated": updated_following_arrays
                }
            }), 200
            
        except Exception as ex:
            logger.error("Error updating username: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500
        finally:
            # Sync updated user to Gorse
            try:
                user_doc = db.collection('humanUsers').document(user_id).get()
                if user_doc.exists:
                    user_data = user_doc.to_dict()
                    user_interests = user_data.get("user_interests", [])
                    gorse_client.insert_user(user_id, labels=user_interests)
                    print(f"✓ Synced user {user_id} username update to Gorse")
            except Exception as e:
                print(f"⚠ Failed to sync user update to Gorse: {e}")

    @staticmethod
    def update_profile(data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            
            user_id = data.get("UserId")
            print(f"📝 Update profile request for user: {user_id}")
            print(f"   Data: {data}")
            
            update_data = {
                "name": data.get("Name"),
                "username": data.get("Username"),
                "profilePicture": data.get("ProfilePicture"),
                "bio": data.get("Bio"),
            }

            # Update the document in Firestore
            db.collection('humanUsers').document(user_id).update(update_data)
            print(f"✓ Updated profile in Firestore for user {user_id}")
            
            # Sync updated user to Gorse
            try:
                user_doc = db.collection('humanUsers').document(user_id).get()
                if user_doc.exists:
                    user_data = user_doc.to_dict()
                    user_interests = user_data.get("user_interests", [])
                    gorse_client.insert_user(user_id, labels=user_interests)
                    print(f"✓ Synced user {user_id} profile update to Gorse")
            except Exception as e:
                print(f"⚠ Failed to sync user update to Gorse: {e}")
            
            return jsonify({"success": True}), 200
        except Exception as ex:
            logger.error("Error updating profile: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500
            
    @staticmethod
    def update_profile_picture(data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            
            user_id = data.get("UID")
            profile_picture = data.get("ProfilePicture")
            
            if not user_id or not profile_picture:
                return jsonify({"success": False, "error": "User Id and ProfilePicture are required"}), 400

            # Update the document in Firestore
            db.collection('humanUsers').document(user_id).update({"profilePicture": profile_picture})
            
            # Sync updated user to Gorse
            try:
                user_doc = db.collection('humanUsers').document(user_id).get()
                if user_doc.exists:
                    user_data = user_doc.to_dict()
                    user_interests = user_data.get("user_interests", [])
                    gorse_client.insert_user(user_id, labels=user_interests)
                    print(f"✓ Synced user {user_id} profile picture update to Gorse")
            except Exception as e:
                print(f"⚠ Failed to sync user update to Gorse: {e}")
            
            return jsonify({"success": True}), 200
        except Exception as ex:
            logger.error("Error updating profile picture: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    @staticmethod
    def update_bio(data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            
            user_id = data.get("UID")
            bio = data.get("Bio")
            
            if not user_id or not bio:
                return jsonify({"success": False, "error": "User Id and Bio are required"}), 400

            # Update the document in Firestore
            db.collection('humanUsers').document(user_id).update({"bio": bio})
            
            # Sync updated user to Gorse
            try:
                user_doc = db.collection('humanUsers').document(user_id).get()
                if user_doc.exists:
                    user_data = user_doc.to_dict()
                    user_interests = user_data.get("user_interests", [])
                    gorse_client.insert_user(user_id, labels=user_interests)
                    print(f"✓ Synced user {user_id} bio update to Gorse")
            except Exception as e:
                print(f"⚠ Failed to sync user update to Gorse: {e}")
            
            return jsonify({"success": True}), 200
        except Exception as ex:
            logger.error("Error updating bio: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    @staticmethod
    def update_interests(data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            
            user_id = data.get("UID")
            interests = data.get("Interests")

            print(f"📝 Update interests request for user: {user_id}")
            print(f"   Raw interests: {interests}")

            if not user_id or interests is None:
                return jsonify({"success": False, "error": "User Id and Interests are required"}), 400

            # Map raw interests to master categories using direct topic mapping
            master_categories = set()  # Use set to avoid duplicates
            unmapped_interests = []

            if interests and CategoryService.TOPIC_TO_CATEGORY_MAP:
                for interest in interests:
                    interest_key = str(interest).lower().strip()
                    if interest_key in CategoryService.TOPIC_TO_CATEGORY_MAP:
                        master_categories.add(CategoryService.TOPIC_TO_CATEGORY_MAP[interest_key])
                    else:
                        unmapped_interests.append(interest)

                # Convert set to sorted list for consistent ordering
                master_categories = sorted(list(master_categories))
                print(f"   Mapped to master categories: {master_categories}")

                if unmapped_interests:
                    print(f"   ⚠ Unmapped interests: {unmapped_interests}")
            else:
                # Fallback: use raw interests if no mapping available
                master_categories = interests if interests else []
                print(f"   No topic mapping available, using raw interests")

            # Update the document in Firestore with BOTH raw and mapped interests
            db.collection('humanUsers').document(user_id).update({
                "user_interests": interests,  # Original interests for display
                "interests": interests,  # Keep raw interests in 'interests' field
                "masterCategories": master_categories  # Mapped master categories
            })
            print(f"✓ Updated interests in Firestore for user {user_id}")

            # Sync MAPPED interests to Gorse - THIS IS THE MOST IMPORTANT SYNC!
            try:
                gorse_client.insert_user(user_id, labels=master_categories)
                print(f"✓ Synced user {user_id} to Gorse with {len(master_categories)} master category labels")

                # Note about cache refresh
                gorse_client.refresh_user_recommendations(user_id)
            except Exception as e:
                print(f"⚠ Failed to sync user interests to Gorse: {e}")

            return jsonify({"success": True}), 200
        except Exception as ex:
            logger.error("Error updating interests: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500
        
    @staticmethod
    def get_profile(data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            uid = request.args.get('uid')
            if not uid:
                return jsonify({"success": False, "error": "UID is required"}), 400

            user_doc = db.collection('humanUsers').document(uid).get()

            if not user_doc.exists:
                return jsonify({"success": False, "error": "User not found"}), 404

            user_data = user_doc.to_dict()
            if ProfileService._is_user_inactive(user_data):
                return jsonify({"success": False, "error": "User not found"}), 404

            return jsonify({"success": True, "data": user_data}), 200
        except Exception as ex:
            logger.error("Error retrieving profile: %s", ex)
            return jsonify({"success": False, "error": "Failed to retrieve profile", "code": "PROFILE_RETRIEVE_ERROR"}), 500

    @staticmethod
    def follow(data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            
            follower_id = data.get("FollowerId")  # A (authenticated user)
            following_id = data.get("FollowingId")  # B (user to follow)
            follower_type = data.get("FollowerType", "human")  # "human" or "ai"
            follower_username = data.get("FollowerUserName")
            following_type = data.get("FollowingType", "human")  # "human" or "ai"
            following_username = data.get("FollowingUserName")

            follower_id = str(follower_id or '').strip()
            following_id = str(following_id or '').strip()
            follower_type = str(follower_type or 'human').strip().lower()
            following_type = str(following_type or 'human').strip().lower()

            if not follower_id or not following_id:
                return jsonify({"success": False, "error": "FollowerId and FollowingId are required"}), 400

            if follower_type not in {'human', 'ai'}:
                follower_type = 'human'
            if following_type not in {'human', 'ai'}:
                following_type = 'human'

            if follower_id == following_id and follower_type == following_type:
                return jsonify({"success": False, "error": "Cannot follow self"}), 400

            follower_ref, follower_doc = ProfileService._resolve_user_ref_and_doc(
                follower_id,
                follower_type,
            )
            following_ref, following_doc = ProfileService._resolve_user_ref_and_doc(
                following_id,
                following_type,
            )

            if follower_ref is None or following_ref is None or follower_doc is None or following_doc is None:
                return jsonify({"success": False, "error": "User not found"}), 404

            follower_data = follower_doc.to_dict() or {}
            following_data = following_doc.to_dict() or {}

            if follower_type == 'human' and ProfileService._is_user_inactive(follower_data):
                return jsonify({"success": False, "error": "Follower account is inactive"}), 403

            if following_type == 'human' and ProfileService._is_user_inactive(following_data):
                return jsonify({"success": False, "error": "Target account is inactive"}), 403

            follower_username = ProfileService._resolve_username(follower_data, follower_id)
            following_username = ProfileService._resolve_username(following_data, following_id)

            following_entry = {
                "id": following_id,
                "username": following_username,
                "type": following_type
            }
            follower_entry = {
                "id": follower_id,
                "username": follower_username,
                "type": follower_type
            }

            current_following = follower_data.get("following", []) or []
            current_followers = following_data.get("followers", []) or []

            def _normalize(entries, default_type="human"):
                normalized = []
                for entry in entries:
                    if isinstance(entry, str):
                        entry_type = default_type
                        try:
                            if not db.collection('humanUsers').document(entry).get().exists and db.collection('aiUsers').document(entry).get().exists:
                                entry_type = "ai"
                        except Exception:
                            pass
                        normalized.append({
                            "id": entry,
                            "username": ProfileService._get_user_name(entry, entry_type),
                            "type": entry_type,
                        })
                        continue

                    if isinstance(entry, dict):
                        entry_id = str(entry.get("id") or entry.get("uid") or entry.get("userId") or entry.get("_id") or "").strip()
                        if not entry_id:
                            continue
                        entry_type = str(entry.get("type") or default_type)
                        entry_username = entry.get("username") or ProfileService._get_user_name(entry_id, entry_type)
                        normalized.append({
                            "id": entry_id,
                            "username": entry_username,
                            "type": entry_type,
                        })
                        continue

                return normalized

            new_following = _normalize(current_following)
            new_followers = _normalize(current_followers)

            already_following = any(
                isinstance(entry, dict)
                and entry.get("id") == following_id
                and str(entry.get("type", "human")) == following_type
                for entry in new_following
            )
            if not already_following:
                new_following.append(following_entry)

            already_follower = any(
                isinstance(entry, dict)
                and entry.get("id") == follower_id
                and str(entry.get("type", "human")) == follower_type
                for entry in new_followers
            )
            if not already_follower:
                new_followers.append(follower_entry)

            batch = db.batch()
            batch.update(follower_ref, {
                "following": new_following,
                "following_count": firestore.Increment(1) if follower_type == 'ai' and not already_following else len(new_following)
            })
            batch.update(following_ref, {
                "followers": new_followers,
                "followers_count": firestore.Increment(1) if following_type == 'ai' and not already_follower else len(new_followers)
            })
            batch.commit()

            # Create notification for the user being followed (only for human users)
            if following_type == "human" and not already_follower:
                try:
                    from services.notifications.event_service import NotificationEventService

                    notification_event_data = {
                        'followerId': follower_id,
                        'followedUserId': following_id,
                        'timestamp': datetime.utcnow().isoformat()
                    }

                    result, status_code = NotificationEventService.handle_user_follow(notification_event_data)
                    logger.info(f"Follow notification event handled with status {status_code}")

                except Exception as e:
                    logger.error(f"Error creating follow notification: {e}")

            return jsonify({"success": True}), 200
        except Exception as ex:
            logger.error("Error adding follow relationship: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    @staticmethod
    def unfollow(data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            
            follower_id = data.get("FollowerId")  # A (authenticated user)
            following_id = data.get("FollowingId")  # B (user to follow)
            follower_type = data.get("FollowerType", "human")  # "human" or "ai"
            following_type = data.get("FollowingType", "human")  # "human" or "ai"

            follower_id = str(follower_id or '').strip()
            following_id = str(following_id or '').strip()
            follower_type = str(follower_type or 'human').strip().lower()
            following_type = str(following_type or 'human').strip().lower()

            if not follower_id or not following_id:
                return jsonify({"success": False, "error": "FollowerId and FollowingId are required"}), 400

            if follower_type not in {'human', 'ai'}:
                follower_type = 'human'
            if following_type not in {'human', 'ai'}:
                following_type = 'human'

            follower_ref, follower_doc = ProfileService._resolve_user_ref_and_doc(
                follower_id,
                follower_type,
            )
            following_ref, following_doc = ProfileService._resolve_user_ref_and_doc(
                following_id,
                following_type,
            )

            if follower_ref is None or following_ref is None or follower_doc is None or following_doc is None:
                return jsonify({"success": False, "error": "User not found"}), 404

            # Update the follower's following list
            follower_data = follower_doc.to_dict()
            current_following = follower_data.get("following", [])
            new_following = []
            removed = False
            
            for entry in current_following:
                if isinstance(entry, dict) and entry.get("id") == following_id and entry.get("type") == following_type:
                    removed = True
                    continue
                elif entry == following_id:  # Handle legacy format
                    removed = True
                    continue
                new_following.append(entry)
                
            if removed:
                follower_ref.update({
                    "following": new_following,
                    "following_count": firestore.Increment(-1) if follower_type == 'ai' else len(new_following)
                })

            # Update the following user's followers list
            following_data = following_doc.to_dict()
            current_followers = following_data.get("followers", [])
            new_followers = []
            removed = False
            
            for entry in current_followers:
                if isinstance(entry, dict) and entry.get("id") == follower_id and entry.get("type") == follower_type:
                    removed = True
                    continue
                elif entry == follower_id:  # Handle legacy format
                    removed = True
                    continue
                new_followers.append(entry)
                
            if removed:
                following_ref.update({
                    "followers": new_followers,
                    "followers_count": firestore.Increment(-1) if following_type == 'ai' else len(new_followers)
                })

            return jsonify({"success": True}), 200
        except Exception as ex:
            logger.error("Error removing follow relationship: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    @staticmethod
    def remove_from_following(data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            
            user_id = data.get("UserId")  # A (authenticated user)
            following_id = data.get("FollowingId")  # B (user to remove from A's following list)
            user_type = data.get("UserType", "human")  # "human" or "ai"
            following_type = data.get("FollowingType", "human")  # "human" or "ai"

            logger.info(f"User {user_id} ({user_type}) is managing their following list by removing {following_id} ({following_type}).")

            # Determine the correct collections based on user types
            user_collection = 'aiUsers' if user_type == 'ai' else 'humanUsers'
            following_collection = 'aiUsers' if following_type == 'ai' else 'humanUsers'
            
            # For AI users, the document ID is the username
            user_doc_id = user_id
            following_doc_id = following_id

            user_ref = db.collection(user_collection).document(user_doc_id)
            following_ref = db.collection(following_collection).document(following_doc_id)
            
            # Get current following list
            user_doc = user_ref.get()
            if not user_doc.exists:
                return jsonify({"success": False, "error": "User not found"}), 404
                
            user_data = user_doc.to_dict()
            current_following = user_data.get("following", [])
            new_following = []
            removed = False
            
            for entry in current_following:
                if isinstance(entry, dict) and entry.get("id") == following_id and entry.get("type") == following_type:
                    removed = True
                    continue
                elif entry == following_id:  # Handle legacy format
                    removed = True
                    continue
                new_following.append(entry)
                
            if removed:
                user_ref.update({
                    "following": new_following,
                    "following_count": firestore.Increment(-1) if user_collection == 'aiUsers' else len(new_following)
                })
                
                # Also update the followers list of the followed user
                following_doc = following_ref.get()
                if following_doc.exists:
                    following_data = following_doc.to_dict()
                    current_followers = following_data.get("followers", [])
                    new_followers = []
                    
                    for entry in current_followers:
                        if isinstance(entry, dict) and entry.get("id") == user_id and entry.get("type") == user_type:
                            continue
                        elif entry == user_id:  # Handle legacy format
                            continue
                        new_followers.append(entry)
                        
                    following_ref.update({
                        "followers": new_followers,
                        "followers_count": firestore.Increment(-1) if following_collection == 'aiUsers' else len(new_followers)
                    })
            
            return jsonify({"success": True, "message": "User successfully removed from your following list."}), 200
        except Exception as ex:
            logger.error("Error removing from following: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    @staticmethod
    def remove_from_followers(data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            
            user_id = data.get("UserId")  # A (authenticated user)
            follower_id = data.get("FollowerId")  # B (user to remove as follower)
            user_type = data.get("UserType", "human")  # "human" or "ai"
            follower_type = data.get("FollowerType", "human")  # "human" or "ai"

            logger.info(f"User {user_id} ({user_type}) is removing follower {follower_id} ({follower_type}).")

            # Determine the correct collections based on user types
            user_collection = 'aiUsers' if user_type == 'ai' else 'humanUsers'
            follower_collection = 'aiUsers' if follower_type == 'ai' else 'humanUsers'
            
            # For AI users, the document ID is the username
            user_doc_id = user_id
            follower_doc_id = follower_id

            user_ref = db.collection(user_collection).document(user_doc_id)
            follower_ref = db.collection(follower_collection).document(follower_doc_id)
            
            # Get current followers list
            user_doc = user_ref.get()
            if not user_doc.exists:
                return jsonify({"success": False, "error": "User not found"}), 404
                
            user_data = user_doc.to_dict()
            current_followers = user_data.get("followers", [])
            new_followers = []
            removed = False
            
            for entry in current_followers:
                if isinstance(entry, dict) and entry.get("id") == follower_id and entry.get("type") == follower_type:
                    removed = True
                    continue
                elif entry == follower_id:  # Handle legacy format
                    removed = True
                    continue
                new_followers.append(entry)
                
            if removed:
                user_ref.update({
                    "followers": new_followers,
                    "followers_count": firestore.Increment(-1) if user_collection == 'aiUsers' else len(new_followers)
                })
                
                # Also update the following list of the follower
                follower_doc = follower_ref.get()
                if follower_doc.exists:
                    follower_data = follower_doc.to_dict()
                    current_following = follower_data.get("following", [])
                    new_following = []
                    
                    for entry in current_following:
                        if isinstance(entry, dict) and entry.get("id") == user_id and entry.get("type") == user_type:
                            continue
                        elif entry == user_id:  # Handle legacy format
                            continue
                        new_following.append(entry)
                        
                    follower_ref.update({
                        "following": new_following,
                        "following_count": firestore.Increment(-1) if follower_collection == 'aiUsers' else len(new_following)
                    })
            
            return jsonify({"success": True, "message": "User successfully removed from your followers list."}), 200
        except Exception as ex:
            logger.error("Error removing from followers: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    @staticmethod
    def send_feedback(data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            
            email = data.get("email")
            feedback_text = data.get("Feedback")

            feedback_data = {
                "email": email,
                "feedback": feedback_text,
                "timestamp": firestore.SERVER_TIMESTAMP
            }

            db.collection('feedbacks').add(feedback_data)

            return jsonify({"success": True}), 200
        except Exception as ex:
            logger.error("Error submitting feedback: %s", ex)
            return jsonify({"success": False, "error": "Failed to submit feedback", "code": "FEEDBACK_ERROR"}), 500
    @staticmethod
    def like_post(data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            
            user_id = data.get("UserId")
            post_id = data.get("PostId")

            if not user_id or not post_id:
                return jsonify({"success": False, "error": "UserId and PostId are required"}), 400

            actor_ref, actor_doc, actor_type, actor_username = ProfileService._resolve_actor_identity(user_id)
            if actor_ref is None or actor_doc is None:
                return jsonify({"success": False, "error": "User not found"}), 404
            if not actor_username:
                return jsonify({"success": False, "error": "User username is missing"}), 400

            actor_id = str(getattr(actor_ref, 'id', '') or '').strip()
            request_user_id = str(user_id or '').strip()
            if not actor_id:
                return jsonify({"success": False, "error": "Resolved user id is missing"}), 400

            post_ref, post_data, post_collection = ProfileService._resolve_likeable_post(post_id)
            if post_ref is None or post_data is None or post_collection is None:
                return jsonify({"success": False, "error": "Post not found"}), 404

            post_author_id = (
                post_data.get('author_id')
                or post_data.get('user_document_id')
                or post_data.get('user_id')
            )

            like_data = {
                "user_id": actor_id,
                "post_id": post_id,
                "post_collection": post_collection,
                "timestamp": firestore.SERVER_TIMESTAMP
            }

            # Increment the like count in the post collection
            post_ref.update({
                "likes": firestore.Increment(1)
            })

            # Update the liked_posts field in humanUsers collection
            if actor_type == 'human':
                actor_ref.update({
                    "liked_posts": firestore.ArrayUnion([post_id])
                })

            # Trigger engagement notification if post author is different
            # if post_author_id and post_author_id != user_id:

            like_entry = {
                'id': actor_id,
                'username': actor_username,
                'type': actor_type
            }

            # Use transaction to add likedBy entry only if not already present
            did_add_like = False
            try:
                def _add_like_transaction(transaction, ref, entry, uid, legacy_uid):
                    snap = ref.get(transaction=transaction)
                    if not snap.exists:
                        transaction.set(ref, {'likedBy': [entry]}, merge=True)
                        return True
                    data = snap.to_dict() or {}
                    liked_by = list(data.get('likedBy', []))
                    exists = False
                    updated = False
                    match_ids = {str(uid), str(legacy_uid)}
                    for index, existing in enumerate(liked_by):
                        if isinstance(existing, dict) and str(existing.get('id') or '') in match_ids:
                            exists = True
                            normalized_existing = dict(existing)
                            if str(normalized_existing.get('id') or '').strip() != entry.get('id'):
                                normalized_existing['id'] = entry.get('id')
                                updated = True
                            if (normalized_existing.get('username') or '').strip() != entry.get('username'):
                                normalized_existing['username'] = entry.get('username')
                                updated = True
                            if (normalized_existing.get('type') or '').strip() != entry.get('type'):
                                normalized_existing['type'] = entry.get('type')
                                updated = True
                            if updated:
                                liked_by[index] = normalized_existing
                            break
                    if not exists:
                        liked_by.append(entry)
                        updated = True
                    if updated:
                        transaction.update(ref, {'likedBy': liked_by})
                    return not exists

                transaction = db.transaction()
                did_add_like = _add_like_transaction(transaction, post_ref, like_entry, actor_id, request_user_id)
            except Exception as e:
                # Fall back: try a simple update with arrayUnion (best-effort)
                try:
                    post_ref.update({'likedBy': firestore.ArrayUnion([like_entry])})
                    did_add_like = True
                except Exception:
                    logger.error(f"Error updating likedBy for post {post_id}: {e}")

            # Record interaction in Gorse
            if did_add_like:
                try:
                    gorse_client.record_interaction(actor_id, post_id, 'like')
                    print(f"💚 GORSE SYNC: Recorded like - user={actor_id[:15]}..., post={post_id[:15]}...")
                except Exception as e:
                    print(f"⚠️  Failed to record like in Gorse: {e}")
            
            # Trigger engagement notification if post author is different and like was actually added
            if did_add_like and post_author_id and post_author_id != actor_id:
                try:
                    import requests
                    notification_data = {
                        'postId': post_id,
                        'type': 'like',
                        'userId': actor_id,
                        'postAuthorId': post_author_id,
                        'timestamp': datetime.utcnow().isoformat()
                    }
                    requests.post('https://inzoneapi-912424781531.us-central1.run.app/api/notifications/events/post-engagement', json=notification_data)
                except Exception as notif_error:
                    logger.error(f"Error sending like notification: {notif_error}")

            return jsonify({"success": True}), 200
        except Exception as ex:
            logger.error("Error liking post: %s", ex)
            return jsonify({"success": False, "error": "Failed to like post", "code": "LIKE_POST_ERROR"}), 500

    @staticmethod
    def unlike_post(data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            
            user_id = data.get("UserId")
            post_id = data.get("PostId")

            if not user_id or not post_id:
                return jsonify({"success": False, "error": "UserId and PostId are required"}), 400

            actor_ref, actor_doc, actor_type, _ = ProfileService._resolve_actor_identity(user_id)
            if actor_ref is None or actor_doc is None:
                return jsonify({"success": False, "error": "User not found"}), 404

            actor_id = str(getattr(actor_ref, 'id', '') or '').strip()
            request_user_id = str(user_id or '').strip()
            if not actor_id:
                return jsonify({"success": False, "error": "Resolved user id is missing"}), 400

            post_ref, _, post_collection = ProfileService._resolve_likeable_post(post_id)
            if post_ref is None or post_collection is None:
                return jsonify({"success": False, "error": "Post not found"}), 404

            # Query to find the like relationship
            query = db.collection('postLikes').where('user_id', '==', actor_id).where('post_id', '==', post_id)
            snapshot = query.stream()

            # Remove the like relationship
            for doc in snapshot:
                doc.reference.delete()

            # Decrement the like count in the post collection
            try:
                post_ref.update({
                    "likes": firestore.Increment(-1)
                })
            except Exception:
                pass

            # Update the liked_posts field in humanUsers collection
            if actor_type == 'human':
                actor_ref.update({
                    "liked_posts": firestore.ArrayRemove([post_id])
                })

            # Remove from post's likedBy array (match by id)
            try:
                snap = post_ref.get()
                if snap.exists:
                    data = snap.to_dict() or {}
                    liked_by = list(data.get('likedBy', []))
                    match_ids = {actor_id, request_user_id}
                    updated = [
                        e for e in liked_by
                        if not (isinstance(e, dict) and str(e.get('id') or '') in match_ids)
                    ]
                    post_ref.update({'likedBy': updated})
            except Exception as e:
                logger.error(f"Error removing likedBy entry for post {post_id}: {e}")

            return jsonify({"success": True, "message": "Post unliked successfully."}), 200
        except Exception as ex:
            logger.error("Error unliking post: %s", ex)
            return jsonify({"success": False, "error": "Failed to unlike post", "code": "UNLIKE_POST_ERROR"}), 500
    @staticmethod
    def get_liked_posts(data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            
            user_id = data.get("UserId")

            # Retrieve the liked posts from the user's profile
            user_ref = db.collection('humanUsers').document(user_id).get()
            if user_ref.exists:
                liked_posts = user_ref.to_dict().get("liked_posts", [])
            else:
                liked_posts = []

            # Fetch the post details for each liked post ID
            liked_posts_details = []
            for post_id in liked_posts:
                post_ref = db.collection('humanPosts').document(post_id).get()
                if post_ref.exists:
                    liked_posts_details.append(post_ref.to_dict())

            return jsonify({"success": True, "liked_posts": liked_posts_details}), 200
        except Exception as ex:
            logger.error("Error retrieving liked posts: %s", ex)
            return jsonify({"success": False, "error": "Failed to retrieve liked posts", "code": "GET_LIKED_POSTS_ERROR"}), 500
    @staticmethod
    def generate_referral_code(data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            
            user_id = data.get("UserDocumentId")
            if not user_id:
                return jsonify({"success": False, "error": "User ID is required"}), 400

            referral_code = f"INZONE-{uuid.uuid4().hex[:6].upper()}"

            # Update user profile with referral code
            user_ref = db.collection('humanUsers').document(user_id)
            user_ref.update({
                "referral_code": referral_code,
                "referral_count": 0,
                "total_referral_earnings": 0
            })

            return jsonify({
                "success": True,
                "data": {
                    "referral_code": referral_code,
                    "referral_link": f"https://inzone.ai/referral?code={referral_code}"
                }
            }), 200
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
    @staticmethod
    def apply_referral(data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            
            referral_code = data.get("ReferralCode")
            new_user_id = data.get("UserDocumentId")

            if not referral_code or not new_user_id:
                return jsonify({"success": False, "error": "Referral code and user ID are required"}), 400

            # Find referrer by referral code
            referrer_query = db.collection('humanUsers').where("referral_code", "==", referral_code).limit(1).get()
            if not referrer_query:
                return jsonify({"success": False, "error": "Invalid referral code"}), 404

            referrer_doc = referrer_query[0]
            referrer_id = referrer_doc.id

            # Check if user has already used a referral code
            new_user_ref = db.collection('humanUsers').document(new_user_id)
            new_user_doc = new_user_ref.get()
            if new_user_doc.exists and new_user_doc.to_dict().get("used_referral_code"):
                return jsonify({"success": False, "error": "User has already used a referral code"}), 400

            # Create referral record
            referral_data = {
                "referrer_id": referrer_id,
                "referee_id": new_user_id,
                "referral_code": referral_code,
                "status": "completed",
                "date_created": firestore.SERVER_TIMESTAMP,
                "rewards_granted": False
            }
            db.collection('referrals').add(referral_data)

            # Update new user's profile
            new_user_ref.update({
                "used_referral_code": referral_code,
                "referrer_id": referrer_id
            })

            # Update referrer's stats
            db.collection('humanUsers').document(referrer_id).update({
                "referral_count": firestore.Increment(1)
            })

            # Grant InCash rewards
            grant_referral_rewards(referrer_id, new_user_id)

            return jsonify({"success": True, "message": "Referral applied successfully"}), 200
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
    @staticmethod
    def grant_referral_rewards(referrer_id, referee_id):
        """Grant InCash rewards to both referrer and referee"""
        try:
            referrer_reward = 1500  # 10$ worth of InCash
            referee_reward = 1500   # 10$ worth of InCash

            # Grant reward to referrer
            db.collection('humanUsers').document(referrer_id).update({
                "balance": firestore.Increment(referrer_reward),
                "total_referral_earnings": firestore.Increment(referrer_reward)
            })

            # Grant reward to new user
            db.collection('humanUsers').document(referee_id).update({
                "balance": firestore.Increment(referee_reward)
            })

            # Record rewards
            reward_data = {
                "referrer_id": referrer_id,
                "referee_id": referee_id,
                "referrer_reward": referrer_reward,
                "referee_reward": referee_reward,
                "date_granted": firestore.SERVER_TIMESTAMP
            }
            db.collection('referral_rewards').add(reward_data)
        except Exception as e:
            logger.error(f"Error granting referral rewards: {e}")
            raise e
    @staticmethod
    def get_referral_stats(data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            user_id = request.args.get('UserDocumentId')
            if not user_id:
                return jsonify({"success": False, "error": "User ID is required"}), 400

            user_doc = db.collection('humanUsers').document(user_id).get()
            if not user_doc.exists:
                return jsonify({"success": False, "error": "User not found"}), 404

            user_data = user_doc.to_dict()

            # Get referral history
            referrals = db.collection('referrals').where("referrer_id", "==", user_id).get()
            referral_history = [{
                "referee_id": ref.get("referee_id"),
                "date": ref.get("date_created"),
                "status": ref.get("status")
            } for ref in referrals]

            return jsonify({
                "success": True,
                "data": {
                    "referral_code": user_data.get("referral_code"),
                    "referral_link": f"https://inzone.ai/referral?code={user_data.get('referral_code')}",
                    "referral_count": user_data.get("referral_count", 0),
                    "total_earnings": user_data.get("total_referral_earnings", 0),
                    "referral_history": referral_history
                }
            }), 200
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
