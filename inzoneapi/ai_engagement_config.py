# AI Engagement System Configuration

# Core engagement settings
MAX_DAILY_INTERACTIONS_PER_AI = 5
MIN_INTERACTION_INTERVAL_HOURS = 2
MAX_INTERACTION_INTERVAL_HOURS = 8

# Interaction probabilities (0.0 - 1.0)
COMMENT_PROBABILITY = 0.4
LIKE_PROBABILITY = 0.6
DM_PROBABILITY = 0.3

# DM rules
DM_COOLDOWN_HOURS = 24  # Wait time before AI can send another DM to same user
MAX_UNANSWERED_DMS = 1  # Max unanswered DMs before stopping

# Content relevance
RELEVANT_CONTENT_ENGAGEMENT_CHANCE = 0.7  # 70% chance for relevant content
GENERAL_CONTENT_ENGAGEMENT_CHANCE = 0.2   # 20% chance for general content

# Scheduler settings
SCHEDULER_ENABLED = True
PEAK_HOURS = [9, 10, 11, 12, 13, 17, 18, 19, 20, 21]  # More frequent during these hours
PEAK_INTERVAL_MINUTES = (30, 90)    # Range for peak hours
REGULAR_INTERVAL_MINUTES = (60, 180) # Range for regular hours
NIGHT_INTERVAL_MINUTES = (180, 360)  # Range for night hours (3-6 hours)

# AI personality prompts
AI_COMMENT_SYSTEM_PROMPT = """
You are an AI character on a social media platform. Generate natural, supportive comments that:
- Feel authentic and human-like
- Show genuine interest in the post
- Encourage conversation
- Match your personality
- Are brief (max 50 words)
- Don't mention being AI or artificial

Your personality: {personality}
Your interests: {interests}
Post about: {post_topic}
Post content: {post_content}
"""

AI_DM_SYSTEM_PROMPT = """
You are an AI character sending a casual, friendly DM to start a conversation. Be:
- Natural and warm
- Brief (max 30 words)  
- Genuinely interested in connecting
- Not pushy or artificial

Your personality: {personality}
Your interests: {interests}
Target user's recent activity suggests they're interested in: {user_interests}
"""

# OpenAI settings
OPENAI_MODEL = "gpt-4o"
OPENAI_TEMPERATURE = 0.8
OPENAI_MAX_TOKENS_COMMENT = 100
OPENAI_MAX_TOKENS_DM = 80

# Database collections
AI_USERS_COLLECTION = "aiUsers"
POSTS_COLLECTION_HUMAN = "humanPosts"
POSTS_COLLECTION_AI = "aiPosts"
COMMENTS_COLLECTION = "postComments"
LIKES_COLLECTION = "postLikes"

# Logging
LOG_LEVEL = "INFO"
LOG_AI_INTERACTIONS = True
LOG_ENGAGEMENT_STATS = True