from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import TextMentionTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.ui import Console
from autogen_core.tools import FunctionTool
from autogen_ext.models.openai import OpenAIChatCompletionClient
from typing import Optional, List, Dict, Union
import asyncio
from firebase_admin import credentials, initialize_app, firestore


cred = credentials.Certificate("key.json")
named_app = initialize_app(cred, name='inzone-app-master')
db = firestore.client(app=named_app)

async def main() -> None:
    from post_using_api import create_social_post
    from generate_image import generate_image

    inzone_poster_tool = FunctionTool(
        create_social_post, description="Creates a social media post for Inzone app by calling an api to post with appropriate arguments."
    )
    
    image_generator_tool = FunctionTool(
        generate_image, description="Generates an image based on the given prompt and returns its URL."
    )

    # Read the OpenAI API key from a file
    with open('openai_key.txt', 'r') as file:
        openai_api_key = file.read().strip()
        
    terminate_word = "TERMINATE"
        
    agent_name = "Byte.Banter"
    popularity = False
    agent_bio = "You are an AI social media personality for the Inzone app"
    agent_personality = """- Vibrant mix of cheeky humor, positivity, and a touch of geek chic
    - Approachable and friendly
    - Always has a witty comment ready but knows when to switch gears and provide thoughtful insights"""
    

    system_message=f"""**Bio**:
    Your name is {agent_name}. {agent_bio}. You are{"" if popularity else " not"} a celebrity.

    **Personality**:
    {agent_personality}

    **Task**:
    - Generate Engaging Content:
        - Create social media posts that reflect your distinct personality
        - Posts should be creative, witty, and align with your character
        - Content should be relevant and engaging for the Inzone community

    - Post Management:
        - Generate sample posts based on the given context or topic
        - Use the provided inzone_poster_tool to post directly to the platform
        - No need to generate any code - simply create content and use the existing tool

    - Content Guidelines:
        - Keep posts appropriate and community-friendly
        - Maintain consistent voice and personality
        - Mix humor with valuable insights
        - Adapt tone based on context while staying true to character
        - Only generate an image if it is explicitly requested in the task. Otherwise, generate text posts. If an image is generated, use its generated URL.

    When asked to create posts:
    1. Generate the content according to your personality
    2. Use the inzone_poster_tool to post directly
    3. Confirm successful posting

    Remember: Focus on creating engaging content - the posting mechanism is already handled by the provided tool.
    
    After successfully creating the posts, respond with "{terminate_word}" to end the conversation.

    Remember: 
    1. Create posts
    2. Use the inzone_poster_tool
    3. Confirm the post was successful
    4. End with {terminate_word}"""
    # change the output length to be around 90-150 characters. Same for comments/captions for photos.
    

    inzone_poster_agent = AssistantAgent(
        name="inzone_poster_agent",
        tools=[inzone_poster_tool, image_generator_tool],
        model_client=OpenAIChatCompletionClient(
        model="gpt-4o-mini",
        api_key=openai_api_key
        ),
        description="An agent that can post social media posts for the Inzone app.",
        system_message=system_message,
        )

    termination = TextMentionTermination(f"{terminate_word}")

    group_chat = RoundRobinGroupChat(
        participants=[inzone_poster_agent],
        termination_condition=termination
    )

    await Console(group_chat.run_stream(task="make a single post"))


asyncio.run(main())
