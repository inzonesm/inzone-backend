"""
Batch Reclassify All Posts Using MultimodalCategoryClassifier

This script processes all human and AI posts and assigns:
1. subCategories: 1-4 specific subcategories
2. masterCategories: Auto-mapped master categories

Features:
- Pagination to avoid Firestore timeouts
- Text-first strategy (cheap)
- Vision analysis for vague/missing text + media (accurate)
- Batch processing with rate limiting
"""

import sys
import time
from datetime import datetime
from collections import Counter
from dependencies import db
from services.content.multimodal_classifier import MultimodalCategoryClassifier

def reclassify_sample(collection_name='humanPosts', limit=5, use_vision=True):
    """
    Reclassify a sample of posts for testing
    
    Args:
        collection_name: 'humanPosts' or 'aiPosts'
        limit: Number of posts to sample
        use_vision: Whether to use vision analysis (multimodal) or text-only
    """
    print("\n" + "="*70)
    print(f"SAMPLE RECLASSIFICATION: {collection_name}")
    print("="*70)
    print(f"Mode: {'Multimodal (text + vision)' if use_vision else 'Text-only'}")
    print(f"Sample size: {limit}\n")
    
    posts = db.collection(collection_name).limit(limit).stream()
    
    count = 0
    for post_doc in posts:
        count += 1
        post_data = post_doc.to_dict()
        post_id = post_doc.id
        
        # Get post content
        post_field = post_data.get('post', {})
        text = post_field.get('text_content', '')
        images = [img for img in post_field.get('image_content', []) if img and img.strip()]
        videos = [vid for vid in post_field.get('video_content', []) if vid and vid.strip()]
        
        # Get current categories
        current_master = post_data.get('masterCategories', [])
        current_sub = post_data.get('subCategories', [])
        
        print(f"\n{count}. Post ID: {post_id}")
        print(f"   Text: {text[:60] if text else '(no text)'}...")
        print(f"   📷 Media: {len(images)} images, {len(videos)} videos")
        print(f"   Current:")
        print(f"     masterCategories: {current_master}")
        print(f"     subCategories: {current_sub if current_sub else '(none)'}")
        
        # Classify with verbose output
        print(f"   🔍 Classifying...")
        start_time = time.time()
        result = MultimodalCategoryClassifier.classify_post(post_data, verbose=True)
        elapsed = time.time() - start_time
        
        print(f"   🤖 AI Result (took {elapsed:.2f}s):")
        print(f"     Method: {result.get('method', 'unknown')}")
        print(f"     subCategories: {result['subCategories']}")
        print(f"     masterCategories: {result['masterCategories']}")
        
        if set(current_master) != set(result['masterCategories']) or set(current_sub) != set(result['subCategories']):
            print(f"   → Would change: YES ✅")
        else:
            print(f"   → Would change: NO ⏭️")

