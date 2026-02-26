#!/usr/bin/env python3
"""
Delete Duplicate YouTube Shorts Videos from aiPosts — Firestore + Storage

This script:
1. Scans all documents in 'aiPosts' for duplicate video URLs
2. Keeps the EARLIEST post for each unique video
3. Deletes duplicate Firestore documents
4. Deletes orphaned video files from Firebase Storage that were only
   referenced by the deleted duplicates

Usage:
    python delete_duplicate_videos.py              # dry run (safe preview)
    python delete_duplicate_videos.py --live       # actually delete

"""

import os
import sys
import re
import json
import logging
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from urllib.parse import unquote

os.environ['GRPC_DNS_RESOLVER'] = 'native'
sys.path.insert(0, str(Path(__file__).parent.parent))

import firebase_admin
from firebase_admin import credentials, firestore, storage

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
STORAGE_VIDEO_PATH = 'migrated_videos'
COLLECTION = 'aiPosts'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(message)s',
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Firebase init
# ---------------------------------------------------------------------------

def init_firebase():
    key_path = os.path.join(os.path.dirname(__file__), '..', 'inzoneapi', 'key.json')
    if not os.path.exists(key_path):
        raise FileNotFoundError(f"key.json not found at {key_path}")

    cred = credentials.Certificate(key_path)

    try:
        app = firebase_admin.get_app()
    except ValueError:
        with open(key_path) as f:
            project_id = json.load(f).get('project_id', 'inzone-f93e4')
        app = firebase_admin.initialize_app(cred, {
            'storageBucket': f'{project_id}.appspot.com',
        })

    db = firestore.client()
    bucket = storage.bucket()
    return db, bucket

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_YT_RE = [
    re.compile(r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})'),
    re.compile(r'youtube\.com/embed/([a-zA-Z0-9_-]{11})'),
]


def normalize_video_id(url: str) -> str:
    """Return a canonical ID for a video URL (YouTube ID or full URL)."""
    url = url.strip()
    for pat in _YT_RE:
        m = pat.search(url)
        if m:
            return m.group(1)
    return url


def extract_video_urls(doc_data: dict) -> list[str]:
    """Pull every video URL out of a post document."""
    urls: list[str] = []

    # nested post.video_content
    post = doc_data.get('post')
    if isinstance(post, dict):
        vc = post.get('video_content', [])
        if isinstance(vc, list):
            urls.extend(u for u in vc if isinstance(u, str) and u.strip())
        elif isinstance(vc, str) and vc.strip():
            urls.append(vc)

    # top-level video_content
    vc = doc_data.get('video_content')
    if isinstance(vc, list):
        urls.extend(u for u in vc if isinstance(u, str) and u.strip())
    elif isinstance(vc, str) and vc.strip():
        urls.append(vc)

    # youtube_shorts_links field
    yt = doc_data.get('youtube_shorts_links')
    if isinstance(yt, str) and yt.strip():
        urls.append(yt)

    return urls


def extract_storage_paths(urls: list[str], bucket_name: str) -> list[str]:
    """
    From a list of URLs, return Firebase Storage object paths
    (only for URLs that live in storage, not plain YouTube URLs).
    """
    paths = []
    for url in urls:
        # https://storage.googleapis.com/BUCKET/path/to/file
        prefix1 = f"https://storage.googleapis.com/{bucket_name}/"
        if url.startswith(prefix1):
            paths.append(unquote(url[len(prefix1):]))
            continue

        # https://firebasestorage.googleapis.com/v0/b/BUCKET/o/PATH?…
        prefix2 = f"https://firebasestorage.googleapis.com/v0/b/{bucket_name}/o/"
        if url.startswith(prefix2):
            raw = url[len(prefix2):]
            raw = raw.split('?')[0]           # strip query params
            paths.append(unquote(raw))
            continue

    return paths

# ---------------------------------------------------------------------------
# Phase 1 — discover duplicates
# ---------------------------------------------------------------------------

def discover_duplicates(db):
    log.info("=" * 70)
    log.info("PHASE 1 — Scanning %s for duplicate videos", COLLECTION)
    log.info("=" * 70)

    video_map = defaultdict(list)          # video_id → [doc info, …]
    total = 0
    with_video = 0

    for doc in db.collection(COLLECTION).stream():
        total += 1
        data = doc.to_dict()
        urls = extract_video_urls(data)
        if not urls:
            continue
        with_video += 1
        for url in urls:
            vid = normalize_video_id(url)
            video_map[vid].append({
                'doc_id': doc.id,
                'url': url,
                'all_urls': urls,
                'date_posted': data.get('date_posted'),
                'username': data.get('user_name') or data.get('username') or 'unknown',
            })

    duplicates = {v: ps for v, ps in video_map.items() if len(ps) > 1}
    dup_entries = sum(len(ps) - 1 for ps in duplicates.values())

    log.info("Total posts scanned       : %d", total)
    log.info("Posts with videos          : %d", with_video)
    log.info("Unique videos              : %d", len(video_map))
    log.info("Videos that have duplicates: %d", len(duplicates))
    log.info("Duplicate entries to remove: %d", dup_entries)

    # Show first 20 groups
    for i, (vid, ps) in enumerate(sorted(duplicates.items(), key=lambda x: -len(x[1]))):
        if i >= 20:
            log.info("… and %d more groups", len(duplicates) - 20)
            break
        log.info("  Video %s  ×%d copies", vid[:40], len(ps))
        for p in ps:
            d = str(p['date_posted'])[:19] if p['date_posted'] else 'N/A'
            log.info("      doc=%s  user=%s  date=%s", p['doc_id'], p['username'], d)

    return video_map, duplicates

