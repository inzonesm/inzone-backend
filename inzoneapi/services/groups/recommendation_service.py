# services/groups/recommendation_service.py
"""
Group Chat Recommendation Service

This service provides intelligent recommendations for group chats based on:
1. User interests and master categories
2. Group chat categorization (auto-assigned via OpenAI)
3. Smart ranking algorithm (recency, popularity, category match)
4. Interaction tracking (views, joins, leaves)
"""

from typing import List, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta
from dependencies import db, openai_client
from utils.master_categories import MASTER_CATEGORIES
from config.feed_config import feed_config
import logging
import json
import math
import hashlib
from firebase_admin import firestore

logger = logging.getLogger(__name__)


class GroupChatRecommendationService:
    """Service for group chat recommendations and categorization"""

    @staticmethod
    def categorize_groupchat(groupchat_name: str, bio: str = None) -> List[str]:
        """
        Auto-categorize a group chat based on its name and bio using OpenAI

        Args:
            groupchat_name: Name of the group chat
            bio: Optional bio/description of the group chat

        Returns:
            List of 1-3 master category IDs that match the group chat
        """
        try:
            # Build the content to analyze
            content = f"Group Chat Name: {groupchat_name}"
            if bio and bio.strip():
                content += f"\nDescription: {bio}"

            # Prepare the prompt for OpenAI
            categories_list = "\n".join([f"- {cat}" for cat in MASTER_CATEGORIES])

            prompt = f"""Analyze this group chat and classify it into 1-3 most relevant categories from the list below.

{content}

Available categories:
{categories_list}

Return ONLY a JSON array of category IDs (e.g., ["gaming_esports", "technology_innovation"]).
Choose categories that best match the group chat's purpose and topic.
Respond with valid JSON only, no additional text."""

            # Call OpenAI GPT-4o-mini for classification
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a category classifier. Return only valid JSON arrays."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=100
            )

            result_text = response.choices[0].message.content.strip()

            # Parse JSON response
            categories = json.loads(result_text)

            # Validate categories
            valid_categories = [cat for cat in categories if cat in MASTER_CATEGORIES]

            if not valid_categories:
                logger.warning(f"No valid categories found for group chat: {groupchat_name}")
                # Default to community category
                return ["community_volunteering_activism"]

            logger.info(f"Categorized group chat '{groupchat_name}' as: {valid_categories}")
            return valid_categories[:3]  # Max 3 categories

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenAI response for group chat categorization: {e}")
            return ["community_volunteering_activism"]
        except Exception as e:
            logger.error(f"Error categorizing group chat: {e}")
            return ["community_volunteering_activism"]

    @staticmethod
    def get_smart_recommendations(
        user_id: str,
        limit: int = 20,
        exclude_joined: bool = True,
        page: int = 1
    ) -> Dict[str, Any]:
        """
        Get smart group chat recommendations for a user based on their interests

        Args:
            user_id: User ID to get recommendations for
            limit: Number of recommendations to return
            exclude_joined: Whether to exclude group chats the user has already joined
            page: Page number for pagination

        Returns:
            Dictionary with recommendations and metadata
        """
        try:
            # STEP 1: Get user's master categories
            user_ref = db.collection('humanUsers').document(user_id)
            user_doc = user_ref.get()

            if not user_doc.exists:
                logger.warning(f"User {user_id} not found")
                return {
                    "success": False,
                    "error": "User not found",
                    "recommendations": []
                }

            user_data = user_doc.to_dict()
            user_categories = user_data.get('masterCategories', [])

            # Fallback to default categories if user has none
            if not user_categories:
                user_categories = [
                    "entertainment_pop_culture",
                    "education_learning",
                    "arts_design",
                    "pets_animals",
                    "travel_places"
                ]
                logger.info(f"Using default categories for user {user_id}")

            # STEP 2: Get user's joined group chats (to exclude them)
            joined_groupchat_ids = set()
            if exclude_joined:
                groupchats_query = db.collection('groupChats').where(
                    'user_ids', 'array_contains', user_id
                ).stream()

                for groupchat in groupchats_query:
                    joined_groupchat_ids.add(groupchat.id)

                logger.info(f"User {user_id} has joined {len(joined_groupchat_ids)} group chats")

            # STEP 3: Get user's viewed group chats (to filter out)
            viewed_groupchat_ids = GroupChatRecommendationService._get_viewed_groupchats(user_id)

            # STEP 4: Fetch candidate group chats with matching categories
            candidates = []

            # Query group chats that have at least one matching category
            for category in user_categories:
                groupchats_query = db.collection('groupChats').where(
                    'masterCategories', 'array_contains', category
                ).limit(50).stream()

                for groupchat in groupchats_query:
                    groupchat_data = groupchat.to_dict()
                    groupchat_id = groupchat.id

                    # Skip if already joined or viewed
                    if groupchat_id in joined_groupchat_ids or groupchat_id in viewed_groupchat_ids:
                        continue

                    # Add to candidates
                    groupchat_data['id'] = groupchat_id
                    candidates.append(groupchat_data)

            # Remove duplicates (same group chat from multiple categories)
            seen_ids = set()
            unique_candidates = []
            for candidate in candidates:
                if candidate['id'] not in seen_ids:
                    seen_ids.add(candidate['id'])
                    unique_candidates.append(candidate)

            logger.info(f"Found {len(unique_candidates)} candidate group chats for user {user_id}")

            # STEP 5: If not enough candidates, add some random popular group chats
            if len(unique_candidates) < limit:
                random_groupchats = db.collection('groupChats').limit(30).stream()

                for groupchat in random_groupchats:
                    groupchat_data = groupchat.to_dict()
                    groupchat_id = groupchat.id

                    if groupchat_id not in seen_ids and groupchat_id not in joined_groupchat_ids:
                        groupchat_data['id'] = groupchat_id
                        unique_candidates.append(groupchat_data)
                        seen_ids.add(groupchat_id)

                logger.info(f"Added random group chats, now have {len(unique_candidates)} candidates")

            # STEP 6: Score and rank the candidates
            scored_candidates = []

            for groupchat in unique_candidates:
                score = GroupChatRecommendationService._calculate_groupchat_score(
                    groupchat, user_categories
                )
                scored_candidates.append((groupchat, score))

            # Sort by score (highest first)
            scored_candidates.sort(key=lambda x: x[1], reverse=True)

            # STEP 7: Paginate results
            start_idx = (page - 1) * limit
            end_idx = start_idx + limit
            paginated_results = scored_candidates[start_idx:end_idx]

            # Extract group chat data
            recommendations = [groupchat for groupchat, score in paginated_results]

            logger.info(f"Returning {len(recommendations)} recommendations for user {user_id} (page {page})")

            return {
                "success": True,
                "recommendations": recommendations,
                "data": {
                    "user_categories": user_categories,
                    "total": len(recommendations),
                    "method": "smart_category_ranked",
                    "page": page,
                    "pool_size": len(unique_candidates)
                }
            }

        except Exception as e:
            logger.error(f"Error getting smart recommendations for user {user_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "recommendations": []
            }

    @staticmethod
    def _calculate_groupchat_score(groupchat: Dict[str, Any], user_categories: List[str]) -> float:
        """
        Calculate a score for a group chat based on multiple factors

        Scoring factors:
        1. Category match (35%): How many user interests match group categories
        2. Recency (30%): How recently was the group created
        3. Popularity (35%): Number of members in the group

        Args:
            groupchat: Group chat data dictionary
            user_categories: List of user's master category interests

        Returns:
            Float score (higher is better)
        """
        # Get configuration weights
        recency_weight = getattr(feed_config, 'recency_weight', 0.3)
        popularity_weight = getattr(feed_config, 'popularity_weight', 0.35)
        category_weight = getattr(feed_config, 'category_weight', 0.35)

        # CATEGORY SCORE: Match between user interests and group categories
        groupchat_categories = groupchat.get('masterCategories', [])
        if not groupchat_categories or not user_categories:
            category_score = 0.0
        else:
            matching_categories = set(groupchat_categories).intersection(set(user_categories))
            category_score = len(matching_categories) / len(user_categories)

        # RECENCY SCORE: Exponential decay based on creation date
        date_created = groupchat.get('date_created')
        if date_created:
            # Convert Firestore timestamp to datetime
            if hasattr(date_created, 'timestamp'):
                created_timestamp = date_created
            else:
                created_timestamp = datetime.fromisoformat(str(date_created))

            now = datetime.now(timezone.utc)

            # Make created_timestamp timezone-aware if it isn't
            if created_timestamp.tzinfo is None:
                created_timestamp = created_timestamp.replace(tzinfo=timezone.utc)

            days_old = (now - created_timestamp).days

            # Exponential decay: e^(-days_old * decay_rate)
            decay_rate = 0.05  # Slower decay for group chats (they're long-lived)
            recency_score = math.exp(-days_old * decay_rate)
        else:
            recency_score = 0.5  # Default if no date

        # POPULARITY SCORE: Based on number of members
        member_count = len(groupchat.get('user_ids', []))
        ai_count = len(groupchat.get('ai_usernames', []))
        total_participants = member_count + ai_count

        # Logarithmic scale for popularity (diminishing returns)
        popularity_score = math.log(1 + total_participants) / math.log(100)  # Normalized to ~100 members
        popularity_score = min(popularity_score, 1.0)  # Cap at 1.0

        # FINAL SCORE: Weighted combination
        final_score = (
            recency_score * recency_weight +
            popularity_score * popularity_weight +
            category_score * category_weight
        )

        return final_score

    @staticmethod
    def _get_viewed_groupchats(user_id: str) -> List[str]:
        """
        Get list of group chats that user has already viewed

        Args:
            user_id: User ID to get viewed group chats for

        Returns:
            List of group chat IDs that the user has viewed
        """
        try:
            interactions_ref = db.collection('groupChatFeedback').document(user_id).collection('interactions')
            interactions = interactions_ref.where('feedbackType', '==', 'view').stream()

            viewed_ids = []
            for interaction in interactions:
                data = interaction.to_dict()
                groupchat_id = data.get('groupchatId')
                if groupchat_id:
                    viewed_ids.append(groupchat_id)

            return viewed_ids

        except Exception as e:
            logger.error(f"Error getting viewed group chats for user {user_id}: {e}")
            return []

    @staticmethod
    def record_interaction(user_id: str, groupchat_id: str, feedback_type: str):
        """
        Record user interaction with a group chat (view, join, leave)

        This uses dual-write strategy:
        1. Firestore: Permanent backup, queryable, restorable
        2. Gorse: Real-time recommendations (future integration)

        Args:
            user_id: User ID
            groupchat_id: Group chat ID
            feedback_type: Type of interaction ('view', 'join', 'leave')
        """
        timestamp = datetime.now(timezone.utc)
        iso_timestamp = timestamp.isoformat()

        try:
            feedback_doc = {
                'userId': user_id,
                'groupchatId': groupchat_id,
                'feedbackType': feedback_type,  # 'view', 'join', 'leave'
                'timestamp': timestamp,
                'isoTimestamp': iso_timestamp
            }

            # Use deterministic document ID to prevent duplicates
            doc_id = hashlib.md5(f"{user_id}_{groupchat_id}_{feedback_type}".encode()).hexdigest()

            # Store in Firestore
            db.collection('groupChatFeedback').document(user_id).collection('interactions').document(doc_id).set(
                feedback_doc, merge=True
            )

            # Update user's interaction summary
            summary_ref = db.collection('groupChatFeedback').document(user_id)
            summary_ref.set({
                'userId': user_id,
                'lastInteraction': timestamp,
                f'{feedback_type}Count': firestore.Increment(1)
            }, merge=True)

            logger.info(f"Recorded {feedback_type} interaction for user {user_id} on group chat {groupchat_id}")

            # TODO: Sync with Gorse when group chats are integrated with Gorse
            # For now, we only store in Firestore

        except Exception as e:
            logger.error(f"Error recording group chat interaction: {e}")

    @staticmethod
    def get_popular_groupchats(limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get popular/trending group chats based on member count

        Args:
            limit: Number of group chats to return

        Returns:
            List of group chat dictionaries
        """
        try:
            # Get all group chats and sort by member count
            groupchats = db.collection('groupChats').limit(100).stream()

            groupchat_list = []
            for groupchat in groupchats:
                data = groupchat.to_dict()
                data['id'] = groupchat.id
                data['member_count'] = len(data.get('user_ids', []))
                groupchat_list.append(data)

            # Sort by member count (descending)
            groupchat_list.sort(key=lambda x: x['member_count'], reverse=True)

            return groupchat_list[:limit]

        except Exception as e:
            logger.error(f"Error getting popular group chats: {e}")
            return []

    @staticmethod
    def sync_groupchat_to_gorse(groupchat_id: str, groupchat_data: Dict[str, Any]):
        """
        Sync a group chat to Gorse recommendation engine as an item

        Args:
            groupchat_id: Group chat ID
            groupchat_data: Group chat data dictionary

        Note: This is a placeholder for future Gorse integration
        """
        # TODO: Implement Gorse integration for group chats
        # For now, this is a no-op
        # When implemented, this should:
        # 1. Call gorse_client.insert_item(groupchat_id, labels=masterCategories, ...)
        # 2. Use item type 'groupchat' to distinguish from posts
        pass
