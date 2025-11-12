# services/content/category_service.py
from dependencies import db
import logging

logger = logging.getLogger(__name__)

class CategoryService:
    """Service for category and topic mapping"""

    TOPIC_TO_CATEGORY_MAP = {}

    @staticmethod
    def initialize_category_mapping():
        """Load topic-to-category mapping from Firestore"""
        print("\n" + "="*70)
        print("Master Categories System Ready")
        print("Post labeling uses OpenAI to directly generate master category labels")
        print("="*70 + "\n")

        # Load topic-to-category mapping from Firestore for user interests
        print("Loading topic-to-category mapping from Firestore...")

        try:
            doc_ref = db.collection('content').document('categories')
            doc = doc_ref.get()

            if doc.exists:
                data = doc.to_dict()
                categories = data.get('categories', {})

                for category_name, topics in categories.items():
                    if isinstance(topics, list):
                        # Remove emoji and normalize the category name
                        # Keep only basic ASCII alphanumeric and spaces/ampersands
                        category_no_emoji = ''.join(char for char in category_name if ord(char) < 128 or char.isalpha())
                        category_no_emoji = category_no_emoji.strip()

                        # Normalize: lowercase, replace separators, remove special chars, strip underscores
                        normalized_category = category_no_emoji.lower()
                        normalized_category = normalized_category.replace(' & ', '_').replace('&', '_')
                        normalized_category = normalized_category.replace(' ', '_').replace('-', '_')
                        normalized_category = normalized_category.replace(',', '').replace('.', '')
                        # Remove any consecutive underscores and strip leading/trailing underscores
                        while '__' in normalized_category:
                            normalized_category = normalized_category.replace('__', '_')
                        normalized_category = normalized_category.strip('_')

                        for topic in topics:
                            topic_key = str(topic).lower().strip()
                            CategoryService.TOPIC_TO_CATEGORY_MAP[topic_key] = normalized_category

                print(f"✓ Loaded {len(CategoryService.TOPIC_TO_CATEGORY_MAP)} topic mappings from {len(categories)} categories")
            else:
                print("⚠ Warning: No categories document found in Firestore")
        except Exception as e:
            print(f"⚠ Warning: Failed to load topic mapping: {e}")
            logger.error(f"Failed to load topic mapping: {e}")

        print("="*70 + "\n")

        return CategoryService.TOPIC_TO_CATEGORY_MAP
