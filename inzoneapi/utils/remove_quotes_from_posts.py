#!/usr/bin/env python3
"""
Script to remove quotation marks from text_content field in aiPosts documents.
This will strip leading/trailing quotes and escaped quotes from post content.
"""

import firebase_admin
from firebase_admin import credentials, firestore
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

def initialize_firebase():
    """Initialize Firebase Admin SDK"""
    try:
        # Check if already initialized
        firebase_admin.get_app()
        print("Firebase already initialized")
    except ValueError:
        # Initialize with service account
        key_path = Path(__file__).parent.parent / 'key.json'
        if not key_path.exists():
            print(f"Error: Firebase key not found at {key_path}")
            sys.exit(1)
        
        cred = credentials.Certificate(str(key_path))
        firebase_admin.initialize_app(cred)
        print("Firebase initialized successfully")

def clean_text_content(text):
    if not text or not isinstance(text, str):
        return text
    
    original = text
    
    # Strip leading and trailing whitespace first
    text = text.strip()
    
    # Remove leading/trailing quote pairs
    # Handle double quotes
    if text.startswith('"') and text.endswith('"') and len(text) > 1:
        text = text[1:-1]
    
    # Handle single quotes
    if text.startswith("'") and text.endswith("'") and len(text) > 1:
        text = text[1:-1]
    
    # Remove escaped quotes
    text = text.replace('\\"', '"').replace("\\'", "'")
    
    # Only return modified text if it actually changed
    return text if text != original else original

def remove_quotes_from_posts(dry_run=True, batch_size=500):
    """
    Remove quotation marks from text_content in all aiPosts documents.
    
    Args:
        dry_run: If True, only preview changes without modifying
        batch_size: Number of documents to process per batch
    """
    db = firestore.client()
    
    print(f"\n{'='*60}")
    print(f"Starting aiPosts quote removal {'(DRY RUN)' if dry_run else '(LIVE UPDATE)'}")
    print(f"{'='*60}\n")
    
    # Get all aiPosts
    posts_ref = db.collection('aiPosts')
    
    total_posts = 0
    modified_posts = 0
    error_posts = 0
    
    # Process in batches
    last_doc = None
    batch_count = 0
    
    while True:
        batch_count += 1
        print(f"\nProcessing batch {batch_count}...")
        
        # Build query
        query = posts_ref.limit(batch_size)
        if last_doc:
            query = query.start_after(last_doc)
        
        docs = query.stream()
        docs_list = list(docs)
        
        if not docs_list:
            print("No more documents to process")
            break
        
        for doc in docs_list:
            total_posts += 1
            doc_id = doc.id
            data = doc.to_dict()
            
            # Get the post field
            post_field = data.get('post', {})
            if not post_field or not isinstance(post_field, dict):
                continue
            
            text_content = post_field.get('text_content', '')
            if not text_content:
                continue
            
            # Clean the text content
            cleaned_text = clean_text_content(text_content)
            
            # Check if text was modified
            if cleaned_text != text_content:
                modified_posts += 1
                
                print(f"\n[{modified_posts}] Document: {doc_id}")
                print(f"  BEFORE: {text_content[:100]}{'...' if len(text_content) > 100 else ''}")
                print(f"  AFTER:  {cleaned_text[:100]}{'...' if len(cleaned_text) > 100 else ''}")
                
                if not dry_run:
                    try:
                        # Update the document
                        db.collection('aiPosts').document(doc_id).update({
                            'post.text_content': cleaned_text
                        })
                        print(f"  ✓ Updated successfully")
                    except Exception as e:
                        error_posts += 1
                        print(f"  ✗ Error updating: {e}")
        
        last_doc = docs_list[-1]
        print(f"Processed {total_posts} posts so far...")
        
        # Safety check - prevent infinite loops
        if batch_count > 1000:
            print("WARNING: Reached maximum batch count (1000). Stopping.")
            break
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Total posts processed: {total_posts}")
    print(f"Posts modified: {modified_posts}")
    print(f"Errors: {error_posts}")
    print(f"Mode: {'DRY RUN (no changes made)' if dry_run else 'LIVE UPDATE (changes saved)'}")
    print(f"{'='*60}\n")
    
    return {
        'total': total_posts,
        'modified': modified_posts,
        'errors': error_posts
    }

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Remove quotation marks from text_content in aiPosts'
    )
    parser.add_argument(
        '--live',
        action='store_true',
        help='Actually update the database (default is dry-run)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=500,
        help='Number of documents to process per batch (default: 500)'
    )
    
    args = parser.parse_args()
    
    # Initialize Firebase
    initialize_firebase()
    
    # Run the script
    dry_run = not args.live
    
    if not dry_run:
        response = input("\n⚠️  WARNING: You are about to modify the database. Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted.")
            return
    
    results = remove_quotes_from_posts(dry_run=dry_run, batch_size=args.batch_size)
    
    if dry_run and results['modified'] > 0:
        print("\n💡 To apply these changes, run with --live flag:")
        print(f"   python {Path(__file__).name} --live")

if __name__ == '__main__':
    main()
