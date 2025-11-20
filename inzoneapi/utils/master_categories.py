"""
Master Category Taxonomy for InZone Social Media Platform
===========================================================
Updated to 25 comprehensive categories with emojis and subcategories
"""

MASTER_CATEGORIES = [
    "travel_places",
    "sports_fitness",
    "business_entrepreneurship",
    "mental_health_mindfulness",
    "career_workplace",
    "news_politics",
    "environment_sustainability",
    "community_volunteering_activism",
    "gaming_esports",
    "digital_life_online_safety",
    "pets_animals",
    "personal_finance_investing",
    "science",
    "comedy_humor_memes",
    "fashion_beauty",
    "society_culture_history",
    "education_learning",
    "food_drink",
    "relationships_life_skills",
    "entertainment_pop_culture",
    "arts_design",
    "technology_innovation",
    "diy_home_garden",
    "music_audio",
    "health_wellness"
]

# Human-readable names for display with emojis
CATEGORY_DISPLAY_NAMES = {
    "travel_places": "✈️ Travel & Places",
    "sports_fitness": "⚽ Sports & Fitness",
    "business_entrepreneurship": "💼 Business & Entrepreneurship",
    "mental_health_mindfulness": "🧘 Mental Health & Mindfulness",
    "career_workplace": "👔 Career & Workplace",
    "news_politics": "📰 News & Politics",
    "environment_sustainability": "🌱 Environment & Sustainability",
    "community_volunteering_activism": "🤝 Community, Volunteering & Activism",
    "gaming_esports": "🎮 Gaming & Esports",
    "digital_life_online_safety": "🔒 Digital Life & Online Safety",
    "pets_animals": "🐾 Pets & Animals",
    "personal_finance_investing": "💰 Personal Finance & Investing",
    "science": "🔬 Science",
    "comedy_humor_memes": "😂 Comedy, Humor & Memes",
    "fashion_beauty": "👗 Fashion & Beauty",
    "society_culture_history": "🏛️ Society, Culture & History",
    "education_learning": "📚 Education & Learning",
    "food_drink": "🍔 Food & Drink",
    "relationships_life_skills": "💝 Relationships & Life Skills",
    "entertainment_pop_culture": "🎬 Entertainment & Pop Culture",
    "arts_design": "🎨 Arts & Design",
    "technology_innovation": "💻 Technology & Innovation",
    "diy_home_garden": "🔨 DIY, Home & Garden",
    "music_audio": "🎵 Music & Audio",
    "health_wellness": "💪 Health & Wellness"
}

# Subcategories mapped to master categories
CATEGORY_SUBCATEGORIES = {
    "travel_places": [
        "destinations", "trip_planning", "culture", "backpacking", "adventure_outdoors"
    ],
    "sports_fitness": [
        "team_sports", "individual_sports", "outdoor_endurance", "training", "fantasy_analytics"
    ],
    "business_entrepreneurship": [
        "startups", "smb", "management", "marketing", "product", "ecommerce"
    ],
    "mental_health_mindfulness": [
        "stress_anxiety", "meditation", "therapy_counseling", "self_care", "resilience"
    ],
    "career_workplace": [
        "job_search", "interviewing", "skills_upskilling", "remote_work", "leadership"
    ],
    "news_politics": [
        "world_news", "local_news", "policy", "elections", "media_literacy"
    ],
    "environment_sustainability": [
        "climate", "conservation_projects", "energy_transition", "zero_waste", "sustainable_living"
    ],
    "community_volunteering_activism": [
        "community_service", "nonprofits", "advocacy", "youth_leadership"
    ],
    "gaming_esports": [
        "pc_console_mobile", "esports", "game_reviews", "modding", "game_dev"
    ],
    "digital_life_online_safety": [
        "digital_citizenship", "privacy", "scams_phishing", "netiquette", "parental_guides"
    ],
    "pets_animals": [
        "pet_care", "training", "wildlife", "conservation", "zoos_aquaria"
    ],
    "personal_finance_investing": [
        "budgeting", "saving", "credit", "investing", "crypto_education"
    ],
    "science": [
        "astronomy", "biology", "chemistry", "earth_science", "physics", "research_explainers"
    ],
    "comedy_humor_memes": [
        "memes", "comedy_sketches", "reaction_humor", "jokes"
    ],
    "fashion_beauty": [
        "style", "skincare", "makeup", "hair", "streetwear", "sustainable_fashion"
    ],
    "society_culture_history": [
        "cultural_studies", "sociology", "anthropology", "history", "philosophy"
    ],
    "education_learning": [
        "study_skills", "k12", "higher_ed", "stem", "humanities", "language_learning"
    ],
    "food_drink": [
        "recipes", "cuisines", "baking", "beverages", "nutrition", "restaurants"
    ],
    "relationships_life_skills": [
        "communication", "friendship", "dating", "conflict_resolution", "personal_growth"
    ],
    "entertainment_pop_culture": [
        "movies_tv", "celebrities", "fandoms", "internet_culture", "pop_culture_news"
    ],
    "arts_design": [
        "drawing_painting", "digital_art", "illustration", "graphic_ui", "sculpture"
    ],
    "technology_innovation": [
        "ai_machine_learning", "programming", "gadgets", "cybersecurity", "data_cloud", "maker_hardware"
    ],
    "diy_home_garden": [
        "home_improvement", "crafts_making", "interior_decor", "woodworking", "gardening"
    ],
    "music_audio": [
        "instruments", "vocal", "music_production_dj", "genres", "concerts_live", "podcasts"
    ],
    "health_wellness": [
        "exercise", "preventive_health", "nutrition_guidance", "sleep", "medical_education"
    ]
}

