import streamlit as st
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
import firebase_admin
from firebase_admin import credentials, firestore
import json
import pandas as pd
from post_videos import post_shorts_from_firestore
from fetch_youtube_shorts import fetch_youtube_shorts
from video_caption_generator import process_videos

###### AUTH STUFF ######
with open('config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

# Create authenticator object
authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

# Render login widget
authenticator.login(location="unrendered")

# Handle authentication status
if not st.session_state.get('authentication_status'):
    if st.session_state.get('authentication_status') == False:
        st.error('Username/password is incorrect')
        st.switch_page("login.py")
    elif st.session_state.get('authentication_status') == None:
        st.warning('Please enter your username and password')
        st.switch_page("login.py")
    st.stop()
###### END AUTH STUFF ######

###### FIREBASE STUFF ######
if not firebase_admin._apps:
    cred = credentials.Certificate("Inzone_agents/assets/key.json")
    firebase_admin.initialize_app(cred, name='video-poster-page')
db = firestore.client()
###### END FIREBASE STUFF ######

###### RETRIEVING AGENTS ######
@st.cache_data(ttl=36000)
def get_agents():
    agents_ref = db.collection('aiUsers')
    agents = {doc.id: doc.to_dict() for doc in agents_ref.stream()}
    return agents
agents_data = get_agents()
###### END RETRIEVING AGENTS ######

###### RETRIEVING UNPOSTED VIDEOS ######
@st.cache_data(ttl=3600)
def get_unposted_videos():
    videos_ref = db.collection('youtubeVideos')
    unposted_videos = [doc.to_dict() for doc in videos_ref.where('posted', '==', False).stream()]
    return unposted_videos
unposted_videos = get_unposted_videos()
num_unposted_videos = len(unposted_videos)

def clear_cache_and_get_unposted_videos():
    get_unposted_videos.clear()
    unposted_videos = get_unposted_videos()
    num_unposted_videos = len(unposted_videos)
    num_posted_container.write(f"Number of unposted videos available: {num_unposted_videos}")
    return unposted_videos, num_unposted_videos
###### END RETRIEVING UNPOSTED VIDEOS ######

with st.sidebar:
    agent = st.selectbox(
      "Select an agent", 
      list(agents_data.keys()), 
      index=(list(agents_data.keys()).index('Byte.Banter') if 'Byte.Banter' in agents_data.keys() else 0)
      )
    
    st.markdown(agents_data[agent]['personality'])
    
st.header("Post Videos")

"---"

st.write("#### Posting with: ", agent)

# Show number of unposted videos
num_posted_container = st.empty()
with num_posted_container:    
    st.write(f"Number of unposted videos available: {num_unposted_videos}")

num_shorts = st.number_input("Number of shorts to fetch", 1, 50)

# Fetch new shorts and generate captions
if st.button("Fetch and Generate Captions"):
    fetch_youtube_shorts(num_shorts)
    process_videos()
    
    unposted_videos, num_unposted_videos = clear_cache_and_get_unposted_videos()
    st.success("Fetched and generated captions for new shorts.")

# max posts available is the number of unposted videos
num_posts = st.number_input("Number of posts to create", 0, num_unposted_videos)

create_button = st.button("Create Posts")

if create_button:
    post_ids = post_shorts_from_firestore(agent, num_posts)
    
    st.write(post_ids)
    unposted_videos, num_unposted_videos = clear_cache_and_get_unposted_videos()

