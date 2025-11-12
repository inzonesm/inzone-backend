# services/ai/bulk_engagement_service.py
from flask import jsonify
from google.cloud import firestore
from dependencies import db
import logging
import random

logger = logging.getLogger(__name__)


class AIBulkEngagementService:
    """Service for bulk AI engagement operations"""

    def __init__(self, inzone_ai_service):
        """
        Initialize with InZoneAIEngagementService instance

        Args:
            inzone_ai_service: The InZoneAIEngagementService instance
        """
        self.inzone_ai_service = inzone_ai_service

    def bulk_engage(self, data: dict) -> tuple:
        """
        AI users perform bulk engagement on recent content

        Args:
            data: Dictionary containing max_interactions and engagement_types

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            max_interactions = data.get('max_interactions', 10)
            engagement_types = data.get('engagement_types', ['comment', 'like', 'dm'])

            # Get active AI users
            ai_users_ref = db.collection('aiUsers').limit(50)
            ai_users = []
            for doc in ai_users_ref.stream():
                ai_data = doc.to_dict()
                ai_data['id'] = doc.id
                ai_users.append(ai_data)

            if not ai_users:
                return jsonify({"success": False, "error": "No AI users found"}), 404

            # Get recent posts
            recent_posts = []

            human_posts_ref = db.collection('humanPosts').order_by('date_posted', direction=firestore.Query.DESCENDING).limit(60)
            for doc in human_posts_ref.stream():
                post_data = doc.to_dict()
                post_data['id'] = doc.id
                post_data['collection'] = 'humanPosts'
                recent_posts.append(post_data)

            ai_posts_ref = db.collection('aiPosts').order_by('date_posted', direction=firestore.Query.DESCENDING).limit(40)
            for doc in ai_posts_ref.stream():
                post_data = doc.to_dict()
                post_data['id'] = doc.id
                post_data['collection'] = 'aiPosts'
                recent_posts.append(post_data)

            # Get trending insights
            trends = self.inzone_ai_service.get_trending_content_insights()

            results = {
                'comments': [],
                'likes': [],
                'dms': [],
                'errors': []
            }

            interaction_count = 0
            used_ai_post_combinations = set()

            # Shuffle for variety
            random.shuffle(ai_users)
            random.shuffle(recent_posts)

            for ai_user in ai_users:
                if interaction_count >= max_interactions:
                    break

                ai_user_id = ai_user['id']

                can_interact = self.inzone_ai_service.check_ai_daily_limit(ai_user_id)
                if not can_interact:
                    continue

                # Get posts this AI hasn't interacted with
                available_posts = []
                for post in recent_posts:
                    if post.get('user_name') == ai_user_id or post.get('user_id') == ai_user_id:
                        continue

                    combination_key = f"{ai_user_id}_{post['id']}"
                    if combination_key not in used_ai_post_combinations:
                        available_posts.append(post)

                if not available_posts:
                    continue

                posts_to_engage = random.sample(available_posts, min(3, len(available_posts)))

                for selected_post in posts_to_engage:
                    if interaction_count >= max_interactions:
                        break

                    combination_key = f"{ai_user_id}_{selected_post['id']}"
                    used_ai_post_combinations.add(combination_key)

                    # Weight engagement types
                    engagement_weights = {'like': 0.6, 'comment': 0.3, 'dm': 0.1}
                    available_engagement_types = [et for et in engagement_types if et in engagement_weights]

                    if available_engagement_types:
                        engagement_type = random.choices(
                            available_engagement_types,
                            weights=[engagement_weights[et] for et in available_engagement_types]
                        )[0]
                    else:
                        engagement_type = random.choice(engagement_types)

                    try:
                        if engagement_type == 'comment':
                            comment_content = self.inzone_ai_service.generate_contextual_ai_comment(ai_user, selected_post, trends)

                            comment_data = {
                                "postId": selected_post['id'],
                                "userId": ai_user_id,
                                "content": comment_content,
                                "createdAt": firestore.SERVER_TIMESTAMP,
                                "isAIGenerated": True,
                                "aiUserName": ai_user.get('name', ai_user_id)
                            }

                            doc_ref = db.collection('postComments').add(comment_data)
                            results['comments'].append({
                                'ai_user': ai_user.get('name'),
                                'post_id': selected_post['id'],
                                'comment': comment_content,
                                'comment_id': doc_ref[1].id
                            })

                        elif engagement_type == 'like':
                            existing_like = list(db.collection('postLikes').where('user_id', '==', ai_user_id).where('post_id', '==', selected_post['id']).limit(1).get())
                            if not existing_like:
                                like_data = {
                                    "user_id": ai_user_id,
                                    "post_id": selected_post['id'],
                                    "timestamp": firestore.SERVER_TIMESTAMP,
                                    "isAIGenerated": True
                                }

                                db.collection('postLikes').add(like_data)

                                post_ref = db.collection(selected_post['collection']).document(selected_post['id'])
                                post_ref.update({"likes": firestore.Increment(1)})

                                results['likes'].append({
                                    'ai_user': ai_user.get('name'),
                                    'post_id': selected_post['id'],
                                    'post_author': selected_post.get('user_name')
                                })

                        elif engagement_type == 'dm':
                            target_user_id = selected_post.get('user_document_id') or selected_post.get('user_name')
                            if target_user_id and target_user_id != ai_user_id:

                                target_user_doc = db.collection('humanUsers').document(target_user_id).get()
                                if target_user_doc.exists:
                                    target_user = target_user_doc.to_dict()

                                    participants = sorted([ai_user_id, target_user_id])
                                    conversation_id = f"{participants[0]}_{participants[1]}"

                                    dm_content = self.inzone_ai_service.generate_ai_dm_message(ai_user, target_user)

                                    conversation_ref = db.collection('conversations').document(conversation_id)

                                    new_message = {
                                        'text': dm_content,
                                        'senderId': ai_user_id,
                                        'senderName': ai_user.get('name', ai_user_id),
                                        'timestamp': firestore.SERVER_TIMESTAMP,
                                        'isRead': False,
                                        'isAIGenerated': True
                                    }

                                    conversation_ref.collection('messages').add(new_message)

                                    conversation_ref.set({
                                        'lastMessage': dm_content,
                                        'lastMessageTime': firestore.SERVER_TIMESTAMP,
                                        'participants': [ai_user_id, target_user_id],
                                        'participantNames': {
                                            ai_user_id: ai_user.get('name', ai_user_id),
                                            target_user_id: target_user.get('name', target_user_id)
                                        },
                                        'lastUpdated': firestore.SERVER_TIMESTAMP,
                                        'isAIConversation': True
                                    }, merge=True)

                                    results['dms'].append({
                                        'ai_user': ai_user.get('name'),
                                        'target_user': target_user.get('name'),
                                        'conversation_id': conversation_id,
                                        'message': dm_content
                                    })

                        interaction_count += 1

                    except Exception as e:
                        results['errors'].append({
                            'ai_user': ai_user.get('name'),
                            'error': str(e),
                            'engagement_type': engagement_type
                        })

            return jsonify({
                "success": True,
                "data": {
                    "total_interactions": interaction_count,
                    "results": results,
                    "trending_insights": trends
                }
            }), 200

        except Exception as ex:
            logger.error("Error in bulk AI engagement: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500
