"""
Resume reclassification from where it was interrupted

This script only processes posts that don't have subCategories yet
"""

import sys
import time
from datetime import datetime
from collections import Counter
from dependencies import db
from services.content.multimodal_classifier import MultimodalCategoryClassifier

def resume_reclassification():
    """
    Resume reclassification - only process posts without subCategories
    """
    print("\n" + "="*70)
    print("🔄 RESUME RECLASSIFICATION")
    print("="*70)
    print("This will process only posts that don't have subCategories yet\n")
    
    response = input("Type 'yes' to continue: ")
    if response.lower() != 'yes':
        print("❌ Cancelled")
        return
    
    collections = ['humanPosts', 'aiPosts']
    
    for collection_name in collections:
        print("\n" + "="*70)
        print(f"CHECKING: {collection_name}")
        print("="*70 + "\n")
        
        # Get ALL posts and filter in Python (simpler and more reliable)
        all_posts = list(db.collection(collection_name).stream())
        
        # Filter posts WITHOUT subCategories
        posts_list = []
        for post_doc in all_posts:
            post_data = post_doc.to_dict()
            subcats = post_data.get('subCategories')
            if subcats is None or len(subcats) == 0:
                posts_list.append(post_doc)
        
        total_remaining = len(posts_list)
        
        if total_remaining == 0:
            print(f"✅ All {collection_name} already classified! Nothing to do.\n")
            continue
        
        print(f"📊 Found {total_remaining} posts still need classification")
        print(f"⏱️  Estimated time: {total_remaining * 2 / 60:.1f} minutes\n")
        
        # Process in batches
        batch_size = 100
        processed = 0
        updated = 0
        errors = 0
        
        for i in range(0, total_remaining, batch_size):
            batch_posts = posts_list[i:i+batch_size]
            print(f"\n📦 Processing batch {i//batch_size + 1} ({len(batch_posts)} posts)...")
            
            for post_doc in batch_posts:
                try:
                    post_data = post_doc.to_dict()
                    post_id = post_doc.id
                    processed += 1
                    
                    # Classify
                    result = MultimodalCategoryClassifier.classify_post(post_data)
                    
                    # Update Firestore
                    db.collection(collection_name).document(post_id).update({
                        'subCategories': result['subCategories'],
                        'masterCategories': result['masterCategories'],
                        'reclassified_at': datetime.utcnow(),
                        'classifier_version': 'multimodal_v1.0'
                    })
                    
                    updated += 1
                    
                    if processed % 50 == 0:
                        print(f"   Progress: {processed}/{total_remaining} ({updated} updated)")
                    
                except Exception as e:
                    errors += 1
                    print(f"   ❌ Error on post {post_id}: {e}")
            
            # Pause between batches
            if i + batch_size < total_remaining:
                print(f"   ⏸️  Pausing 2 seconds...")
                time.sleep(2)
        
        print(f"\n✅ {collection_name} complete!")
        print(f"   Processed: {processed}")
        print(f"   Updated: {updated}")
        print(f"   Errors: {errors}")
    
    print("\n" + "="*70)
    print("🎉 RESUME COMPLETE!")
    print("="*70 + "\n")


if __name__ == '__main__':
    try:
        resume_reclassification()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user. You can run this script again to resume.")
        sys.exit(1)
