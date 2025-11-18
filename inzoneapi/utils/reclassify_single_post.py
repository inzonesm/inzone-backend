"""
使用多模态 AI 重新分类单个帖子
"""

from dependencies import db
from services.content.multimodal_classifier import MultimodalClassifier

post_id = "GwIQtA6h781N7YYq40IS"

print("\n" + "="*70)
print(f"RECLASSIFYING POST: {post_id}")
print("="*70 + "\n")

# Get the post
doc = db.collection('humanPosts').document(post_id).get()

if doc.exists:
    post_data = doc.to_dict()
    
    # Show current info
    post_field = post_data.get('post', {})
    text = post_field.get('text_content', '')
    images = [img for img in post_field.get('image_content', []) if img and img.strip()]
    videos = [vid for vid in post_field.get('video_content', []) if vid and vid.strip()]
    current_cats = post_data.get('masterCategories', [])
    
    print("📝 CURRENT POST INFO:")
    print(f"   Text: {text}")
    print(f"   Images: {len(images)}")
    for i, img in enumerate(images, 1):
        print(f"      {i}. {img}")
    print(f"   Videos: {len(videos)}")
    print(f"   Current categories: {current_cats}\n")
    
    print("="*70)
    print("ANALYZING WITH MULTIMODAL AI...")
    print("="*70 + "\n")
    
    # Use multimodal classification
    new_cats = MultimodalClassifier.classify_post(post_data)
    
    print(f"🤖 AI SUGGESTED CATEGORIES:")
    print(f"   {new_cats}\n")
    
    print("="*70)
    print("COMPARISON")
    print("="*70 + "\n")
    
    print(f"Before: {current_cats}")
    print(f"After:  {new_cats}")
    print(f"\nWould change: {'YES ✅' if set(current_cats) != set(new_cats) else 'NO'}")
    
    # Ask if user wants to update
    print("\n" + "="*70)
    response = input("\nDo you want to update this post? (yes/no): ").strip().lower()
    
    if response == 'yes':
        from datetime import datetime
        db.collection('humanPosts').document(post_id).update({
            'masterCategories': new_cats,
            'reclassified_at': datetime.now(),
            'reclassified_by': 'ai_multimodal_gpt4o_manual'
        })
        print("✅ Post updated successfully!")
    else:
        print("❌ Update cancelled")
    
else:
    print("❌ Post not found!")

print("\n" + "="*70 + "\n")
