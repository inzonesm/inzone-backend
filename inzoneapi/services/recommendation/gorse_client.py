from typing import List
import requests
from datetime import datetime, timezone
from config import Config
from config.feed_config import feed_config
from dependencies import db
from firebase_admin import firestore

class GorseClient:
    """Client for Gorse Recommendation System"""
    
    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            'Content-Type': 'application/json'
        }
        if self.api_key:
            self.headers['X-API-Key'] = self.api_key
        
        # Enable if URL is set and not localhost
        self.enabled = bool(api_url and api_url != 'http://localhost:8087')
        if self.enabled:
            print(f"✓ Gorse client initialized: {self.api_url}")
            if not api_key:
                print("  ⚠ No API key set (may not be required)")
        else:
            print("⚠ Gorse client disabled (no valid URL or using localhost)")
        
        # BATCH CACHE: Store generated recommendations for each (user_id, batch_number) pair
        # This ensures same batch always returns same posts, fixing scroll duplication
        self.batch_cache = {}  # Key: f"{user_id}:{batch_number}" -> Value: list of post IDs
        self.cache_max_size = 100  # Prevent unbounded growth
    
    def get_recommendations(self, user_id: str, limit: int = 20, offset: int = 0) -> List[str]:
        """Get personalized post recommendations for a user"""
        if not self.enabled:
            return []
        
        try:
            # 🎯 REMOVED write-back-type to prevent automatic marking
            # We'll manually mark posts as 'read' only after user actually views them
            response = requests.get(
                f'{self.api_url}/api/recommend/{user_id}',
                headers=self.headers,
                params={
                    'n': limit, 
                    'offset': offset
                    # No write-back to avoid premature marking
                },
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                # Gorse returns a list of strings (item IDs directly)
                if isinstance(data, list):
                    if data and isinstance(data[0], str):
                        return data  # List of post IDs
                    elif data and isinstance(data[0], dict):
                        return [item.get('Id', item.get('ItemId', '')) for item in data]
                return []
            else:
                print(f"Gorse API error: {response.status_code}")
                return []
        except Exception as e:
            print(f"Error getting recommendations: {e}")
            return []
    
    def record_interaction(self, user_id: str, post_id: str, feedback_type: str):
        """
        Record user interaction (read, like, comment, share) to both Gorse and Firestore

        DUAL-WRITE STRATEGY:
        1. Firestore: Permanent backup, queryable, restorable
        2. Gorse: Real-time recommendations
        """
        timestamp = datetime.now(timezone.utc)
        iso_timestamp = timestamp.isoformat()

        # STEP 1: FIRESTORE BACKUP (Primary data store)
        try:
            feedback_doc = {
                'userId': user_id,
                'postId': post_id,
                'feedbackType': feedback_type,  # 'read', 'like', 'comment', 'share'
                'timestamp': timestamp,
                'isoTimestamp': iso_timestamp
            }

            # Store in Firestore: userFeedback/{userId}/interactions/{auto_id}
            db.collection('userFeedback').document(user_id).collection('interactions').add(feedback_doc)

            # Also update user's interaction summary for quick analytics
            summary_ref = db.collection('userFeedback').document(user_id)
            summary_ref.set({
                'userId': user_id,
                'lastInteraction': timestamp,
                f'{feedback_type}Count': firestore.Increment(1)
            }, merge=True)

            print(f"[Backup] ✅ Saved {feedback_type} to Firestore: user={user_id[:10]}..., post={post_id[:10]}...")

        except Exception as e:
            print(f"[Backup] ⚠️ Error saving feedback to Firestore: {e}")
            # Continue anyway - Gorse should still work

        # STEP 2: GORSE (Recommendation engine)
        if not self.enabled:
            return

        try:
            # Gorse expects an array of feedback items
            feedback_list = [{
                'FeedbackType': feedback_type,
                'UserId': user_id,
                'ItemId': post_id,
                'Timestamp': iso_timestamp
            }]
            requests.put(
                f'{self.api_url}/api/feedback',
                headers=self.headers,
                json=feedback_list,
                timeout=5
            )
        except Exception as e:
            print(f"[Gorse] ⚠️ Error recording interaction: {e}")
    
    def get_similar_posts(self, post_id: str, limit: int = 5) -> List[str]:
        """Get similar posts based on a post ID"""
        if not self.enabled:
            return []
        
        try:
            response = requests.get(
                f'{self.api_url}/api/item/{post_id}/neighbors',
                headers=self.headers,
                params={'n': limit},
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                # Handle list of strings or list of dicts
                if isinstance(data, list):
                    if data and isinstance(data[0], str):
                        return data
                    elif data and isinstance(data[0], dict):
                        return [item.get('Id', item.get('ItemId', '')) for item in data]
                return []
            return []
        except Exception as e:
            print(f"Error getting similar posts: {e}")
            return []
    
    def get_popular_posts(self, limit: int = 10) -> List[str]:
        """Get trending/popular posts"""
        if not self.enabled:
            return []

        try:
            response = requests.get(
                f'{self.api_url}/api/popular',
                headers=self.headers,
                params={'n': limit},
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                # Handle list of strings or list of dicts
                if isinstance(data, list):
                    if data and isinstance(data[0], str):
                        return data
                    elif data and isinstance(data[0], dict):
                        return [item.get('Id', item.get('ItemId', '')) for item in data]
                return []
            return []
        except Exception as e:
            print(f"Error getting popular posts: {e}")
            return []

    def get_user_viewed_posts(self, user_id: str, feedback_type: str = 'read') -> List[str]:
        """
        Get list of posts that user has already viewed/read from Firestore backup

        Args:
            user_id: User ID to get feedback for
            feedback_type: Type of feedback to filter (default: 'read')

        Returns:
            List of item IDs that the user has viewed
        """
        try:
            # Query Firestore backup instead of Gorse
            interactions_ref = db.collection('userFeedback').document(user_id).collection('interactions')

            # Filter by feedback type (e.g., 'read' for views)
            interactions = interactions_ref.where('feedbackType', '==', feedback_type).stream()

            # Extract post IDs
            viewed_posts = []
            for interaction in interactions:
                data = interaction.to_dict()
                post_id = data.get('postId')
                if post_id:
                    viewed_posts.append(post_id)

            # Show sample of viewed posts for debugging
            sample = viewed_posts[:5] if len(viewed_posts) > 5 else viewed_posts
            print(f"[SmartRecs] User {user_id[:15]}... has viewed {len(viewed_posts)} posts (sample: {[p[:8]+'...' for p in sample]})")
            return viewed_posts

        except Exception as e:
            print(f"[SmartRecs] Error getting viewed posts from Firestore for user {user_id}: {e}")
            return []

    def insert_user(self, user_id: str, labels: List[str] = None):
        """Insert or update a user in Gorse"""
        if not self.enabled:
            return False
        
        try:
            user_data = {
                'UserId': user_id,
                'Labels': labels or []
            }
            response = requests.patch(
                f'{self.api_url}/api/user/{user_id}',
                headers=self.headers,
                json=user_data,
                timeout=5
            )
            return response.status_code in [200, 201]
        except Exception as e:
            print(f"Error inserting user to Gorse: {e}")
            return False
    
    def insert_item(self, item_id: str, labels: List[str] = None, comment: str = None, timestamp: str = None):
        """Insert or update an item (post) in Gorse"""
        if not self.enabled:
            return False
        
        try:
            item_data = {
                'ItemId': item_id,
                'Labels': labels or [],
                'Comment': comment or '',
                'Timestamp': timestamp or datetime.now(timezone.utc).isoformat()
            }
            # Use POST to insert new items
            response = requests.post(
                f'{self.api_url}/api/item',
                headers=self.headers,
                json=item_data,
                timeout=5
            )
            return response.status_code in [200, 201]
        except Exception as e:
            print(f"Error inserting item to Gorse: {e}")
            return False
    
    def refresh_user_recommendations(self, user_id: str):
        """Clear cached recommendations for a specific user"""
        if not self.enabled:
            return False
        
        # Actually, there's no direct API to clear cache in Gorse
        # The cache will automatically expire based on cache_expire setting
        # The best we can do is ensure the user data is updated (which we already did)
        # and let Gorse handle the cache expiration naturally
        
        print(f"ℹ️  User {user_id} recommendations will refresh after cache expires (cache_expire in config)")
        print(f"   Note: Gorse doesn't provide an API to manually clear individual user cache")
        print(f"   The updated interests are already in Gorse - fresh recommendations will be generated when cache expires")
        return True
    
    def delete_item(self, item_id: str):
        """Delete an item (post) from Gorse"""
        if not self.enabled:
            return False

        try:
            response = requests.delete(
                f'{self.api_url}/api/item/{item_id}',
                headers=self.headers,
                timeout=5
            )
            return response.status_code in [200, 204]
        except Exception as e:
            print(f"Error deleting item from Gorse: {e}")
            return False

    def get_items_by_label_firestore(self, label: str, n: int = 100, user_id: str = None) -> List[str]:
        """
        Get posts with a specific masterCategory directly from Firestore (no Gorse dependency)

        Args:
            label: The category label to filter by
            n: Maximum number of items to return
            user_id: User ID for consistent per-user shuffle (optional)

        Returns:
            List of post IDs with the specified label (shuffled for variety)
        """
        try:
            import random
            import hashlib
            from datetime import date
            
            post_ids = []

            # Fetch MUCH MORE than needed for maximum variety after shuffling
            # For n=150 (from 30 * 5), fetch_limit will be min(750, 1000) = 750 posts
            fetch_limit = min(n * 5, 1000)  # Fetch 5x what we need, max 1000 (increased from 500)

            # Query humanPosts with this category, ordered by timestamp
            # This requires a composite index: (masterCategories, date_posted DESC)
            # Create it in Firebase Console when prompted
            try:
                human_posts = db.collection('humanPosts')\
                    .where('masterCategories', 'array_contains', label)\
                    .order_by('date_posted', direction=firestore.Query.DESCENDING)\
                    .limit(fetch_limit // 2)\
                    .stream()

                for post in human_posts:
                    post_ids.append(post.id)
            except Exception as e:
                # Fallback if index doesn't exist yet
                print(f"[Firestore] Index may be needed for humanPosts ordering: {e}")
                print(f"[Firestore] Falling back to unordered query...")
                human_posts = db.collection('humanPosts')\
                    .where('masterCategories', 'array_contains', label)\
                    .limit(fetch_limit // 2)\
                    .stream()

                for post in human_posts:
                    post_ids.append(post.id)

            # Query aiPosts with this category, ordered by timestamp
            try:
                ai_posts = db.collection('aiPosts')\
                    .where('masterCategories', 'array_contains', label)\
                    .order_by('date_posted', direction=firestore.Query.DESCENDING)\
                    .limit(fetch_limit // 2)\
                    .stream()

                for post in ai_posts:
                    post_ids.append(post.id)
            except Exception as e:
                # Fallback if index doesn't exist yet
                print(f"[Firestore] Index may be needed for aiPosts ordering: {e}")
                print(f"[Firestore] Falling back to unordered query...")
                ai_posts = db.collection('aiPosts')\
                    .where('masterCategories', 'array_contains', label)\
                    .limit(fetch_limit // 2)\
                    .stream()

                for post in ai_posts:
                    post_ids.append(post.id)

            # Shuffle with deterministic seed based on user_id + current date
            # Same user gets same shuffle order on the same day (consistency)
            # But different order each day (freshness)
            if user_id:
                today = date.today().isoformat()
                seed_string = f"{user_id}_{label}_{today}"
                seed = int(hashlib.md5(seed_string.encode()).hexdigest(), 16) % (2**32)
                random.seed(seed)
            
            random.shuffle(post_ids)
            random.seed()  # Reset to random seed for other operations

            print(f"[Firestore] Found {len(post_ids)} posts for label '{label}' (shuffled, {fetch_limit} limit)")
            return post_ids[:n]

        except Exception as e:
            print(f"[Firestore] Error getting posts by label '{label}': {e}")
            return []

    def get_diverse_posts_firestore(self, n: int = 100, user_id: str = None) -> List[str]:
        """
        Get diverse recent posts from ALL categories for exploration

        This fetches posts without category filtering to provide discovery/exploration.
        Posts are ordered by recency to ensure fresh content, then shuffled for variety.

        Args:
            n: Maximum number of items to return
            user_id: User ID for consistent per-user shuffle (optional)

        Returns:
            List of post IDs from diverse categories (shuffled)
        """
        try:
            import random
            import hashlib
            from datetime import date
            
            post_ids = []

            # Fetch MORE than needed for variety after shuffling
            fetch_limit = min(n * 5, 1000)  # Match the fetch strategy of category posts

            # Get recent humanPosts ordered by date (no category filter)
            human_posts = db.collection('humanPosts')\
                .order_by('date_posted', direction=firestore.Query.DESCENDING)\
                .limit(fetch_limit // 2)\
                .stream()

            for post in human_posts:
                post_ids.append(post.id)

            # Get recent aiPosts ordered by date (no category filter)
            ai_posts = db.collection('aiPosts')\
                .order_by('date_posted', direction=firestore.Query.DESCENDING)\
                .limit(fetch_limit // 2)\
                .stream()

            for post in ai_posts:
                post_ids.append(post.id)

            # Deterministic shuffle based on user_id + current date
            if user_id:
                today = date.today().isoformat()
                seed_string = f"{user_id}_diverse_{today}"
                seed = int(hashlib.md5(seed_string.encode()).hexdigest(), 16) % (2**32)
                random.seed(seed)
            
            random.shuffle(post_ids)
            random.seed()  # Reset to random seed

            print(f"[Firestore] Found {len(post_ids)} diverse exploration posts (shuffled)")
            return post_ids[:n]

        except Exception as e:
            print(f"[Firestore] Error getting diverse posts: {e}")
            return []

    def get_items_by_label(self, label: str, n: int = 100) -> List[str]:
        """
        Get all items with a specific label by paginating through the items API

        Args:
            label: The category label to filter by
            n: Maximum number of items to return

        Returns:
            List of item IDs with the specified label
        """
        if not self.enabled:
            return []

        items = []
        cursor = ""
        page_size = 100
        max_pages = 10  # Prevent infinite loops
        pages_fetched = 0

        while len(items) < n and pages_fetched < max_pages:
            url = f'{self.api_url}/api/items?n={page_size}'
            if cursor:
                url += f'&cursor={cursor}'

            try:
                response = requests.get(url, headers=self.headers, timeout=5)
                if response.status_code != 200:
                    break

                data = response.json()
                if not data:
                    break

                # Handle different response formats
                items_list = data.get('Items', []) if isinstance(data, dict) else []

                # Filter items by label
                for item in items_list:
                    if label in item.get('Labels', []):
                        items.append(item['ItemId'])

                cursor = data.get('Cursor', '') if isinstance(data, dict) else ''
                if not cursor:
                    break

                pages_fetched += 1

            except Exception as e:
                print(f"Error fetching items by label: {e}")
                break

        return items[:n]

    def get_smart_recommendations(self,
                                 user_id: str,
                                 user_labels: List[str],
                                 n: int = 10,
                                 target_match_rate: float = 0.7,
                                 shuffle: bool = True) -> List[str]:
        """
        Get smart category-based recommendations for a user with high category match rate

        This method achieves 70%+ match rate by filtering items by user's category labels,
        then blending with diverse recommendations from Gorse's general algorithm.

        Args:
            user_id: User ID to get recommendations for
            user_labels: List of category labels the user is interested in
            n: Total number of recommendations to return
            target_match_rate: Target percentage of recommendations from user's categories (0.0-1.0)
            shuffle: Whether to shuffle the category-based recommendations

        Returns:
            List of recommended item IDs
        """
        if not self.enabled:
            return []

        recommendations = []
        n_category = int(n * target_match_rate)

        # Collect items from user's interest categories
        category_items = []
        items_per_category = max(20, n_category * 2)  # Get extra for diversity

        for label in user_labels:
            items = self.get_items_by_label(label, n=items_per_category)
            category_items.extend(items)

        # Remove duplicates
        category_items = list(set(category_items))

        # Shuffle for variety (optional)
        if shuffle:
            import random
            random.shuffle(category_items)

        # Take required number from categories
        recommendations.extend(category_items[:n_category])

        # Fill remaining slots with general/diverse recommendations
        if len(recommendations) < n:
            remaining = n - len(recommendations)
            try:
                # Get general recommendations from Gorse
                url = f'{self.api_url}/api/recommend/{user_id}?n={remaining + 10}'
                response = requests.get(url, headers=self.headers, timeout=5)

                if response.status_code == 200:
                    general_recs = response.json()
                    # Filter out duplicates
                    for rec in general_recs:
                        if rec not in recommendations and len(recommendations) < n:
                            recommendations.append(rec)
            except Exception as e:
                print(f"Error getting general recommendations: {e}")

        # If still short, pad with remaining category items
        if len(recommendations) < n:
            for item in category_items[n_category:]:
                if item not in recommendations:
                    recommendations.append(item)
                if len(recommendations) >= n:
                    break

        return recommendations[:n]

    def get_smart_recommendations_with_ranking(self,
                                               user_id: str,
                                               user_labels: List[str],
                                               n: int = 10,
                                               target_match_rate: float = 0.7,
                                               recency_weight: float = 0.5,
                                               popularity_weight: float = 0.3,
                                               batch_number: int = 0,
                                               exclude_ids: List[str] = None) -> List[str]:
        """
        Get smart category-based recommendations with recency and popularity ranking

        This enhanced version:
        1. Filters items by user's category labels
        2. Scores each item by recency (newer = higher score)
        3. Scores each item by popularity (likes + comments)
        4. Combines scores and ranks items
        5. Blends top-ranked items with diverse recommendations

        Args:
            user_id: User ID to get recommendations for
            user_labels: List of category labels the user is interested in
            n: Total number of recommendations to return
            target_match_rate: Target percentage from user's categories (0.0-1.0)
            recency_weight: Weight for recency score (0.0-1.0, default 0.5)
            popularity_weight: Weight for popularity score (0.0-1.0, default 0.3)

        Returns:
            List of recommended item IDs, ranked by combined score
        """
        # NOTE: This method is Firestore-only and does NOT require Gorse to be enabled
        # It works independently for cold start recommendations

        import math
        from datetime import datetime, timezone, timedelta

        # BATCH CACHE: DISABLED - Always filter viewed posts on every request
        # This ensures users never see already-viewed posts in their feed
        cache_key = f"{user_id}:{batch_number}"

        # CACHE DISABLED - Always generate fresh recommendations
        # if cache_key in self.batch_cache:
        #     cached_recommendations = self.batch_cache[cache_key]
        #     print(f"[SmartRecs] 🎯 CACHE HIT! Returning cached batch {batch_number} ({len(cached_recommendations)} posts)")
        #     return cached_recommendations

        print(f"[SmartRecs] 🆕 Generating batch {batch_number} with fresh filtering")

        recommendations = []

        # Get user's viewed posts to filter them out
        viewed_posts = self.get_user_viewed_posts(user_id, feedback_type='read')
        viewed_posts_set = set(viewed_posts)

        # Also exclude posts already loaded in client (prevents race conditions)
        if exclude_ids is None:
            exclude_ids = []
        exclude_set = set(exclude_ids)

        # Combine both sets for comprehensive filtering
        all_excluded = viewed_posts_set | exclude_set

        if exclude_set:
            print(f"[SmartRecs] 🚫 Excluding {len(exclude_set)} client-loaded posts + {len(viewed_posts_set)} Firestore-viewed posts = {len(all_excluded)} total excluded")

        # Collect items from user's interest categories (100% category-based)
        category_items = []
        items_per_category = max(200, n * 5)  # Fetch MUCH more for variety (5x instead of 3x)

        print(f"[SmartRecs] 🔍 User {user_id[:15]}... has viewed {len(viewed_posts)} posts total")
        print(f"[SmartRecs] 🎯 Fetching items for {len(user_labels)} labels: {user_labels[:3]}...")
        for label in user_labels:
            items = self.get_items_by_label_firestore(label, n=items_per_category, user_id=user_id)
            category_items.extend(items)

        # Remove duplicates
        category_items = list(set(category_items))
        print(f"[SmartRecs] 📦 Found {len(category_items)} unique category items (before filtering viewed)")

        # Filter out already viewed posts AND client-loaded posts
        category_items_before = len(category_items)
        category_items = [item_id for item_id in category_items if item_id not in all_excluded]
        filtered_out = category_items_before - len(category_items)
        print(f"[SmartRecs] ✂️  Filtered out {filtered_out} excluded posts (viewed + client-loaded)")
        print(f"[SmartRecs] ✅ {len(category_items)} fresh posts remaining for recommendations")

        # If we don't have enough posts from user's categories, fetch random posts from ANY category
        if len(category_items) < n:
            needed = n - len(category_items)
            print(f"[SmartRecs] Not enough category posts ({len(category_items)}/{n}), fetching {needed} random posts from any category...")
            
            # Fetch diverse posts (no category filter)
            random_items = self.get_diverse_posts_firestore(n=needed * 3, user_id=user_id)  # Fetch 3x for filtering
            
            # Remove duplicates and already excluded (viewed + client-loaded)
            random_items = [item_id for item_id in random_items if item_id not in all_excluded and item_id not in category_items]
            
            if random_items:
                category_items.extend(random_items[:needed])  # Add only what we need
                print(f"[SmartRecs] Added {len(random_items[:needed])} random posts, total now: {len(category_items)}")
            else:
                print(f"[SmartRecs] No random posts available after filtering")

        # Score each item by recency and popularity
        # OPTIMIZATION: Batch fetch posts to reduce Firestore queries
        scored_items = []
        
        print(f"[SmartRecs] Batch fetching {len(category_items)} posts...")
        
        # Batch fetch all posts (up to 500 at a time due to Firestore limits)
        posts_data = {}
        batch_size = 500
        
        for i in range(0, len(category_items), batch_size):
            batch_items = category_items[i:i+batch_size]
            
            # Try humanPosts first in parallel
            human_refs = [db.collection('humanPosts').document(item_id) for item_id in batch_items]
            human_docs = db.get_all(human_refs)
            
            for doc in human_docs:
                if doc.exists:
                    posts_data[doc.id] = (doc.to_dict(), True)  # True = is_human_post
            
            # For items not found in humanPosts, try aiPosts
            missing_items = [item_id for item_id in batch_items if item_id not in posts_data]
            if missing_items:
                ai_refs = [db.collection('aiPosts').document(item_id) for item_id in missing_items]
                ai_docs = db.get_all(ai_refs)
                
                for doc in ai_docs:
                    if doc.exists:
                        posts_data[doc.id] = (doc.to_dict(), False)  # False = is_ai_post
        
        print(f"[SmartRecs] Fetched {len(posts_data)} posts, now scoring...")

        for item_id in category_items:
            try:
                if item_id not in posts_data:
                    continue
                
                post_data, is_human_post = posts_data[item_id]

                # Calculate Recency Score (exponential decay)
                post_date = post_data.get('date_posted')
                recency_score = 0.5  # Default

                if post_date:
                    try:
                        # Handle Firestore timestamp
                        if hasattr(post_date, 'timestamp'):
                            post_datetime = datetime.fromtimestamp(post_date.timestamp(), tz=timezone.utc)
                        else:
                            post_datetime = post_date

                        days_old = (datetime.now(timezone.utc) - post_datetime).days

                        # Exponential decay: e^(-days_old * decay_rate)
                        # Half-life of ~7 days with recency_weight=0.5
                        decay_rate = recency_weight / 7.0
                        recency_score = math.exp(-days_old * decay_rate)

                    except Exception as e:
                        pass  # Use default recency_score

                # Calculate Popularity Score (engagement)
                likes = post_data.get('likes', 0)
                comments = post_data.get('comments', [])
                comments_count = len(comments) if isinstance(comments, list) else 0

                # Log scale for popularity (handles viral posts)
                # Comments weighted 2x more than likes
                engagement_score = math.log(1 + likes) + math.log(1 + comments_count * 2)

                # Normalize engagement score (divide by 10 to keep in 0-1 range)
                popularity_score = min(1.0, engagement_score / 10.0)

                # HUMAN POST BOOST: Posts from human users get configurable boost
                if is_human_post and feed_config.human_boost > 0:
                    popularity_score = min(1.0, popularity_score * (1 + feed_config.human_boost))

                # MEDIA BOOST: Posts with images/videos get configurable boost
                # Can be disabled (set to 0.0) to prevent content clustering
                has_video = post_data.get('has_video', False)
                has_image = post_data.get('has_image', False)

                if has_video and feed_config.video_boost > 0:
                    popularity_score = min(1.0, popularity_score * (1 + feed_config.video_boost))
                elif has_image and feed_config.image_boost > 0:
                    popularity_score = min(1.0, popularity_score * (1 + feed_config.image_boost))
                elif not has_video and not has_image and feed_config.text_boost > 0:
                    # Boost text-only posts if configured
                    popularity_score = min(1.0, popularity_score * (1 + feed_config.text_boost))

                # Calculate Category Match Score
                # Posts matching more of user's interests get higher scores
                post_categories = post_data.get('masterCategories', [])
                if not post_categories:
                    post_categories = post_data.get('category', [])

                # Count how many user interests this post matches
                matching_categories = set(user_labels) & set(post_categories)
                match_count = len(matching_categories)

                # Normalize by number of user interests (0-1 scale)
                # More matches = higher score
                if len(user_labels) > 0:
                    category_score = match_count / len(user_labels)
                else:
                    category_score = 0.5  # Default if no user labels

                # Ensure minimum score of 0.2 for any categorized post
                category_score = max(0.2, category_score)

                # Combined Score
                # recency_weight controls importance of freshness
                # popularity_weight controls importance of engagement
                # (1 - recency_weight - popularity_weight) goes to category matching
                category_weight = 1.0 - recency_weight - popularity_weight
                final_score = (
                    recency_score * recency_weight +
                    popularity_score * popularity_weight +
                    category_score * category_weight
                )

                # INFLUENCER BOOST: Independent multiplier on final score (configurable)
                is_influencer = post_data.get('is_influencer', False)
                if is_influencer and feed_config.influencer_boost > 0:
                    final_score = min(1.0, final_score * (1 + feed_config.influencer_boost))
                    print(f"[SmartRecs] Influencer boost applied to {item_id[:15]}... (final: {final_score:.3f})")

                scored_items.append((item_id, final_score, recency_score, popularity_score, category_score))

            except Exception as e:
                print(f"[SmartRecs] Error scoring item {item_id}: {e}")
                continue

        # Sort by combined score (descending)
        scored_items.sort(key=lambda x: x[1], reverse=True)

        print(f"[SmartRecs] Scored {len(scored_items)} items")

        # Show top 3 scores for debugging
        if scored_items:
            print(f"[SmartRecs] Top 3 scores:")
            for i, (item_id, final, recency, popularity, category) in enumerate(scored_items[:3]):
                print(f"  {i+1}. {item_id[:15]}... | Score: {final:.3f} (R:{recency:.2f}, P:{popularity:.2f}, C:{category:.2f})")

        # Take top N items based on score
        recommendations.extend([item_id for item_id, _, _, _, _ in scored_items[:n]])

        # CONTENT DIVERSITY: Mix up media types (images, videos, text) for variety
        # Group recommendations by media type, then interleave them
        print(f"[SmartRecs] 🎨 Applying content diversity mixing...")
        
        # Categorize by media type
        video_posts = []
        image_posts = []
        text_posts = []
        
        for item_id in recommendations:
            if item_id in posts_data:
                post_data, _ = posts_data[item_id]
                has_video = post_data.get('has_video', False)
                has_image = post_data.get('has_image', False)
                
                if has_video:
                    video_posts.append(item_id)
                elif has_image:
                    image_posts.append(item_id)
                else:
                    text_posts.append(item_id)
            else:
                # If not in posts_data, treat as text post
                text_posts.append(item_id)
        
        print(f"[SmartRecs] Media breakdown: {len(video_posts)} videos, {len(image_posts)} images, {len(text_posts)} text")
        
        # IMPROVED INTERLEAVING: Distribute media types evenly throughout the list
        # Use weighted round-robin to ensure good mixing even with unbalanced counts
        mixed_recommendations = []
        total_posts = len(video_posts) + len(image_posts) + len(text_posts)
        
        if total_posts > 0:
            # Calculate how often to insert each type (as a ratio)
            video_ratio = len(video_posts) / total_posts if video_posts else 0
            image_ratio = len(image_posts) / total_posts if image_posts else 0
            text_ratio = len(text_posts) / total_posts if text_posts else 0
            
            # Track positions in each list
            video_idx = 0
            image_idx = 0
            text_idx = 0
            
            # Use fractional counters for weighted distribution
            video_counter = 0.0
            image_counter = 0.0
            text_counter = 0.0
            
            while len(mixed_recommendations) < total_posts:
                # Add from the type with the highest counter
                # This ensures proportional distribution
                
                if video_idx < len(video_posts):
                    video_counter += video_ratio
                if image_idx < len(image_posts):
                    image_counter += image_ratio
                if text_idx < len(text_posts):
                    text_counter += text_ratio
                
                # Pick the type with highest counter and add one post
                if video_counter >= image_counter and video_counter >= text_counter and video_idx < len(video_posts):
                    mixed_recommendations.append(video_posts[video_idx])
                    video_idx += 1
                    video_counter -= 1.0
                elif image_counter >= text_counter and image_idx < len(image_posts):
                    mixed_recommendations.append(image_posts[image_idx])
                    image_idx += 1
                    image_counter -= 1.0
                elif text_idx < len(text_posts):
                    mixed_recommendations.append(text_posts[text_idx])
                    text_idx += 1
                    text_counter -= 1.0
                else:
                    # Safety: add any remaining posts
                    if video_idx < len(video_posts):
                        mixed_recommendations.append(video_posts[video_idx])
                        video_idx += 1
                    elif image_idx < len(image_posts):
                        mixed_recommendations.append(image_posts[image_idx])
                        image_idx += 1
                    elif text_idx < len(text_posts):
                        mixed_recommendations.append(text_posts[text_idx])
                        text_idx += 1
                    else:
                        break  # All exhausted
        
        # Use mixed recommendations if we successfully categorized posts
        if mixed_recommendations:
            recommendations = mixed_recommendations[:n]
            print(f"[SmartRecs] ✅ Mixed {len(recommendations)} posts by media type for variety")

        # BATCH VARIATION: Apply rotation based on batch_number to give users variety
        # This ensures different batches show different content without resetting viewed history
        if batch_number > 0 and len(recommendations) > 2:
            import random
            # Use batch_number as seed for consistent but varied results
            random.seed(batch_number)
            # Rotate the list slightly (keep top 2 for smaller batches, shuffle rest)
            top_items = recommendations[:2]  # Keep best 2 items at top (10-post batch)
            remaining_items = recommendations[2:]
            random.shuffle(remaining_items)
            recommendations = top_items + remaining_items
            print(f"[SmartRecs] 🔀 Applied batch variation (seed: {batch_number})")

        print(f"[SmartRecs] Returning {len(recommendations)} recommendations")

        # FALLBACK: If still empty or insufficient, allow re-showing viewed posts
        if len(recommendations) < n:
            shortage = n - len(recommendations)
            print(f"[SmartRecs] ⚠️  WARNING: Only found {len(recommendations)} unviewed posts, need {n}")
            print(f"[SmartRecs] ⚠️  User has exhausted fresh content! Re-showing {shortage} previously viewed posts...")
            print(f"[SmartRecs] 💡 SOLUTION: Add more posts to database OR wait for new content")

            # Re-fetch category items WITHOUT filtering (using Firestore)
            fallback_items = []
            for label in user_labels:
                items = self.get_items_by_label_firestore(label, n=items_per_category)
                fallback_items.extend(items)

            fallback_items = list(set(fallback_items))

            # Score fallback items (same logic as before, but without filtering)
            fallback_scored = []
            for item_id in fallback_items:
                if item_id in recommendations:
                    continue  # Skip items already added

                try:
                    post_ref = db.collection('humanPosts').document(item_id)
                    post_doc = post_ref.get()

                    if not post_doc.exists:
                        post_ref = db.collection('aiPosts').document(item_id)
                        post_doc = post_ref.get()

                    if not post_doc.exists:
                        continue

                    post_data = post_doc.to_dict()

                    # Simple scoring for fallback (just use recency)
                    post_date = post_data.get('date_posted')
                    if post_date:
                        try:
                            if hasattr(post_date, 'timestamp'):
                                post_datetime = datetime.fromtimestamp(post_date.timestamp(), tz=timezone.utc)
                            else:
                                post_datetime = post_date

                            days_old = (datetime.now(timezone.utc) - post_datetime).days
                            decay_rate = recency_weight / 7.0
                            recency_score = math.exp(-days_old * decay_rate)

                            fallback_scored.append((item_id, recency_score))
                        except:
                            pass

                except Exception as e:
                    continue

            # Sort by recency and add to recommendations
            fallback_scored.sort(key=lambda x: x[1], reverse=True)
            for item_id, _ in fallback_scored:
                if item_id not in recommendations:
                    recommendations.append(item_id)
                    if len(recommendations) >= n:
                        break

            print(f"[SmartRecs] Added {len(recommendations)} posts total (including {len(recommendations) - len([r for r in recommendations if r not in all_excluded])} re-shown posts)")

        # Final statistics
        fresh_posts = len([r for r in recommendations if r not in all_excluded])
        reshown_posts = len(recommendations) - fresh_posts
        
        if reshown_posts > 0:
            print(f"[SmartRecs] 🔄 REPEAT WARNING: Returning {reshown_posts}/{len(recommendations)} previously viewed posts")
            print(f"[SmartRecs] 📊 Stats: {fresh_posts} fresh + {reshown_posts} repeats = {len(recommendations)} total")
        else:
            print(f"[SmartRecs] ✅ SUCCESS: All {len(recommendations)} recommendations are fresh (never viewed before)")
        
        # PREPARE FINAL RECOMMENDATIONS
        final_recommendations = recommendations[:n]

        # DEBUG: Check for duplicates before returning
        unique_recs = list(set(final_recommendations))
        if len(unique_recs) != len(final_recommendations):
            print(f"[SmartRecs] ⚠️  WARNING: Found {len(final_recommendations) - len(unique_recs)} duplicate posts in batch!")
            print(f"[SmartRecs] Removing duplicates...")
            final_recommendations = unique_recs[:n]  # Use unique list

        # CACHE DISABLED - Do not store in cache
        # self.batch_cache[cache_key] = final_recommendations
        #
        # # Prevent cache from growing indefinitely
        # if len(self.batch_cache) > self.cache_max_size:
        #     # Remove oldest entry (FIFO)
        #     oldest_key = next(iter(self.batch_cache))
        #     del self.batch_cache[oldest_key]
        #     print(f"[SmartRecs] 🗑️ Cache cleanup: removed oldest batch")

        print(f"[SmartRecs] ✅ Returning batch {batch_number} for user {user_id[:15]}... ({len(final_recommendations)} posts, all filtered fresh)")

        return final_recommendations

    def verify_match_rate(self,
                         recommendations: List[str],
                         user_labels: List[str]) -> dict:
        """
        Verify the match rate of recommendations

        Args:
            recommendations: List of recommended item IDs
            user_labels: User's interest labels

        Returns:
            Dictionary with match statistics
        """
        if not self.enabled:
            return {
                'total': 0,
                'matches': 0,
                'match_rate': 0,
                'match_percentage': 0,
                'matched_items': [],
                'unmatched_items': []
            }

        matches = 0
        total = len(recommendations)
        matched_items = []
        unmatched_items = []

        for item_id in recommendations:
            try:
                response = requests.get(f'{self.api_url}/api/item/{item_id}',
                                      headers=self.headers, timeout=5)
                if response.status_code == 200:
                    item = response.json()
                    item_labels = item.get('Labels', [])

                    # Check if any user label matches any item label
                    matching_labels = set(user_labels) & set(item_labels)
                    if matching_labels:
                        matches += 1
                        matched_items.append({
                            'item_id': item_id,
                            'labels': item_labels,
                            'matching': list(matching_labels)
                        })
                    else:
                        unmatched_items.append({
                            'item_id': item_id,
                            'labels': item_labels
                        })
            except Exception as e:
                print(f"Error verifying item {item_id}: {e}")

        match_rate = matches / total if total > 0 else 0

        return {
            'total': total,
            'matches': matches,
            'match_rate': match_rate,
            'match_percentage': round(match_rate * 100, 1),
            'matched_items': matched_items,
            'unmatched_items': unmatched_items
        }

    def restore_from_firestore(self, user_id: str = None, days_back: int = 30):
        """
        Restore user feedback from Firestore backup to Gorse

        USE CASE: Disaster recovery when Gorse crashes or loses data

        Args:
            user_id: Specific user to restore (None = all users)
            days_back: How many days of history to restore (default 30)

        Returns:
            Dictionary with restoration statistics
        """
        if not self.enabled:
            print("[Restore] Gorse is disabled, skipping restore")
            return {'success': False, 'error': 'Gorse disabled'}

        print(f"[Restore] Starting Gorse restoration from Firestore backup...")
        print(f"[Restore] Target: {'All users' if not user_id else f'User {user_id}'}, Days: {days_back}")

        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days_back)
        restored_count = 0
        error_count = 0
        users_processed = set()

        try:
            # Get users to restore
            if user_id:
                user_docs = [db.collection('userFeedback').document(user_id)]
            else:
                user_docs = db.collection('userFeedback').stream()

            for user_doc in user_docs:
                current_user_id = user_doc.id if hasattr(user_doc, 'id') else user_id
                users_processed.add(current_user_id)

                # Get interactions for this user
                interactions_ref = db.collection('userFeedback').document(current_user_id).collection('interactions')
                interactions = interactions_ref.where('timestamp', '>=', cutoff_time).stream()

                for interaction in interactions:
                    try:
                        data = interaction.to_dict()
                        feedback_type = data.get('feedbackType')
                        post_id = data.get('postId')
                        timestamp = data.get('isoTimestamp')

                        if not all([feedback_type, post_id, timestamp]):
                            continue

                        # Write to Gorse
                        feedback_list = [{
                            'FeedbackType': feedback_type,
                            'UserId': current_user_id,
                            'ItemId': post_id,
                            'Timestamp': timestamp
                        }]

                        response = requests.put(
                            f'{self.api_url}/api/feedback',
                            headers=self.headers,
                            json=feedback_list,
                            timeout=5
                        )

                        if response.status_code in [200, 201]:
                            restored_count += 1
                        else:
                            error_count += 1

                    except Exception as e:
                        error_count += 1
                        print(f"[Restore] Error restoring interaction: {e}")

                print(f"[Restore] Processed user {current_user_id[:15]}...")

            print(f"[Restore] ✅ Restoration complete!")
            print(f"[Restore] Users: {len(users_processed)}, Restored: {restored_count}, Errors: {error_count}")

            return {
                'success': True,
                'users_processed': len(users_processed),
                'interactions_restored': restored_count,
                'errors': error_count
            }

        except Exception as e:
            print(f"[Restore] ⚠️ Restoration failed: {e}")
            return {'success': False, 'error': str(e)}


gorse_client = GorseClient(Config.GORSE_API_URL, Config.GORSE_API_KEY)