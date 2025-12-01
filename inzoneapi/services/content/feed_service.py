# services/content/feed_service.py
from dependencies import db, openai_client
from typing import Dict, Any, List
import logging
from flask import jsonify, request
from google.cloud import firestore
from datetime import datetime, timezone, timedelta
import json
import uuid
import math
import random
import hashlib
from services.recommendation.gorse_client import gorse_client
from services.content.post_retrieval_service import PostRetrievalService
from services.content.multimodal_classifier import MultimodalCategoryClassifier
from utils.helpers import get_user_name

logger = logging.getLogger(__name__)

class FeedService:
    """Service for feed and post operations"""

    @staticmethod
    def generate_categories(post_text: str) -> List[str]:
        """
        Generate master categories for a post using OpenAI.
        Returns a list of master category IDs (e.g., ["mental_health_wellness", "gaming_virtual_worlds"])
        """
        try:
            if not post_text:
                return []

            # Build a clear list of master categories for the prompt
            from utils.master_categories import MASTER_CATEGORIES, CATEGORY_DISPLAY_NAMES

            categories_list = "\n".join([
                f"- {cat_id}: {CATEGORY_DISPLAY_NAMES[cat_id]}"
                for cat_id in MASTER_CATEGORIES
            ])

            prompt = (
                f"Classify the following post into 1-4 of these master categories.\n\n"
                f"MASTER CATEGORIES:\n{categories_list}\n\n"
                f"Return ONLY a JSON array of category IDs (the lowercase_underscore version). "
                f"Example: [\"mental_health_wellness\", \"gaming_virtual_worlds\"]\n\n"
                f"Post: {post_text}\n\n"
                f"Categories (JSON array only):"
            )

            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",  # Using mini for faster/cheaper classification
                messages=[
                    {"role": "system", "content": "You are a precise content classifier. Return only valid JSON arrays of category IDs."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3  # Lower temperature for more consistent classification
            )

            content = response.choices[0].message.content.strip()

            # Extract JSON array from response
            try:
                # Remove markdown code blocks if present
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]

                categories = json.loads(content)

                if isinstance(categories, list):
                    # Validate that returned categories are in MASTER_CATEGORIES
                    valid_categories = [cat for cat in categories if cat in MASTER_CATEGORIES]

                    if not valid_categories:
                        logger.warning("No valid master categories returned for post, using fallback")
                        return ["entertainment_pop_culture"]  # Safe fallback

                    # Limit to 4 categories
                    return valid_categories[:4]
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON response from OpenAI: {content}")
                return ["entertainment_pop_culture"]  # Safe fallback

            return []

        except Exception as ex:
            logger.error(f"Error generating categories: {ex}")
            return ["entertainment_pop_culture"]  # Safe fallback

    @staticmethod
    def create_human_post(data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a human post"""
        try:
            logger.info("=" * 70)
            logger.info("[CREATE_HUMAN_POST] New post creation started")
            logger.info("=" * 70)
            
            if not data or not data.get("Post"):
                return jsonify({"success": False, "error": "Post content is required", "code": "INVALID_POST_CONTENT"}), 400

            username = data.get("UserName")
            if not username:
                return jsonify({"success": False, "error": "Username is required", "code": "INVALID_USERNAME"}), 400

            post_text = data.get("Post").get("TextContent", "")
            image_content = data.get("Post").get("ImageContent", [])
            video_content = data.get("Post").get("VideoContent", [])
            user_document_id = data.get("UserDocumentId")

            logger.info(f"[CREATE_HUMAN_POST] Post text: {post_text[:60]}...")
            logger.info(f"[CREATE_HUMAN_POST] Images: {len(image_content)}, Videos: {len(video_content)}")
            logger.info("[CREATE_HUMAN_POST] Calling MultimodalCategoryClassifier...")

            # Use multimodal classifier for better categorization
            classification_result = MultimodalCategoryClassifier.classify_post({
                'post': {
                    'text_content': post_text,
                    'image_content': image_content,
                    'video_content': video_content
                }
            })
            
            subCategories = classification_result.get('subCategories', [])
            masterCategories = classification_result.get('masterCategories', [])
            
            logger.info(f"[CREATE_HUMAN_POST] Classification result:")
            logger.info(f"  - subCategories: {subCategories}")
            logger.info(f"  - masterCategories: {masterCategories}")
            logger.info(f"  - method: {classification_result.get('method', 'unknown')}")
            
            # Fallback to old method if classification fails
            if not masterCategories:
                masterCategories = data.get("category", []) if data.get("category", []) else FeedService.generate_categories(post_text)
                logger.warning(f"[CREATE_HUMAN_POST] Multimodal classifier returned no categories, using fallback: {masterCategories}")

            # Check if user is an influencer
            influencer_doc = db.collection('influencers').document(user_document_id).get()
            is_influencer = influencer_doc.exists

            logger.info(f"[CREATE_HUMAN_POST] Saving post to Firestore...")
            logger.info(f"  - Post ID: {data.get('Id')}")
            logger.info(f"  - subCategories: {subCategories}")
            logger.info(f"  - masterCategories: {masterCategories}")

            post_data = {
                "category": masterCategories,  # Keep for backward compatibility
                "subCategories": subCategories,  # New: granular categorization
                "masterCategories": masterCategories,  # New: master categories
                "comments": [],
                "date_posted": firestore.SERVER_TIMESTAMP,
                "likes": 0,
                "has_image": bool(image_content),
                "has_video": bool(video_content),
                "post": {
                    "image_content": image_content,
                    "text_content": post_text,
                    "video_content": video_content
                },
                "user_document_id": user_document_id,
                "user_name": username,
                "id": data.get("Id"),
                "is_influencer": is_influencer,
                "character_info": data.get("character_info")
            }

            db.collection('humanPosts').document(data.get("Id")).set(post_data)
            
            logger.info(f"[CREATE_HUMAN_POST] ✅ Post saved successfully!")
            logger.info("=" * 70)

            # Update Gorse with new post using master categories
            try:
                labels = masterCategories.copy() if masterCategories else []
                if image_content:
                    labels.append('has_image')
                if video_content:
                    labels.append('has_video')
                labels.append('human_post')

                gorse_client.insert_item(
                    item_id=data.get("Id"),
                    labels=labels,
                    comment=post_text[:200] if post_text else '',
                    timestamp=datetime.now(timezone.utc).isoformat()
                )
                logger.info(f"Synced human post {data.get('Id')} to Gorse with {len(masterCategories)} master categories + {len(subCategories)} subcategories")
            except Exception as e:
                logger.warning(f"Failed to sync post to Gorse: {e}")

            return jsonify({"postId": data.get("Id")}), 200
        except Exception as ex:
            logger.error(f"Error creating human post: {ex}")
            return jsonify({"success": False, "error": str(ex), "code": "POST_CREATE_ERROR"}), 500

    @staticmethod
    def create_ai_post(data: Dict[str, Any]) -> Dict[str, Any]:
        """Create an AI post"""
        try:
            if not data or not data.get("Post"):
                return jsonify({"success": False, "error": "Post content is required", "code": "INVALID_POST_CONTENT"}), 400

            username = data.get("username")
            if not username:
                return jsonify({"success": False, "error": "Username is required", "code": "MISSING_USERNAME"}), 400

            ai_user_ref = db.collection('aiUsers').document(username)
            ai_user_doc = ai_user_ref.get()
            if not ai_user_doc.exists:
                return jsonify({"success": False, "error": "Invalid username", "code": "USER_NOT_FOUND"}), 400

            post_text = data.get("Post").get("TextContent", "")
            image_content = data.get("Post").get("ImageContent", [])
            video_content = data.get("Post").get("VideoContent", [])

            # Use multimodal classifier for better categorization
            classification_result = MultimodalCategoryClassifier.classify_post({
                'post': {
                    'text_content': post_text,
                    'image_content': image_content,
                    'video_content': video_content
                }
            })
            
            subCategories = classification_result.get('subCategories', [])
            masterCategories = classification_result.get('masterCategories', [])
            
            # Fallback to old method if classification fails
            if not masterCategories:
                masterCategories = data.get("category", []) if data.get("category", []) else FeedService.generate_categories(post_text)
                logger.warning(f"Multimodal classifier returned no categories, using fallback")

            post_data = {
                "category": masterCategories,  # Keep for backward compatibility
                "subCategories": subCategories,  # New: granular categorization
                "masterCategories": masterCategories,  # New: master categories
                "comments": [],
                "date_posted": firestore.SERVER_TIMESTAMP,
                "likes": 0,
                "has_image": bool(image_content),
                "has_video": bool(video_content),
                "post": {
                    "image_content": image_content,
                    "text_content": post_text,
                    "video_content": video_content
                },
                "user_name": username
            }

            doc_ref = db.collection('aiPosts').document()
            post_id = doc_ref.id
            post_data["id"] = post_id
            doc_ref.set(post_data)

            ai_user_ref.update({"posts": firestore.ArrayUnion([post_id])})

            # Update Gorse with new AI post using master categories
            try:
                labels = masterCategories.copy() if masterCategories else []
                if image_content:
                    labels.append('has_image')
                if video_content:
                    labels.append('has_video')
                labels.append('ai_post')

                gorse_client.insert_item(
                    item_id=post_id,
                    labels=labels,
                    comment=post_text[:200] if post_text else '',
                    timestamp=datetime.now(timezone.utc).isoformat()
                )
                logger.info(f"Synced AI post {post_id} to Gorse with {len(masterCategories)} master categories + {len(subCategories)} subcategories")
            except Exception as e:
                logger.warning(f"Failed to sync AI post to Gorse: {e}")

            return jsonify({"postId": post_id}), 200
        except Exception as ex:
            logger.error(f"Error creating AI post: {ex}")
            return jsonify({"success": False, "error": str(ex), "code": "POST_CREATE_ERROR"}), 500

    @staticmethod
    def repost_post(data: Dict[str, Any]) -> Dict[str, Any]:
        """Repost a normal post (not just AI chats)"""
        try:
            if not data:
                return jsonify({"success": False, "error": "Request data missing", "code": "NO_DATA"}), 400

            original_post_id = data.get("OriginalPostId")
            reposting_user_id = data.get("RepostingUserId")

            if not original_post_id or not reposting_user_id:
                return jsonify({"success": False, "error": "OriginalPostId and RepostingUserId are required", "code": "MISSING_PARAMS"}), 400

            original_doc = db.collection("humanPosts").document(original_post_id).get()
            original_post_type = "human"

            if not original_doc.exists:
                original_doc = db.collection("aiPosts").document(original_post_id).get()
                original_post_type = "ai"

            if not original_doc.exists:
                return jsonify({"success": False, "error": "Original post not found", "code": "ORIGINAL_POST_NOT_FOUND"}), 404

            original_data = original_doc.to_dict()
            post = original_data.get("post", {})
            post_text = post.get("text_content", "")
            image_content = post.get("image_content", [])
            video_content = post.get("video_content", [])
            categories = original_data.get("category", [])
            original_user_name = original_data.get("user_name")

            reposting_user_doc = db.collection("humanUsers").document(reposting_user_id).get()
            user_type = "human"

            if not reposting_user_doc.exists:
                reposting_user_doc = db.collection("aiUsers").document(reposting_user_id).get()
                user_type = "ai"

            if not reposting_user_doc.exists:
                return jsonify({"success": False, "error": "Reposting user not found", "code": "REPOSTING_USER_NOT_FOUND"}), 404

            reposting_user_data = reposting_user_doc.to_dict()

            repost_id = str(uuid.uuid4())
            repost_data = {
                "original_post_id": original_post_id,
                "original_post_type": original_post_type,
                "original_post_author": original_user_name,
                "category": categories,
                "comments": [],
                "date_posted": firestore.SERVER_TIMESTAMP,
                "likes": 0,
                "has_image": bool(image_content),
                "has_video": bool(video_content),
                "post": {
                    "image_content": image_content,
                    "text_content": post_text,
                    "video_content": video_content
                },
                "user_document_id": reposting_user_id,
                "user_name": reposting_user_data.get("username"),
                "id": repost_id,
                "user_type": user_type
            }

            db.collection("reposts").document(repost_id).set(repost_data)

            # Update Gorse with new repost
            try:
                labels = categories.copy() if categories else []
                if image_content:
                    labels.append('image')
                if video_content:
                    labels.append('video')
                labels.append('reposts')

                gorse_client.insert_item(
                    item_id=repost_id,
                    labels=labels,
                    comment=post_text[:200] if post_text else '',
                    timestamp=datetime.now(timezone.utc).isoformat()
                )
                logger.info(f"Synced repost {repost_id} to Gorse")
            except Exception as e:
                logger.warning(f"Failed to sync repost to Gorse: {e}")

            # Create notification for original post author (don't notify yourself)
            original_author_id = original_data.get('user_document_id')
            if original_author_id and original_author_id != reposting_user_id:
                try:
                    reposting_username = get_user_name(reposting_user_id)

                    notification_data = {
                        'userId': original_author_id,
                        'type': 'repost',
                        'title': 'Post Reposted',
                        'body': f'{reposting_username} reposted your post',
                        'isRead': False,
                        'createdAt': firestore.SERVER_TIMESTAMP,
                        'data': {
                            'originalPostId': original_post_id,
                            'repostId': repost_id,
                            'reposterId': reposting_user_id,
                            'reposterUsername': reposting_username
                        },
                        # deeplink removed per repository-wide deprecation of in-app deeplinks
                    }

                    db.collection('notifications').add(notification_data)
                    logger.info(f"Repost notification created for user {original_author_id}")

                except Exception as e:
                    logger.error(f"Error creating repost notification: {e}")

            return jsonify({"postId": repost_id}), 200
        except Exception as ex:
            logger.error(f"Error creating repost: {ex}")
            return jsonify({"success": False, "error": str(ex), "code": "REPOST_ERROR"}), 500

    @staticmethod
    def create_repost(data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a repost with AI chat content"""
        try:
            if not data or not data.get("Post"):
                return jsonify({"success": False, "error": "Post content is required", "code": "INVALID_POST_CONTENT"}), 400

            post_text = data.get("Post").get("TextContent", "")
            image_content = data.get("Post").get("ImageContent", [])
            video_content = data.get("Post").get("VideoContent", [])

            # Use multimodal classifier for better categorization
            classification_result = MultimodalCategoryClassifier.classify_post({
                'post': {
                    'text_content': post_text,
                    'image_content': image_content,
                    'video_content': video_content
                }
            })
            
            subCategories = classification_result.get('subCategories', [])
            masterCategories = classification_result.get('masterCategories', [])
            
            # Fallback to old method if classification fails
            if not masterCategories:
                masterCategories = data.get("category", []) if data.get("category", []) else FeedService.generate_categories(post_text)
                logger.warning(f"Multimodal classifier returned no categories, using fallback")

            post_data = {
                "ai_chat_content": data.get("AIChatContent"),
                "ai_name": data.get("AIName"),
                "ai_profile_image_url": data.get("AIProfileImageURL"),
                "category": masterCategories,  # Keep for backward compatibility
                "subCategories": subCategories,  # New: granular categorization
                "masterCategories": masterCategories,  # New: master categories
                "comments": [],
                "date_posted": firestore.SERVER_TIMESTAMP,
                "likes": 0,
                "has_image": bool(image_content),
                "has_video": bool(video_content),
                "post": {
                    "image_content": image_content,
                    "text_content": post_text,
                    "video_content": video_content
                },
                "user_document_id": data.get("UserDocumentId"),
                "user_name": data.get("UserName"),
                "ai_id": data.get("AiId"),
                "id": data.get("Id")
            }

            db.collection('reposts').document(data.get("Id")).set(post_data)

            # Sync repost to Gorse with master categories
            try:
                labels = masterCategories.copy() if masterCategories else []
                if image_content:
                    labels.append('has_image')
                if video_content:
                    labels.append('has_video')
                labels.append('repost')

                gorse_client.insert_item(
                    item_id=data.get("Id"),
                    labels=labels,
                    comment=post_text[:200] if post_text else '',
                    timestamp=datetime.now(timezone.utc).isoformat()
                )
                logger.info(f"Synced repost {data.get('Id')} to Gorse with {len(masterCategories)} master categories + {len(subCategories)} subcategories")
            except Exception as e:
                logger.warning(f"Failed to sync repost to Gorse: {e}")

            return jsonify({"postId": data.get("Id")}), 200
        except Exception as ex:
            logger.error(f"Error creating repost: {ex}")
            return jsonify({"success": False, "error": str(ex), "code": "POST_CREATE_ERROR"}), 500

    @staticmethod
    def update_human_post(data: Dict[str, Any]) -> Dict[str, Any]:
        """Update a human post"""
        try:
            post_id = data.get("Id")
            doc_ref = db.collection('humanPosts').document(post_id)

            if not doc_ref.get().exists:
                return jsonify({"success": False, "error": "Post not found", "code": "POST_NOT_FOUND"}), 404

            update_data = {
                "post": {
                    "image_content": data.get("Post").get("ImageContent", []),
                    "text_content": data.get("Post").get("TextContent"),
                    "video_content": data.get("Post").get("VideoContent", [])
                }
            }

            doc_ref.update(update_data)
            return jsonify({"postId": post_id}), 200
        except Exception as ex:
            logger.error(f"Error updating human post: {ex}")
            return jsonify({"success": False, "error": str(ex), "code": "POST_UPDATE_ERROR"}), 500

    @staticmethod
    def update_ai_post(data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an AI post"""
        try:
            post_id = data.get("Id")
            doc_ref = db.collection('aiPosts').document(post_id)

            if not doc_ref.get().exists:
                return jsonify({"success": False, "error": "Post not found", "code": "POST_NOT_FOUND"}), 404

            update_data = {
                "post": {
                    "image_content": data.get("Post").get("ImageContent", []),
                    "text_content": data.get("Post").get("TextContent"),
                    "video_content": data.get("Post").get("VideoContent", [])
                }
            }

            doc_ref.update(update_data)
            return jsonify({"postId": post_id}), 200
        except Exception as ex:
            logger.error(f"Error updating AI post: {ex}")
            return jsonify({"success": False, "error": str(ex), "code": "POST_UPDATE_ERROR"}), 500

    @staticmethod
    def get_feed() -> Dict[str, Any]:
        """Get the main feed"""
        try:
            collections = ['aiPosts', 'humanPosts', 'reposts']
            posts = []

            for coll in collections:
                query = (
                    db.collection(coll)
                      .order_by("date_posted", direction=firestore.Query.DESCENDING)
                      .limit(15)
                )
                for doc in query.stream():
                    data = doc.to_dict() or {}
                    data['id'] = doc.id
                    data['collection'] = coll

                    ts = data.get('date_posted')
                    if isinstance(ts, datetime):
                        data['date_posted'] = ts.astimezone(timezone.utc).isoformat()
                    elif ts is None:
                        data['date_posted'] = ""

                    posts.append(data)

            posts.sort(key=lambda x: x.get('date_posted', ''), reverse=True)

            return jsonify({"success": True, "data": posts[:15]}), 200

        except Exception as ex:
            logger.exception("Error getting feed")
            return jsonify({"success": False, "error": str(ex)}), 500

    @staticmethod
    def get_smart_recommendations(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get smart category-based recommendations for a user

        Request body:
            {
                "user_id": "user123",
                "limit": 20,  # optional, default 20
                "target_match_rate": 0.7,  # optional, default 0.7 (70%)
                "include_verification": false  # optional, default false
            }

        Returns personalized recommendations based on user's interest categories
        with high match rate (70%+ by default)
        """
        try:
            from config import feed_config
            from services.content.post_retrieval_service import PostRetrievalService

            user_id = data.get('user_id')
            limit = data.get('limit', 20)
            target_match_rate = data.get('target_match_rate', 0.7)
            include_verification = data.get('include_verification', False)
            batch_number = data.get('batch_number', 0)  # Batch number for different recommendation sets
            page = data.get('page', 1)  # NEW: Page number for pagination within same batch
            exclude_ids = data.get('exclude_ids', [])  # Post IDs already loaded in client

            if not user_id:
                return jsonify({"success": False, "error": "user_id is required"}), 400

            if exclude_ids:
                logger.info(f"[SmartRecs] Batch #{batch_number}, Page {page} requested by user {user_id[:15]}... (excluding {len(exclude_ids)} already-loaded posts)")
            else:
                logger.info(f"[SmartRecs] Batch #{batch_number}, Page {page} requested by user {user_id[:15]}...")

            # Get user's interest labels from Firestore
            user_doc = db.collection('humanUsers').document(user_id).get()
            if not user_doc.exists:
                return jsonify({"success": False, "error": "User not found"}), 404

            user_data = user_doc.to_dict()

            # CRITICAL FIX: Use masterCategories field for consistent matching
            # masterCategories are mapped from user interests and match post labels in Gorse
            user_labels = user_data.get('masterCategories', [])

            # Fallback to interests if masterCategories not yet populated
            if not user_labels:
                user_labels = user_data.get('interests', [])
                logger.warning(f"User {user_id} missing masterCategories, using raw interests")

            # DEFAULT CATEGORIES: If user has no interests, use beginner-friendly categories
            # These categories have broad appeal and high engagement
            DEFAULT_COLD_START_CATEGORIES = [
                "comedy_humor_memes",           # Universal appeal
                "education_learning",           # Educational content
                "arts_design",                  # Visual content
                "pets_animals",                 # Animal content (highly engaging)
                "travel_places",                # Aspirational content
                "entertainment_pop_culture"     # Trending content
            ]

            if not user_labels:
                logger.info(f"User {user_id} has no interests, using default cold start categories")
                user_labels = DEFAULT_COLD_START_CATEGORIES

            # PHASE 2: Use ranking by default (recency + popularity)
            # To disable ranking, pass use_ranking=false in request
            use_ranking = data.get('use_ranking', True)

            # PAGINATION SETUP: Generate larger pool, then slice by page
            # Each batch generates 30 posts (3 pages x 10 posts per page)
            # Same batch_number = same 30 posts, different pages = different slices
            POSTS_PER_PAGE = 10  # Each page returns 10 posts
            MAX_POOL_SIZE = 30   # Generate 30 posts per batch (supports 3 pages)
            total_pool_size = MAX_POOL_SIZE  # Always generate full pool for consistent pagination

            if use_ranking:
                # Get smart recommendations WITH recency and popularity ranking
                # Use global config for real-time adjustable parameters
                recommendations = gorse_client.get_smart_recommendations_with_ranking(
                    user_id=user_id,
                    user_labels=user_labels,
                    n=total_pool_size,  # Get large pool for pagination
                    target_match_rate=target_match_rate,
                    recency_weight=feed_config.recency_weight,
                    popularity_weight=feed_config.popularity_weight,
                    batch_number=batch_number,  # NEW: Pass batch number for variation
                    exclude_ids=exclude_ids  # Exclude posts already loaded in client
                )
                method = "smart_category_ranked"
            else:
                # Get smart recommendations WITHOUT ranking
                recommendations = gorse_client.get_smart_recommendations(
                    user_id=user_id,
                    user_labels=user_labels,
                    n=total_pool_size,  # Get large pool for pagination
                    target_match_rate=target_match_rate,
                    shuffle=True
                )
                method = "smart_category_basic"

            logger.info(f"[SmartRecs] Generated pool of {len(recommendations)} post IDs (requested limit: {limit})")

            if len(recommendations) == 0:
                logger.warning("[SmartRecs] No recommendations generated! Check if posts exist in user's categories")
                return jsonify({
                    "success": False,
                    "error": "No recommendations available",
                    "recommendations": [],
                    "data": {"user_labels": user_labels, "total": 0}
                }), 200

            # PAGINATION: Slice the recommendation pool by page number
            # Page 1 = items 0-9, Page 2 = items 10-19, Page 3 = items 20-29
            start_idx = (page - 1) * POSTS_PER_PAGE
            end_idx = start_idx + POSTS_PER_PAGE
            paged_recommendations = recommendations[start_idx:end_idx]

            # Show first 3 IDs for debugging
            if paged_recommendations:
                first_3_ids = [pid[:15] + '...' for pid in paged_recommendations[:3]]
                logger.info(f"[SmartRecs] Batch {batch_number}, Page {page}: Returning posts [{start_idx}:{end_idx}] = {len(paged_recommendations)} posts")
                logger.info(f"[SmartRecs] First 3 IDs: {first_3_ids}")
            else:
                logger.info(f"[SmartRecs] Batch {batch_number}, Page {page}: EMPTY (no posts in range [{start_idx}:{end_idx}])")

            # Convert post IDs to full post objects for Flutter app
            all_post_objects = PostRetrievalService.get_posts_by_ids(paged_recommendations)

            # Filter out None values (posts that don't exist in Firestore)
            post_objects = [p for p in all_post_objects if p is not None]
            logger.info(f"[SmartRecs] Fetched {len(post_objects)} valid post objects (out of {len(all_post_objects)} requested)")

            if len(post_objects) == 0:
                logger.warning("[SmartRecs] No valid post objects! Posts may not exist in Firestore")
            else:
                first_ids = [p.get('id', '?')[:15] for p in post_objects[:3]]
                logger.info(f"[SmartRecs] First 3 IDs: {first_ids}")

            result = {
                "success": True,
                "recommendations": post_objects,  # Flutter expects this key with full post objects
                "data": {
                    "post_ids": paged_recommendations,  # IDs for this specific page
                    "user_labels": user_labels,
                    "total": len(post_objects),
                    "target_match_rate": target_match_rate,
                    "method": method,
                    "ranking_enabled": use_ranking,
                    "page": page,  # Current page number
                    "batch_number": batch_number,  # Current batch number
                    "pool_size": len(recommendations)  # Total pool size for this batch
                }
            }

            # Optional: Include match rate verification
            if include_verification and recommendations:
                verification = gorse_client.verify_match_rate(recommendations, user_labels)
                result["data"]["verification"] = verification

            return jsonify(result), 200

        except Exception as ex:
            logger.exception("Error getting smart recommendations")
            return jsonify({"success": False, "error": str(ex)}), 500
    @staticmethod
    def posts_flow(user_id: str, page: int = 1) -> tuple:
        """
        Main feed generation endpoint with Gorse integration.
        Returns paginated posts with smart ranking.
        """
        try:
            posts_per_page = 10  # 🎯 Changed from 30 to 10 posts per page

            print(f"\n{'='*60}")
            print(f"📱 FEED REQUEST from user: {user_id}, page: {page}")
            print(f"{'='*60}")

            # Try to get recommendations from Gorse first
            if gorse_client.enabled:
                try:
                    offset = (page - 1) * posts_per_page
                    print(f"🤖 Requesting recommendations from Gorse...")

                    # 🎯 Request 50% more posts to filter duplicates and low-quality recommendations
                    request_limit = int(posts_per_page * 1.5)
                    recommended_ids = gorse_client.get_recommendations(
                        user_id=user_id,
                        limit=request_limit,
                        offset=offset
                    )

                    if recommended_ids and len(recommended_ids) >= posts_per_page * 0.5:  # At least 50% success rate
                        print(f"✅ GORSE ACTIVE: Got {len(recommended_ids)} personalized recommendations!")
                        print(f"   Post IDs: {recommended_ids[:3]}..." if len(recommended_ids) > 3 else f"   Post IDs: {recommended_ids}")

                        # 🎯 Check recommendation quality: if we got fewer posts than requested, pool is draining
                        recommendation_quality = len(recommended_ids) / request_limit
                        print(f"📊 Recommendation quality: {recommendation_quality:.1%} ({len(recommended_ids)}/{request_limit})")

                        posts = PostRetrievalService.get_posts_by_ids(recommended_ids)

                        if posts and len(posts) >= posts_per_page * 0.5:
                            print(f"✅ Successfully fetched {len(posts)} posts from Firestore")

                            # 🎯 Only take the number we need
                            posts = posts[:posts_per_page]
                            actual_post_ids = [p.get('id') for p in posts if p.get('id')]

                            # 🎯 Do NOT mark as 'read' here - let Flutter track actual views via /feed/track-view
                            print(f"📝 Returning {len(actual_post_ids)} recommendations (will be marked as read when actually viewed)")

                            # 🎯 If quality is low (< 70%), warn that we're running out of recommendations
                            if recommendation_quality < 0.7:
                                print(f"⚠️  LOW QUALITY WARNING: Recommendation pool draining (quality: {recommendation_quality:.1%})")
                                print(f"   Consider generating more content or waiting for user interactions")

                            print(f"🎯 Returning GORSE-POWERED recommendations\n")
                            # Add source indicator
                            for post in posts:
                                post['recommendation_source'] = 'gorse'

                            return jsonify({
                                'posts': posts,
                                'page': page,
                                'has_more': recommendation_quality > 0.3,  # Only say "has_more" if quality is decent
                                'source': 'gorse',
                                'quality': round(recommendation_quality, 2)
                            }), 200
                        else:
                            print(f"⚠️  Not enough valid posts from Gorse ({len(posts)} posts), falling back")
                    else:
                        if recommended_ids:
                            print(f"⚠️  Too few recommendations from Gorse ({len(recommended_ids)}/{request_limit}), falling back")
                        else:
                            print("⚠️  No recommendations from Gorse, falling back to legacy algorithm")
                except Exception as e:
                    print(f"❌ Error getting Gorse recommendations: {e}")
                    print("⚠️  Falling back to legacy algorithm")
            else:
                print("⚠️  Gorse is disabled, using legacy algorithm")

            user_doc = db.collection('humanUsers').document(user_id).get()
            user_categories = set()
            if user_doc.exists:
                user_categories.update(user_doc.to_dict().get('interests', []))

            # Helper Functions
            def parse_date(date_str):
                try:
                    naive_dt = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %Z")
                    return naive_dt.replace(tzinfo=timezone.utc)
                except Exception:
                    return datetime.min.replace(tzinfo=timezone.utc)

            def compute_freshness_score(post_date):
                now = datetime.now(timezone.utc)
                seconds_since = (now - post_date).total_seconds()
                return 1 / math.log(seconds_since + 2)

            def compute_engagement_score(post):
                return float(post.get("engagement_score", 0.5))

            def compute_media_score(post):
                if post.get("has_video"):
                    return 1.0 if post.get("post_type") == "human_post" else 0.9
                elif post.get("has_image"):
                    return 0.8 if post.get("post_type") == "human_post" else 0.7
                else:
                    return 0.6 if post.get("post_type") == "human_post" else 0.5

            def compute_human_score(post):
                return 1.0 if post.get("post_type") in ["human_post", "repost"] else 0.8

            def compute_repost_adjustment(post):
                if post.get("post_type") == "repost":
                    return 0.8
                return 0.0

            def compute_category_score(post):
                if not user_categories:
                    return 0.0
                post_cats = set(post.get('category', []))
                matches = user_categories.intersection(post_cats)
                return min(0.1 * len(matches), 0.3)

            def compute_final_score(post):
                date_str = post.get('date_posted', '')
                post_date = parse_date(date_str)
                freshness = compute_freshness_score(post_date)
                engagement = compute_engagement_score(post)
                media = compute_media_score(post)
                human = compute_human_score(post)
                repost_adj = compute_repost_adjustment(post)
                category_score = compute_category_score(post)

                # Base score calculation
                if post.get("has_video"):
                    base_score = (0.30 * freshness +
                             0.20 * engagement +
                             0.15 * media +
                             0.12 * human +
                             0.23 * repost_adj)
                else:
                    base_score = (0.25 * freshness +
                             0.20 * engagement +
                             0.10 * media +
                             0.15 * human +
                             0.30 * repost_adj)

                final_score = base_score + category_score
                return final_score

            # Fetch and Filter Posts
            def fetch_posts(collection_name, limit=None, filter=None, or_filter=None):
                results = []
                seen_ids = set()

                if filter:
                    field, value = filter
                    query = db.collection(collection_name).where(field, '==', value)
                    if limit:
                        query = query.limit(limit)
                    return [doc.to_dict() for doc in query.stream()]

                if or_filter:
                    for field, value in or_filter:
                        query = db.collection(collection_name).where(field, '==', value)
                        if limit:
                            query = query.limit(limit)
                        for doc in query.stream():
                            doc_dict = doc.to_dict()
                            doc_id = doc.id
                            if doc_id not in seen_ids:
                                results.append(doc_dict)
                                seen_ids.add(doc_id)
                    return results[:limit] if limit else results

                # If no filters
                query = db.collection(collection_name)
                if limit:
                    query = query.limit(limit)
                return [doc.to_dict() for doc in query.stream()]

            human_posts_all = fetch_posts('humanPosts')

            human_count = len(human_posts_all)

            ai_posts_all = (
                fetch_posts('aiPosts', limit=(human_count * 2), filter=('has_image', True)) +
                fetch_posts('aiPosts', limit=(human_count * 4), filter=('has_video', True)) +
                fetch_posts('aiPosts', limit=(human_count // 2), or_filter=[('has_image', False), ('has_video', False)])
            )

            reposts_all = fetch_posts('reposts')

            print(f"Total posts fetched - AI: {len(ai_posts_all)}, Human: {len(human_posts_all)}, Reposts: {len(reposts_all)}")

            # Separate Posts by Type
            def separate_posts(posts):
                text_posts = [p for p in posts if not p.get("has_video") and not p.get("has_image")]
                video_posts = [p for p in posts if p.get("has_video")]
                image_posts = [p for p in posts if p.get("has_image")]
                return text_posts, video_posts, image_posts

            ai_text, ai_video, ai_image = separate_posts(ai_posts_all)
            human_text, human_video, human_image = separate_posts(human_posts_all)

            print(f"Separated posts - AI: Text={len(ai_text)}, Video={len(ai_video)}, Image={len(ai_image)}")
            print(f"Separated posts - Human: Text={len(human_text)}, Video={len(human_video)}, Image={len(human_image)}")

            # Assign Post Types
            for post in ai_text + ai_video + ai_image:
                post['post_type'] = 'ai_post'
            for post in human_text + human_video + human_image:
                post['post_type'] = 'human_post'
            for post in reposts_all:
                post['post_type'] = 'repost'

            # Combine all posts
            all_posts = human_posts_all + reposts_all + ai_posts_all

            # Compute scores for all posts
            for post in all_posts:
                post['final_score'] = compute_final_score(post)

            # Sort Posts by Final Score
            sorted_posts = sorted(all_posts, key=lambda x: x['final_score'], reverse=True)
            print(f"Posts after sorting: {len(sorted_posts)}")

            # Deduplication
            seen_ids = set()
            unique_posts = []
            for post in sorted_posts:
                post_id = post.get('id')
                if post_id and post_id not in seen_ids:
                    unique_posts.append(post)
                    seen_ids.add(post_id)
            print(f"Unique posts after deduplication: {len(unique_posts)}")

            random.shuffle(unique_posts)
            offset = (page - 1) * posts_per_page
            final_feed = unique_posts[offset:offset + posts_per_page]

            # Count post types in final feed
            post_types = {'ai_post': 0, 'human_post': 0, 'repost': 0}
            media_types = {'text': 0, 'video': 0, 'image': 0}
            for post in final_feed:
                post_types[post.get('post_type', 'unknown')] += 1
                if post.get('has_video'):
                    media_types['video'] += 1
                elif post.get('has_image'):
                    media_types['image'] += 1
                else:
                    media_types['text'] += 1

            print(f"Final feed composition:")
            print(f"Post types: {post_types}")
            print(f"Media types: {media_types}")
            print(f"Total posts in feed: {len(final_feed)}")
            print(f"Showing posts {offset + 1} to {offset + len(final_feed)} of {len(unique_posts)} total unique posts")

            return jsonify({'posts': final_feed}), 200

        except Exception as ex:
            print(f"Error generating posts flow: {ex}")
            return jsonify({"success": False, "error": str(ex)}), 500

    @staticmethod
    def test_feed_quality(user_id: str, page: int = 1, pages_to_test: int = 10) -> tuple:
        """Test feed quality across multiple pages to detect duplicates and issues"""
        try:
            from flask import current_app as app

            all_posts = []
            seen_post_ids = set()
            seen_content_hashes = set()

            post_occurrences = {}
            post_locations = {}

            issues = {
                "repeating_posts": [],
                "consecutive_user_posts": [],
                "cross_page_duplicates": [],
                "content_duplicates": []
            }

            session_headers = {
                'User-Agent': 'TestFeedQuality/1.0',
                'X-Test-Session-ID': str(uuid.uuid4())
            }

            # Collect posts from multiple pages
            for p in range(page, page + pages_to_test):
                print(f"Testing page {p}...")
                with app.test_client() as client:
                    response = client.get(
                        f"/feed/posts-flow?user_id={user_id}&page={p}",
                        headers=session_headers
                    )

                    if response.status_code == 200:
                        try:
                            response_data = response.json

                            page_posts = response_data.get('posts', [])
                            if not isinstance(page_posts, list):
                                return jsonify({
                                    "error": "Posts data is not a list",
                                    "details": page_posts
                                }), 500

                            print(f"Collected {len(page_posts)} posts from page {p}")

                            for post in page_posts:
                                if not isinstance(post, dict):
                                    continue

                                post_id = post.get('id')
                                if not post_id:
                                    continue

                                if post_id in post_occurrences:
                                    post_occurrences[post_id] += 1
                                else:
                                    post_occurrences[post_id] = 1

                                if post_id in post_locations:
                                    post_locations[post_id].append(p)
                                else:
                                    post_locations[post_id] = [p]

                                content_fields = []
                                if post.get('post_text'):
                                    content_fields.append(post.get('post_text'))
                                if post.get('post', {}).get('video_content'):
                                    video_content = post.get('post', {}).get('video_content')
                                    if isinstance(video_content, list) and len(video_content) > 0:
                                        content_fields.append(str(video_content[0]))
                                    elif isinstance(video_content, dict) and video_content.get('url'):
                                        content_fields.append(video_content.get('url'))
                                if post.get('post', {}).get('image_content'):
                                    image_content = post.get('post', {}).get('image_content')
                                    if isinstance(image_content, list) and len(image_content) > 0:
                                        content_fields.append(str(image_content[0]))
                                    elif isinstance(image_content, dict) and image_content.get('url'):
                                        content_fields.append(image_content.get('url'))

                                if content_fields:
                                    content_hash = hashlib.md5(''.join(content_fields).encode()).hexdigest()

                                    if content_hash in seen_content_hashes:
                                        issues["content_duplicates"].append({
                                            "post_id": post_id,
                                            "username": post.get('user_name', 'unknown'),
                                            "page": p,
                                            "content_hash": content_hash
                                        })
                                    seen_content_hashes.add(content_hash)

                                all_posts.append(post)

                        except ValueError as e:
                            return jsonify({"error": f"Invalid JSON response: {str(e)}"}), 500
                    else:
                        return jsonify({"error": f"Failed to fetch page {p}"}), 500

            # Process post occurrences
            for post_id, count in post_occurrences.items():
                if count > 1:
                    matching_posts = [p for p in all_posts if p.get('id') == post_id]
                    if matching_posts:
                        post = matching_posts[0]
                        issues["repeating_posts"].append({
                            "post_id": post_id,
                            "username": post.get('user_name', 'unknown'),
                            "count": count,
                            "pages": post_locations.get(post_id, [])
                        })

            # Test for consecutive posts by same user
            for i in range(1, len(all_posts)):
                if not isinstance(all_posts[i], dict) or not isinstance(all_posts[i - 1], dict):
                    continue
                current_username = all_posts[i].get('user_name')
                prev_username = all_posts[i - 1].get('user_name')

                if current_username and current_username == prev_username:
                    issues["consecutive_user_posts"].append({
                        "username": current_username,
                        "post_ids": [all_posts[i - 1].get('id'), all_posts[i].get('id')]
                    })

            # Test for cross-page duplicates
            for post_id, pages in post_locations.items():
                if len(pages) > 1:
                    matching_posts = [p for p in all_posts if p.get('id') == post_id]
                    if matching_posts:
                        post = matching_posts[0]
                        issues["cross_page_duplicates"].append({
                            "post_id": post_id,
                            "username": post.get('user_name', 'unknown'),
                            "duplicate_pages": pages
                        })

            # Collect statistics
            stats = {
                "total_posts_analyzed": len(all_posts),
                "unique_post_ids": len(post_occurrences),
                "unique_content_hashes": len(seen_content_hashes),
                "unique_users": len(set(post.get('user_name') for post in all_posts if isinstance(post, dict) and post.get('user_name'))),
                "pages_analyzed": pages_to_test,
                "repeating_posts_count": len(issues["repeating_posts"]),
                "consecutive_user_posts_count": len(issues["consecutive_user_posts"]),
                "cross_page_duplicates_count": len(issues["cross_page_duplicates"]),
                "content_duplicates_count": len(issues["content_duplicates"])
            }

            print(f"Feed quality test results: {stats}")

            pages_inventory = {}
            for post_id, pages in post_locations.items():
                for page_num in pages:
                    if page_num not in pages_inventory:
                        pages_inventory[page_num] = []
                    pages_inventory[page_num].append(post_id)

            return jsonify({
                "stats": stats,
                "issues": issues,
                "pages_inventory": pages_inventory
            }), 200
        except Exception as ex:
            logger.error("Error testing feed quality: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    @staticmethod
    def update_post(data: Dict[str, Any]) -> tuple:
        """Update a post"""
        try:
            post_id = data.get("PostId")

            if not post_id:
                return jsonify({"success": False, "error": "PostId is required", "code": "INVALID_POST_ID"}), 400

            update_data = {
                "content": data.get("Content"),
                "imageUrl": data.get("ImageUrl"),
                "updatedAt": firestore.SERVER_TIMESTAMP
            }

            collections = ['aiPosts', 'humanPosts', 'reposts']
            post_found = False

            for collection in collections:
                post_ref = db.collection(collection).document(post_id)
                post_doc = post_ref.get()

                if post_doc.exists:
                    post_ref.update(update_data)
                    post_found = True
                    break

            if not post_found:
                return jsonify({"success": False, "error": "Post not found", "code": "POST_NOT_FOUND"}), 404

            return jsonify({"success": True}), 200
        except Exception as ex:
            logger.error("Error updating post: %s", ex)
            return jsonify({"success": False, "error": str(ex), "code": "POST_UPDATE_ERROR"}), 500

    @staticmethod
    def write_comment(data: Dict[str, Any]) -> tuple:
        """Write a comment on a post"""
        try:
            post_id = data.get("PostId")
            user_id = data.get("UserId")
            content = data.get("Content")

            comment_data = {
                "postId": post_id,
                "userId": user_id,
                "content": content,
                "createdAt": firestore.SERVER_TIMESTAMP
            }

            doc_ref = db.collection('postComments').add(comment_data)

            # Find the post owner to send notification
            collections = ['humanPosts', 'reposts', 'aiPosts']
            post_author_id = None

            for collection in collections:
                try:
                    post_doc = db.collection(collection).document(post_id).get()
                    if post_doc.exists:
                        post_data = post_doc.to_dict()
                        post_author_id = post_data.get('user_document_id')
                        break
                except Exception as e:
                    continue

            # Create notification for post author (don't notify yourself)
            if post_author_id and post_author_id != user_id:
                try:
                    commenter_username = get_user_name(user_id)

                    notification_data = {
                        'userId': post_author_id,
                        'type': 'comment',
                        'title': 'New Comment',
                        'body': f'{commenter_username} commented on your post',
                        'isRead': False,
                        'createdAt': firestore.SERVER_TIMESTAMP,
                        'data': {
                            'postId': post_id,
                            'commentId': doc_ref[1].id,
                            'commenterId': user_id,
                            'commenterUsername': commenter_username
                        }
                    }

                    db.collection('notifications').add(notification_data)
                    logger.info(f"Comment notification created for user {post_author_id}")

                except Exception as e:
                    logger.error(f"Error creating comment notification: {e}")

            return jsonify({"commentId": doc_ref[1].id}), 200
        except Exception as ex:
            logger.error("Error writing comment: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    @staticmethod
    def get_user_posts(user_id: str) -> tuple:
        """Get posts by a specific user"""
        try:
            # Retrieve user posts from all collections
            collections = ['humanPosts', 'reposts']
            posts = []

            for collection in collections:
                query = db.collection(collection).where("user_document_id", "==", user_id).limit(25)
                snapshot = query.stream()
                posts.extend([doc.to_dict() for doc in snapshot])

            posts.sort(key=lambda x: x['date_posted'], reverse=True)

            return jsonify(posts[:25]), 200
        except Exception as ex:
            logger.error("Error getting user posts: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    @staticmethod
    def get_ai_posts(username: str) -> tuple:
        """Get posts by a specific AI user"""
        try:
            collection = 'aiPosts'
            posts = []

            query = db.collection(collection).where("user_name", "==", username).limit(25)
            snapshot = query.stream()
            posts.extend([doc.to_dict() for doc in snapshot])

            posts.sort(key=lambda x: x['date_posted'], reverse=True)

            return jsonify(posts[:25]), 200
        except Exception as ex:
            logger.error("Error getting AI user posts: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500