def reclassify_all_posts(dry_run=True, batch_size=100):
    """
    Reclassify all human and AI posts
    
    Args:
        dry_run: If True, only show changes without updating
        batch_size: Number of posts to process per batch
    """
    print("\n" + "="*70)
    print("BATCH RECLASSIFICATION - ALL POSTS")
    print("="*70)
    print(f"Mode: {'DRY RUN (no changes)' if dry_run else 'LIVE UPDATE'}")
    print(f"Batch size: {batch_size}\n")
    
    collections = ['humanPosts', 'aiPosts']
    
    # Overall statistics
    grand_total_processed = 0
    grand_total_updated = 0
    grand_total_errors = 0
    
    for collection_name in collections:
        print("\n" + "="*70)
        print(f"PROCESSING: {collection_name}")
        print("="*70 + "\n")
        
        # Collection statistics
        total_processed = 0
        total_updated = 0
        total_errors = 0
        
        # Category statistics
        sub_category_counts = Counter()
        master_category_counts = Counter()
        
        # Pagination
        last_doc = None
        batch_num = 0
        
        while True:
            batch_num += 1
            print(f"\n📦 Batch {batch_num} ({collection_name})...")
            
            # Query with pagination
            if last_doc:
                query = db.collection(collection_name).order_by('__name__').start_after(last_doc).limit(batch_size)
            else:
                query = db.collection(collection_name).order_by('__name__').limit(batch_size)
            
            posts = list(query.stream())
            
            if not posts:
                print("   No more posts to process.")
                break
            
            for post_doc in posts:
                try:
                    post_data = post_doc.to_dict()
                    post_id = post_doc.id
                    
                    # Get current categories
                    current_master = post_data.get('masterCategories', [])
                    current_sub = post_data.get('subCategories', [])
                    
                    # Classify
                    result = MultimodalCategoryClassifier.classify_post(post_data)
                    new_sub = result.get('subCategories', [])
                    new_master = result.get('masterCategories', [])
                    
                    # Track category usage
                    for cat in new_sub:
                        sub_category_counts[cat] += 1
                    for cat in new_master:
                        master_category_counts[cat] += 1
                    
                    total_processed += 1
                    
                    # Check if changed
                    if set(current_master) != set(new_master) or set(current_sub) != set(new_sub):
                        total_updated += 1
                        
                        if not dry_run:
                            # Actually update
                            db.collection(collection_name).document(post_id).update({
                                'subCategories': new_sub,
                                'masterCategories': new_master,
                                'reclassified_at': datetime.now(),
                                'classifier_version': '2.0',
                                'classification_method': 'multimodal_ai'
                            })
                    
                    # Progress indicator
                    if total_processed % 50 == 0:
                        print(f"   Processed {total_processed} posts... ({total_updated} updated)")
                    
                except Exception as e:
                    print(f"   ❌ Error processing post {post_id}: {e}")
                    total_errors += 1
                    continue
            
            # Update pagination cursor
            if posts:
                last_doc = posts[-1]
            
            # Rate limiting
            if not dry_run:
                print(f"   ⏸️  Pausing 2 seconds...")
                time.sleep(2)
        
        # Collection summary
        print("\n" + "="*70)
        print(f"SUMMARY: {collection_name}")
        print("="*70)
        print(f"Total processed: {total_processed}")
        print(f"Total updated: {total_updated}")
        print(f"Total errors: {total_errors}")
        
        print(f"\nTop 10 SubCategories:")
        for cat, count in sub_category_counts.most_common(10):
            print(f"  {cat}: {count}")
        
        print(f"\nTop 10 MasterCategories:")
        for cat, count in master_category_counts.most_common(10):
            print(f"  {cat}: {count}")
        
        grand_total_processed += total_processed
        grand_total_updated += total_updated
        grand_total_errors += total_errors
    
    # Grand summary
    print("\n" + "="*70)
    print("GRAND SUMMARY - ALL COLLECTIONS")
    print("="*70)
    print(f"Total posts processed: {grand_total_processed}")
    print(f"Total posts updated: {grand_total_updated}")
    print(f"Total errors: {grand_total_errors}")
    print(f"Success rate: {(grand_total_processed - grand_total_errors) / grand_total_processed * 100:.1f}%")
    print("="*70 + "\n")


if __name__ == '__main__':
    import sys
    
    print("\n🤖 Multimodal AI Post Reclassification")
    print("="*70)
    
    if '--help' in sys.argv or '-h' in sys.argv:
        print("""
Usage:
  python reclassify_all_posts.py [OPTIONS]

Options:
  --sample                    Preview 5 posts without making changes
  --sample --limit N          Preview N posts
  --sample --collection NAME  Preview from specific collection (humanPosts/aiPosts)
  --dry-run                   Show all changes without updating database
  --live                      Actually update the database (requires confirmation)

Examples:
  python reclassify_all_posts.py --sample
  python reclassify_all_posts.py --sample --limit 10
  python reclassify_all_posts.py --sample --collection aiPosts
  python reclassify_all_posts.py --dry-run
  python reclassify_all_posts.py --live
        """)
        sys.exit(0)
    
    if '--sample' in sys.argv:
        # Sample mode
        limit = 5
        collection = 'humanPosts'
        
        if '--limit' in sys.argv:
            try:
                limit_idx = sys.argv.index('--limit') + 1
                limit = int(sys.argv[limit_idx])
            except (ValueError, IndexError):
                print("⚠️  Invalid --limit value, using default: 5")
        
        if '--collection' in sys.argv:
            try:
                coll_idx = sys.argv.index('--collection') + 1
                collection = sys.argv[coll_idx]
            except IndexError:
                print("⚠️  Invalid --collection value, using default: humanPosts")
        
        reclassify_sample(collection_name=collection, limit=limit)
    
    elif '--dry-run' in sys.argv:
        # Dry run - show all changes
        print("\n📊 Running dry run (no database changes)...\n")
        reclassify_all_posts(dry_run=True)
    
    elif '--live' in sys.argv:
        # Live update - requires confirmation
        print("\n⚠️  WARNING: This will update all posts in the database!")
        print("Strategy: Multimodal AI classification (text + vision)")
        print("Fields added: subCategories, masterCategories")
        confirm = input("\nType 'yes' to proceed: ")
        
        if confirm.lower() == 'yes':
            print("\n🚀 Starting LIVE reclassification...\n")
            reclassify_all_posts(dry_run=False)
        else:
            print("❌ Cancelled.")
    
    else:
        # Default: show sample
        print("\n💡 Tip: Use --help to see all options\n")
        reclassify_sample(limit=5)
