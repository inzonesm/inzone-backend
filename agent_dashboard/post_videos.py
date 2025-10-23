import firebase_admin
from firebase_admin import credentials, firestore
from Inzone_agents.post_using_api import create_social_post

# Initialize Firebase Admin SDK
if not firebase_admin._apps:
    cred = credentials.Certificate("Inzone_agents/assets/key.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

def post_shorts_from_firestore(username, number_of_posts):
    post_ids = []
    posts_created = 0

    # Reference to the 'youtubeVideos' collection
    videos_ref = db.collection('youtubeVideos')

    # Query for videos with posted = False
    query = videos_ref.where('posted', '==', False).limit(number_of_posts)

    for doc in query.stream():
        video_data = doc.to_dict()
        post_message = video_data.get('generated_caption', '')
        video_ref = [video_data.get('youtube_shorts_links', '')]

        try:
            post_id = create_social_post(
                post_message,
                username=username,
                video_ref=video_ref,
            )
            if post_id and post_id['success']:
                post_id['data']['postMessage'] = post_message
                post_id['data']['videoRef'] = video_ref
                post_ids.append(post_id)
                # Update the document in Firestore
                doc.reference.update({
                    'posted': True,
                    'post_id': post_id['data']['postId']
                })
                posts_created += 1
            else:
                print(f"Failed to create post: {post_id}")
        except Exception as e:
            print(f"An error occurred: {e}")

        if posts_created >= number_of_posts:
            break

    return post_ids

# Call the function to post shorts from Firestore
# print(post_shorts_from_firestore("Byte.Banter", 2))
