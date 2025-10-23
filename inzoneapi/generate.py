import json
import os
from openai import OpenAI

# Set your OpenAI API key here
OPENAI_API_KEY = "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"

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

def generate_categories(post_text):
    try:
        if not post_text:
            return []
        
        prompt = (
            f"Classify the following post into relevant categories and return a JSON array. "
            f"Do not add anything else—just give me a JSON array starting and ending with brackets. "
            f"Post: {post_text}"
        )
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a text classification model."},
                {"role": "user", "content": prompt}
            ]
        )
        
        content = response.choices[0].message.content.strip()

        # Ensure we only get valid JSON output
        try:
            categories = json.loads(content)
            if isinstance(categories, list):
                return categories[:5]
        except json.JSONDecodeError:
            print(f"Invalid JSON response: {content}")
        
        return []
    
    except Exception as ex:
        print(f"Error generating categories: {ex}")
        return []

def generate():
    test_cases = [
        ("Ever tried making slime that glows in the dark? Well, I just did and it's epic! Mixing science with fun never gets old.",
         ["DIY Projects", "Science Experiments", "Crafts", "Hobbies", "Educational Activities"]),
        
        ("I just finished reading an amazing sci-fi novel about time travel and paradoxes. Highly recommend it!",
         ["Books", "Science Fiction", "Entertainment", "Reading", "Time Travel"]),
        
        ("Best homemade pizza recipe: fresh dough, spicy tomato sauce, and lots of cheese! Who else loves making pizza at home?",
         ["Cooking", "Food", "Recipes", "Homemade", "Hobbies"]),
        
        ("Anyone else obsessed with the new electric cars? The range and tech are getting insane!",
         ["Technology", "Automobiles", "Electric Vehicles", "Sustainability", "Innovation"]),
        
        ("", [])  # Edge case: Empty input should return an empty list.
    ]

    for i, (post, expected) in enumerate(test_cases):
        result = generate_categories(post)
        print(result)
        assert isinstance(result, list), f"Test {i+1} failed: Output is not a list"
        assert all(isinstance(cat, str) for cat in result), f"Test {i+1} failed: Output contains non-string values"
        print(f"Test {i+1} Passed: {result}")

if __name__ == "__main__":
    generate()
