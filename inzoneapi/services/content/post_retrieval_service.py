# services/content/post_retrieval_service.py
from typing import List, Dict, Any
from dependencies import db


class PostRetrievalService:
    """Service for retrieving posts from Firestore"""

    @staticmethod
    def get_post_by_id(post_id: str) -> Dict[str, Any]:
        """
        Helper function to fetch a post from Firestore by ID
        Tries humanPosts, aiPosts, and reposts collections
        """
        try:
            # Try humanPosts first
            post_doc = db.collection('humanPosts').document(post_id).get()
            if post_doc.exists:
                post_data = post_doc.to_dict()
                # Skip deleted posts
                if post_data.get('content') == '[This post has been deleted by the user]':
                    return None
                post_data['id'] = post_id  # Add document ID to the dict
                return post_data

            # Try aiPosts
            post_doc = db.collection('aiPosts').document(post_id).get()
            if post_doc.exists:
                post_data = post_doc.to_dict()
                post_data['id'] = post_id  # Add document ID to the dict
                post_data['is_ai'] = True  # Mark as AI post for Flutter identification

                # Enrich AI posts with user profile information using character_info
                # Flutter's PostCard checks character_info['image'] for profile pictures
                user_name = post_data.get('user_name')
                if user_name:
                    try:
                        # Try aiUsers collection first
                        ai_user_doc = db.collection('aiUsers').document(user_name).get()
                        profile_pic_url = None

                        if ai_user_doc.exists:
                            ai_user_data = ai_user_doc.to_dict()
                            # Check all possible field names for profile picture
                            profile_pic_url = (
                                ai_user_data.get('profile_picture_url') or
                                ai_user_data.get('profilePicture') or
                                ai_user_data.get('profile_picture')
                            )
                            print(f"✅ Found AI user '{user_name}' in aiUsers, profile_pic: {profile_pic_url[:50] if profile_pic_url else 'None'}...")
                        else:
                            # Try popularCharacters collection as fallback
                            char_doc = db.collection('popularCharacters').document(user_name).get()
                            if char_doc.exists:
                                char_data = char_doc.to_dict()
                                profile_pic_url = (
                                    char_data.get('profile_picture_url') or
                                    char_data.get('profilePicture') or
                                    char_data.get('profile_picture')
                                )
                                print(f"✅ Found AI user '{user_name}' in popularCharacters, profile_pic: {profile_pic_url[:50] if profile_pic_url else 'None'}...")

                        # Add to character_info so Flutter's PostCard can use it
                        if profile_pic_url and profile_pic_url != 'url_to_profile_picture':
                            post_data['character_info'] = {
                                'name': user_name,
                                'image': profile_pic_url
                            }
                            print(f"✅ Enriched AI post {post_id} with character_info for {user_name}")
                        else:
                            print(f"⚠️  No valid profile picture URL for AI user '{user_name}' (value: {profile_pic_url})")

                    except Exception as e:
                        print(f"⚠️  Error enriching AI post {post_id}: {e}")
                else:
                    print(f"⚠️  AI post {post_id} missing user_name field")

                return post_data

            # Try reposts
            post_doc = db.collection('reposts').document(post_id).get()
            if post_doc.exists:
                post_data = post_doc.to_dict()
                # Skip deleted posts
                if post_data.get('content') == '[This post has been deleted by the user]':
                    return None
                post_data['id'] = post_id  # Add document ID to the dict
                return post_data

            return None
        except Exception as e:
            print(f"Error fetching post {post_id}: {e}")
            return None

    @staticmethod
    def get_post_by_id_cached(post_id: str, ai_user_cache: dict) -> Dict[str, Any]:
        """
        Optimized version of get_post_by_id that uses a cache for AI user profiles.
        This significantly speeds up batch post fetching by avoiding repeated Firestore queries.
        """
        try:
            # Try humanPosts first
            post_doc = db.collection('humanPosts').document(post_id).get()
            if post_doc.exists:
                post_data = post_doc.to_dict()
                # Skip deleted posts
                if post_data.get('content') == '[This post has been deleted by the user]':
                    return None
                post_data['id'] = post_id
                return post_data

            # Try aiPosts with cached profile enrichment
            post_doc = db.collection('aiPosts').document(post_id).get()
            if post_doc.exists:
                post_data = post_doc.to_dict()
                post_data['id'] = post_id
                post_data['is_ai'] = True

                # Enrich AI posts with cached user profile information
                user_name = post_data.get('user_name')
                if user_name:
                    # Check cache first
                    if user_name in ai_user_cache:
                        profile_pic_url = ai_user_cache[user_name]
                    else:
                        # Not in cache, fetch from Firestore and cache it
                        profile_pic_url = None
                        try:
                            ai_user_doc = db.collection('aiUsers').document(user_name).get()
                            if ai_user_doc.exists:
                                ai_user_data = ai_user_doc.to_dict()
                                profile_pic_url = (
                                    ai_user_data.get('profile_picture_url') or
                                    ai_user_data.get('profilePicture') or
                                    ai_user_data.get('profile_picture')
                                )
                            else:
                                # Try popularCharacters as fallback
                                char_doc = db.collection('popularCharacters').document(user_name).get()
                                if char_doc.exists:
                                    char_data = char_doc.to_dict()
                                    profile_pic_url = (
                                        char_data.get('profile_picture_url') or
                                        char_data.get('profilePicture') or
                                        char_data.get('profile_picture')
                                    )
                        except Exception as e:
                            profile_pic_url = None

                        # Cache the result (even if None, to avoid repeated failed lookups)
                        ai_user_cache[user_name] = profile_pic_url

                    # Add to character_info if we have a valid URL
                    if profile_pic_url and profile_pic_url != 'url_to_profile_picture':
                        post_data['character_info'] = {
                            'name': user_name,
                            'image': profile_pic_url
                        }

                return post_data

            # Try reposts
            post_doc = db.collection('reposts').document(post_id).get()
            if post_doc.exists:
                post_data = post_doc.to_dict()
                # Skip deleted posts
                if post_data.get('content') == '[This post has been deleted by the user]':
                    return None
                post_data['id'] = post_id
                return post_data

            return None
        except Exception as e:
            print(f"Error fetching post {post_id}: {e}")
            return None

    @staticmethod
    def get_posts_by_ids(post_ids: List[str]) -> List[Dict[str, Any]]:
        """Fetch multiple posts from Firestore by their IDs with optimized AI user profile caching"""
        posts = []
        ai_user_cache = {}  # Cache AI user profiles to avoid repeated Firestore queries

        for post_id in post_ids:
            post_data = PostRetrievalService.get_post_by_id_cached(post_id, ai_user_cache)
            if post_data:
                posts.append(post_data)

        return posts
