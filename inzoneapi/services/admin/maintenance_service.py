# services/admin/maintenance_service.py
import logging

logger = logging.getLogger(__name__)


class AdminMaintenanceService:
    """Service for admin maintenance operations"""

    @staticmethod
    def fix_missing_uid(db) -> tuple:
        """
        Fix humanUsers documents that are missing the 'uid' field

        Args:
            db: Firestore database instance

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            logger.info("Starting UID fix process...")

            # Get all documents from humanUsers collection
            users_ref = db.collection('humanUsers')
            docs = users_ref.stream()

            updated_count = 0
            total_count = 0
            errors = []

            for doc in docs:
                total_count += 1
                doc_data = doc.to_dict()
                doc_id = doc.id

                # Check if the document is missing the 'uid' field entirely
                if 'uid' not in doc_data:
                    logger.info(f"Found user without UID field: {doc_id}")

                    # Update the document to set uid = document_id
                    try:
                        users_ref.document(doc_id).update({
                            'uid': doc_id
                        })
                        updated_count += 1
                        logger.info(f"Updated user {doc_id} - set uid to {doc_id}")

                    except Exception as e:
                        error_msg = f"Failed to update user {doc_id}: {e}"
                        logger.error(error_msg)
                        errors.append(error_msg)

            # Verify the fix
            verification_docs = users_ref.stream()
            missing_uid_count = 0
            verification_total = 0

            for doc in verification_docs:
                verification_total += 1
                doc_data = doc.to_dict()
                if 'uid' not in doc_data:
                    missing_uid_count += 1

            logger.info(f"UID fix process completed:")
            logger.info(f"Total users processed: {total_count}")
            logger.info(f"Users updated: {updated_count}")
            logger.info(f"Users still missing UID after fix: {missing_uid_count}")

            return {
                "success": True,
                "message": "UID fix process completed",
                "data": {
                    "total_processed": total_count,
                    "updated": updated_count,
                    "already_had_uid": total_count - updated_count,
                    "still_missing_uid": missing_uid_count,
                    "errors": errors
                }
            }, 200

        except Exception as ex:
            logger.error("Error during UID fix process: %s", ex)
            return {"success": False, "error": str(ex)}, 500
