# services/ai/data_maintenance_service.py
import logging

logger = logging.getLogger(__name__)


class AIDataMaintenanceService:
    """Service for AI data maintenance operations - cleanup and migration"""

    def __init__(self, db):
        """
        Initialize the data maintenance service

        Args:
            db: Firestore database instance
        """
        self.db = db

    def debug_comments(self) -> tuple:
        """
        Debug the structure of comments in postComments collection

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            logger.info("Starting comment collection debug")

            # Count documents in postComments collection
            comments_docs = list(self.db.collection('postComments').limit(500).stream())
            logger.info(f"Found {len(comments_docs)} documents in postComments collection")

            # Analyze structure
            ai_comments_wrong = 0
            human_comments_proper = 0
            mixed_docs = 0
            unknown_structure = 0

            for doc in comments_docs:
                doc_data = doc.to_dict()
                doc_id = doc.id

                # Check if this is an AI comment with wrong structure (individual document)
                if 'isAIGenerated' in doc_data or 'is_ai' in doc_data or 'aiUserName' in doc_data:
                    ai_comments_wrong += 1
                    logger.info(f"AI comment doc {doc_id}: {doc_data.get('content', 'No content')}")

                # Check if this is proper structure (has comments array)
                elif 'comments' in doc_data:
                    comments_array = doc_data.get('comments', [])
                    has_ai = any(comment.get('isAIGenerated') or comment.get('is_ai') for comment in comments_array if isinstance(comment, dict))
                    if has_ai:
                        mixed_docs += 1
                    else:
                        human_comments_proper += 1
                else:
                    unknown_structure += 1
                    logger.info(f"Unknown structure doc {doc_id}: {doc_data}")

            return {
                'success': True,
                'total_docs': len(comments_docs),
                'ai_comments_wrong_structure': ai_comments_wrong,
                'human_comments_proper_structure': human_comments_proper,
                'mixed_docs_with_ai_comments': mixed_docs,
                'unknown_structure': unknown_structure
            }, 200

        except Exception as e:
            logger.error(f"Error debugging comments: {e}")
            return {'success': False, 'error': str(e)}, 500

    def cleanup_incorrect_ai_comments(self) -> tuple:
        """
        Remove all AI comments that were incorrectly stored as separate documents
        instead of being added to the comments array of the post document.

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            logger.info("Starting cleanup of incorrectly structured AI comments")

            # Get all documents from postComments collection
            comments_docs = list(self.db.collection('postComments').stream())
            logger.info(f"Found {len(comments_docs)} total documents in postComments collection")

            deleted_count = 0
            kept_count = 0
            errors = []

            for doc in comments_docs:
                try:
                    doc_data = doc.to_dict()
                    doc_id = doc.id

                    # Check if this is an AI comment with wrong structure (individual document)
                    is_ai_comment = (
                        doc_data.get('isAIGenerated') == True or
                        doc_data.get('is_ai') == True or
                        'aiUserName' in doc_data
                    )

                    # Check if this is the correct structure (has comments array)
                    has_comments_array = 'comments' in doc_data

                    if is_ai_comment and not has_comments_array:
                        # This is an incorrectly structured AI comment - delete it
                        logger.info(f"Deleting incorrect AI comment doc {doc_id}: {doc_data.get('content', 'No content')}")
                        self.db.collection('postComments').document(doc_id).delete()
                        deleted_count += 1
                    else:
                        # This is either a proper structure or human comment - keep it
                        kept_count += 1

                except Exception as e:
                    error_msg = f"Error processing document {doc_id}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)

            result = {
                'success': True,
                'total_documents_processed': len(comments_docs),
                'incorrect_ai_comments_deleted': deleted_count,
                'correct_documents_kept': kept_count,
                'errors': errors
            }

            logger.info(f"Cleanup completed: {result}")
            return result, 200

        except Exception as e:
            logger.error(f"Error during AI comments cleanup: {e}")
            return {'success': False, 'error': str(e)}, 500

    def migrate_post_likes(self) -> tuple:
        """
        Migrate all documents from post_likes collection to postLikes collection

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            logger.info("Starting migration from post_likes to postLikes collection")

            # Get all documents from post_likes collection
            post_likes_docs = list(self.db.collection('post_likes').stream())
            logger.info(f"Found {len(post_likes_docs)} documents in post_likes collection")

            if len(post_likes_docs) == 0:
                return {
                    'success': True,
                    'message': 'No documents found in post_likes collection',
                    'migrated_count': 0
                }, 200

            migrated_count = 0
            errors = []

            # Migrate each document
            for doc in post_likes_docs:
                try:
                    doc_data = doc.to_dict()
                    doc_id = doc.id

                    # Add to new postLikes collection with same document ID
                    self.db.collection('postLikes').document(doc_id).set(doc_data)

                    # Delete from old post_likes collection
                    self.db.collection('post_likes').document(doc_id).delete()

                    migrated_count += 1
                    logger.info(f"Migrated document {doc_id}")

                except Exception as e:
                    error_msg = f"Error migrating document {doc_id}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)

            result = {
                'success': True,
                'total_documents_found': len(post_likes_docs),
                'migrated_count': migrated_count,
                'errors': errors
            }

            logger.info(f"Migration completed: {result}")
            return result, 200

        except Exception as e:
            logger.error(f"Error during post_likes migration: {e}")
            return {'success': False, 'error': str(e)}, 500

    def verify_post_likes_migration(self) -> tuple:
        """
        Verify the migration by checking both collections

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            # Count documents in old collection
            old_collection_docs = list(self.db.collection('post_likes').limit(10).stream())
            old_count = len(old_collection_docs)

            # Count documents in new collection
            new_collection_docs = list(self.db.collection('postLikes').limit(500).stream())
            new_count = len(new_collection_docs)

            return {
                'success': True,
                'old_collection_post_likes_count': old_count,
                'new_collection_postLikes_count': new_count,
                'migration_needed': old_count > 0
            }, 200

        except Exception as e:
            logger.error(f"Error verifying migration: {e}")
            return {'success': False, 'error': str(e)}, 500
