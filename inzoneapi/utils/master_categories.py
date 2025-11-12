"""
Master Category Taxonomy for InZone Social Media Platform
===========================================================
All users and posts are mapped to these 17 standardized categories
using semantic similarity matching.
"""

MASTER_CATEGORIES = [
    "mental_health_wellness",
    "entrepreneurship_financial_literacy",
    "entertainment_memes",
    "food_diy",
    "pets_wildlife",
    "online_safety_privacy",
    "travel_adventure",
    "creativity_art",
    "music_dance",
    "empowerment_leadership",
    "trauma_loss_resilience",
    "health_healthy_habits",
    "environmental_community_actions",
    "gaming_virtual_worlds",
    "learning_education",
    "bullying_prevention_online_respect",
    "inclusivity_anti_discrimination"
]

# Human-readable names for display/debugging
CATEGORY_DISPLAY_NAMES = {
    "mental_health_wellness": "Mental Health & Wellness",
    "entrepreneurship_financial_literacy": "Entrepreneurship & Financial Literacy",
    "entertainment_memes": "Entertainment & Memes",
    "food_diy": "Food & DIY",
    "pets_wildlife": "Pets & Wildlife",
    "online_safety_privacy": "Online Safety & Privacy",
    "travel_adventure": "Travel & Adventure",
    "creativity_art": "Creativity & Art",
    "music_dance": "Music & Dance",
    "empowerment_leadership": "Empowerment & Leadership",
    "trauma_loss_resilience": "Trauma, Loss & Resilience",
    "health_healthy_habits": "Health & Healthy Habits",
    "environmental_community_actions": "Environmental & Community Actions",
    "gaming_virtual_worlds": "Gaming & Virtual Worlds",
    "learning_education": "Learning & Education",
    "bullying_prevention_online_respect": "Bullying Prevention & Online Respect",
    "inclusivity_anti_discrimination": "Inclusivity & Anti-Discrimination"
}

# Expanded keyword lists for better semantic matching
CATEGORY_KEYWORDS = {
    "mental_health_wellness": [
        "mental health", "wellness", "mindfulness", "meditation", "therapy",
        "counseling", "self-care", "stress", "anxiety", "depression",
        "emotional health", "psychology", "relaxation", "spirituality"
    ],
    "entrepreneurship_financial_literacy": [
        "entrepreneurship", "financial literacy", "business", "startup",
        "money management", "budgeting", "saving", "investing", "finance",
        "young entrepreneurs", "career", "job skills", "economics"
    ],
    "entertainment_memes": [
        "entertainment", "memes", "funny", "humor", "comedy", "jokes",
        "viral content", "trending", "pop culture", "celebrities",
        "movies", "tv shows", "viral trends", "internet culture"
    ],
    "food_diy": [
        "food", "cooking", "recipes", "baking", "diy", "crafts",
        "nutrition", "healthy eating", "meal prep", "cuisine",
        "home cooking", "crafting", "handmade", "projects"
    ],
    "pets_wildlife": [
        "pets", "animals", "wildlife", "dogs", "cats", "pet care",
        "animal rescue", "nature", "conservation", "veterinary",
        "animal adoption", "zoo", "aquarium", "birds"
    ],
    "online_safety_privacy": [
        "online safety", "privacy", "cybersecurity", "internet safety",
        "digital citizenship", "data protection", "passwords",
        "scams", "phishing", "identity theft", "cyberbullying prevention"
    ],
    "travel_adventure": [
        "travel", "adventure", "exploring", "tourism", "vacation",
        "backpacking", "hiking", "camping", "outdoor activities",
        "destinations", "culture", "geography", "trips"
    ],
    "creativity_art": [
        "creativity", "art", "drawing", "painting", "design",
        "illustration", "digital art", "sculpture", "photography",
        "crafts", "artistic", "creative projects", "visual arts"
    ],
    "music_dance": [
        "music", "dance", "singing", "instruments", "bands",
        "concerts", "choreography", "ballet", "hip hop", "performance",
        "musical", "rhythm", "dancing", "songs"
    ],
    "empowerment_leadership": [
        "empowerment", "leadership", "confidence", "self-esteem",
        "motivation", "inspiration", "role models", "success",
        "goal setting", "personal growth", "youth activism", "advocacy"
    ],
    "trauma_loss_resilience": [
        "trauma", "loss", "grief", "resilience", "healing",
        "coping", "recovery", "support", "survivor", "bereavement",
        "emotional support", "crisis", "overcoming challenges"
    ],
    "health_healthy_habits": [
        "health", "fitness", "exercise", "healthy habits", "wellness",
        "nutrition", "diet", "physical activity", "sports",
        "hygiene", "sleep", "lifestyle", "medical"
    ],
    "environmental_community_actions": [
        "environment", "sustainability", "climate change", "recycling",
        "community service", "volunteering", "activism", "conservation",
        "eco-friendly", "green living", "social impact", "charity"
    ],
    "gaming_virtual_worlds": [
        "gaming", "video games", "esports", "virtual worlds",
        "online games", "game reviews", "streaming", "twitch",
        "minecraft", "roblox", "fortnite", "game development"
    ],
    "learning_education": [
        "learning", "education", "study", "school", "homework",
        "tutoring", "academic", "knowledge", "skills", "science",
        "math", "reading", "writing", "research", "student"
    ],
    "bullying_prevention_online_respect": [
        "bullying prevention", "anti-bullying", "respect", "kindness",
        "empathy", "peer support", "conflict resolution", "netiquette",
        "standing up", "bystander intervention", "positive relationships"
    ],
    "inclusivity_anti_discrimination": [
        "inclusivity", "diversity", "anti-discrimination", "equality",
        "lgbtq", "gender identity", "cultural diversity", "acceptance",
        "social justice", "human rights", "prejudice", "bias", "tolerance"
    ]
}


def get_category_display_name(category_id):
    """Get human-readable name for a category"""
    return CATEGORY_DISPLAY_NAMES.get(category_id, category_id)


def get_all_categories():
    """Get list of all master categories"""
    return MASTER_CATEGORIES.copy()


def get_category_keywords(category_id):
    """Get keywords for a specific category"""
    return CATEGORY_KEYWORDS.get(category_id, [])