# Expanded keyword lists for semantic matching
CATEGORY_KEYWORDS = {
    "travel_places": [
        "travel", "trip", "vacation", "explore", "destination", "tourist",
        "adventure", "journey", "visit", "backpack", "flight", "hotel",
        "culture", "places", "planning"
    ],
    "sports_fitness": [
        "sports", "fitness", "workout", "exercise", "training", "athlete",
        "gym", "run", "soccer", "basketball", "football", "health", "team sports",
        "individual sports", "outdoor", "endurance", "fantasy"
    ],
    "business_entrepreneurship": [
        "business", "entrepreneur", "startup", "company", "marketing",
        "leadership", "strategy", "ceo", "founder", "venture", "smb",
        "management", "product", "ecommerce"
    ],
    "mental_health_mindfulness": [
        "mental health", "mindfulness", "meditation", "therapy", "wellness",
        "anxiety", "depression", "self-care", "stress", "emotional", "counseling", "resilience"
    ],
    "career_workplace": [
        "career", "job", "work", "workplace", "professional", "employment",
        "office", "resume", "interview", "employer", "employee", "job search",
        "skills", "upskilling", "remote work", "leadership"
    ],
    "news_politics": [
        "politics", "news", "government", "election", "vote", "political",
        "policy", "democracy", "president", "senator", "current events",
        "world news", "local news", "media literacy"
    ],
    "environment_sustainability": [
        "environment", "climate", "sustainability", "eco", "green",
        "recycle", "conservation", "nature", "planet", "renewable",
        "energy transition", "zero waste", "sustainable living"
    ],
    "community_volunteering_activism": [
        "community", "volunteer", "activism", "service", "nonprofit",
        "advocacy", "social good", "charity", "youth leadership", "giving back"
    ],
    "gaming_esports": [
        "game", "gaming", "esports", "gamer", "play", "console", "pc",
        "stream", "twitch", "tournament", "player", "video game", "mobile",
        "modding", "game dev"
    ],
    "digital_life_online_safety": [
        "digital", "online safety", "privacy", "cybersecurity", "internet safety",
        "scams", "phishing", "netiquette", "digital citizenship", "parental guides",
        "online", "security"
    ],
    "pets_animals": [
        "pet", "dog", "cat", "animal", "wildlife", "puppy", "kitten",
        "bird", "fish", "zoo", "veterinary", "rescue", "training", "conservation"
    ],
    "personal_finance_investing": [
        "finance", "money", "invest", "stock", "crypto", "bitcoin",
        "budget", "saving", "wealth", "financial", "trading", "credit", "personal finance"
    ],
    "science": [
        "science", "astronomy", "biology", "chemistry", "physics", "research",
        "experiment", "discovery", "earth science", "scientific", "laboratory"
    ],
    "comedy_humor_memes": [
        "funny", "meme", "joke", "humor", "laugh", "comedy", "lol",
        "hilarious", "comic", "satire", "prank", "viral", "sketches", "reaction"
    ],
    "fashion_beauty": [
        "fashion", "style", "outfit", "clothes", "makeup", "beauty",
        "skincare", "hair", "model", "designer", "trend", "accessory", "streetwear", "sustainable"
    ],
    "society_culture_history": [
        "society", "culture", "history", "tradition", "heritage",
        "museum", "social", "cultural", "historical", "civilization",
        "sociology", "anthropology", "philosophy", "cultural studies"
    ],
    "education_learning": [
        "education", "learn", "study", "school", "student", "teacher",
        "course", "university", "college", "knowledge", "academic", "k12",
        "higher ed", "stem", "humanities", "language learning"
    ],
    "food_drink": [
        "food", "cooking", "recipe", "restaurant", "meal", "eat", "drink",
        "cuisine", "chef", "kitchen", "baking", "nutrition", "delicious", "beverages"
    ],
    "relationships_life_skills": [
        "relationship", "dating", "love", "friend", "friendship",
        "communication", "life", "personal growth", "advice", "conflict resolution",
        "life skills"
    ],
    "entertainment_pop_culture": [
        "entertainment", "celebrity", "pop culture", "famous", "viral",
        "trending", "popular", "star", "fandom", "gossip", "movies", "tv",
        "shows", "internet culture"
    ],
    "arts_design": [
        "art", "design", "draw", "paint", "creative", "artist", "graphic",
        "illustration", "visual", "sculpture", "craft", "photography", "digital art", "ui"
    ],
    "technology_computing": [
        "tech", "technology", "software", "app", "coding", "programming",
        "ai", "ml", "machine learning", "gadget", "digital", "computer", "internet",
        "cybersecurity", "data", "cloud", "hardware", "maker"
    ],
    "diy_home_garden": [
        "diy", "home improvement", "crafts", "woodworking", "gardening", "home",
        "garden", "decor", "interior", "renovation", "making", "handmade", "projects"
    ],
    "music_audio": [
        "music", "song", "artist", "album", "concert", "band", "sing",
        "playlist", "audio", "instrument", "musician", "sound", "vocal",
        "production", "dj", "genres", "live", "podcasts"
    ],
    "health_wellness": [
        "health", "wellness", "medical", "doctor", "hospital", "disease",
        "healthy", "medicine", "treatment", "patient", "care", "preventive",
        "nutrition", "sleep", "exercise"
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