# ---------------------------------------------------------------------------
# Phase 2 — figure out what to delete
# ---------------------------------------------------------------------------

def plan_deletions(duplicates, bucket_name):
    """
    For each group of duplicates, keep the earliest post.
    Return:
      - doc_ids_to_delete          : list[str]
      - storage_paths_to_delete    : list[str]   (only those exclusively owned by deleted docs)
      - keeper_storage_paths       : set[str]    (paths still referenced by kept docs)
    """
    docs_to_delete: list[str] = []
    urls_to_keep: set[str] = set()
    urls_to_delete: set[str] = set()

    for vid, posts in duplicates.items():
        sorted_posts = sorted(posts, key=lambda p: (
            p['date_posted'] if p['date_posted'] is not None else datetime.max
        ))
        keeper = sorted_posts[0]
        removals = sorted_posts[1:]

        # Keep all URLs from the keeper
        urls_to_keep.update(keeper['all_urls'])

        for p in removals:
            docs_to_delete.append(p['doc_id'])
            urls_to_delete.update(p['all_urls'])

    # Only delete storage files that are NOT referenced by any kept doc
    exclusively_deleted_urls = urls_to_delete - urls_to_keep

    storage_paths = extract_storage_paths(list(exclusively_deleted_urls), bucket_name)

    return docs_to_delete, storage_paths

# ---------------------------------------------------------------------------
# Phase 3 — execute deletions
# ---------------------------------------------------------------------------

def execute_deletions(db, bucket, docs_to_delete, storage_paths, dry_run=True):
    mode = "DRY RUN" if dry_run else "LIVE"
    log.info("=" * 70)
    log.info("PHASE 2 — Deleting duplicates  [%s]", mode)
    log.info("=" * 70)
    log.info("Firestore docs to delete : %d", len(docs_to_delete))
    log.info("Storage files to delete  : %d", len(storage_paths))

    # --- Firestore ---
    if docs_to_delete:
        if dry_run:
            log.info("[DRY] Would delete %d documents from %s", len(docs_to_delete), COLLECTION)
        else:
            deleted = 0
            BATCH = 400
            for i in range(0, len(docs_to_delete), BATCH):
                batch = db.batch()
                for doc_id in docs_to_delete[i:i + BATCH]:
                    batch.delete(db.collection(COLLECTION).document(doc_id))
                batch.commit()
                deleted += len(docs_to_delete[i:i + BATCH])
                log.info("  Deleted %d / %d Firestore docs …", deleted, len(docs_to_delete))
            log.info("Firestore: deleted %d documents.", deleted)

    # --- Storage ---
    if storage_paths:
        deleted_storage = 0
        failed_storage = 0
        total_bytes = 0

        for path in storage_paths:
            blob = bucket.blob(path)
            if dry_run:
                # Check if blob exists to give accurate preview
                if blob.exists():
                    blob.reload()
                    size = blob.size or 0
                    total_bytes += size
                    log.info("[DRY] Would delete: %s  (%.2f MB)", path, size / 1024 / 1024)
                    deleted_storage += 1
                else:
                    log.info("[DRY] Blob not found (already gone): %s", path)
            else:
                try:
                    if blob.exists():
                        blob.reload()
                        total_bytes += blob.size or 0
                        blob.delete()
                        deleted_storage += 1
                        log.info("  Deleted: %s", path)
                    else:
                        log.info("  Blob not found (skipped): %s", path)
                except Exception as e:
                    log.error("  Failed to delete %s: %s", path, e)
                    failed_storage += 1

        mb = total_bytes / (1024 * 1024)
        log.info("Storage: %s %d files  (%.2f MB)",
                 "would delete" if dry_run else "deleted", deleted_storage, mb)
        if failed_storage:
            log.warning("Storage: %d deletions failed", failed_storage)
    else:
        log.info("No storage files to clean up (videos may be YouTube URLs, not stored files).")

    # --- Summary ---
    log.info("=" * 70)
    log.info("SUMMARY")
    log.info("=" * 70)
    log.info("  Firestore docs removed : %d", len(docs_to_delete))
    log.info("  Storage files removed  : %d", len(storage_paths))
    if dry_run:
        log.info("")
        log.info("This was a DRY RUN. Nothing was actually deleted.")
        log.info("Re-run with  --live  to perform real deletions.")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    dry_run = '--live' not in sys.argv

    db, bucket = init_firebase()
    log.info("Connected to bucket: %s", bucket.name)

    # 1. Discover
    video_map, duplicates = discover_duplicates(db)

    if not duplicates:
        log.info("No duplicates found — nothing to do.")
        return

    # 2. Plan
    docs_to_delete, storage_paths = plan_deletions(duplicates, bucket.name)

    # 3. Safety gate for live mode
    if not dry_run:
        print()
        print("WARNING: You are about to PERMANENTLY delete:")
        print(f"  • {len(docs_to_delete)} Firestore documents from '{COLLECTION}'")
        print(f"  • {len(storage_paths)} files from Firebase Storage")
        print()
        answer = input("Type 'yes' to confirm: ")
        if answer.strip().lower() != 'yes':
            print("Aborted.")
            sys.exit(0)

    # 4. Execute
    execute_deletions(db, bucket, docs_to_delete, storage_paths, dry_run=dry_run)


if __name__ == '__main__':
    main()
