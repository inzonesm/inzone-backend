import autogen
from autogen.agentchat import AssistantAgent, UserProxyAgent
import os
import datetime
from typing import List, Dict, Any
import uuid
import asyncio

class ChatOrchestrator:
    """
    Orchestrates responses from AI characters in a group chat using autogen agents
    """
    
    def __init__(self, ai_participants):
        """
        Initialize the orchestrator with AI participants from the group chat
        
        Args:
            ai_participants: List of AI participants from the group chat
        """
        self.ai_participants = ai_participants
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
            
        # Configure autogen settings with the latest API
        self.config_list = [
            {
                "model": "gpt-4-0125-preview",
                "api_key": self.openai_api_key,
            }
        ]
        
        # Create agent for each AI character
        self.agents = self._create_agents()
        
    def _create_agents(self):
        """Create autogen agents for each AI character using the latest API"""
        agents = {}
        
        # Create the orchestrator agent first with the new API format
        orchestrator_agent = self._create_orchestrator_agent()
        agents["orchestrator"] = orchestrator_agent
        
        # Create an agent for each AI character
        for participant in self.ai_participants:
            uid = participant.get("uid")
            name = participant.get("name")
            
            if uid and name:
                agent = self._create_character_agent(uid, name)
                agents[uid] = agent
                
        return agents
        
    def _create_orchestrator_agent(self):
        """Create the orchestrator agent that decides which AI characters should respond"""
        return AssistantAgent(
            name="orchestrator",
            system_message="""You are an orchestrator for a group chat with AI characters.
            Your job is to:
            1. Analyze the group chat conversation
            2. Decide which AI character should respond next based on the context
            3. You can have multiple AI characters respond in sequence if appropriate
            4. Make decisions that create a natural, engaging conversation flow
            
            Be strategic about which characters respond to make the conversation feel authentic.
            Sometimes one character might respond, other times multiple characters might have a mini-conversation.
            """,
            llm_config={"config_list": self.config_list}
        )
        
    def _create_character_agent(self, uid, name):
        """Create an agent for a specific AI character"""
        return AssistantAgent(
            name=name,
            system_message=f"""You are {name}, an AI character in a group chat.
            Respond authentically as {name} would, maintaining your unique personality, knowledge, and speech patterns.
            Keep responses conversational, engaging, and appropriate for a group chat setting.
            You may reference the conversation history to maintain context.
            """,
            llm_config={"config_list": self.config_list}
        )
    
    def _format_messages_for_autogen(self, messages):
        """Format the Firestore messages for autogen"""
        formatted = []
        
        for msg in messages:
            sender_name = msg.get("sender", {}).get("name", "Unknown")
            content = msg.get("content", "")
            formatted.append(f"{sender_name}: {content}")
            
        return "\n".join(formatted)
    
    def _create_message_object(self, sender, content):
        """Create a message object in the format needed for Firestore"""
        current_time = datetime.datetime.now()
        
        return {
            "id": current_time.strftime("%Y%m%d%H%M%S") + str(uuid.uuid4())[:8],
            "sender": sender,
            "content": content,
            "isProcessed": True
        }
    
    async def _get_character_response(self, character_agent, character_name, chat_history):
        """Get a response from a character agent using async approach"""
        # Create a user proxy agent with updated API
        user_proxy = UserProxyAgent(
            name="user_proxy",
            human_input_mode="NEVER",
            code_execution_config=False
        )
        
        # Generate the character's response using async API
        character_query = f"""
        Here is the recent conversation in a group chat:
        
        {chat_history}
        
        Please respond as {character_name} to the conversation above.
        """
        
        # Initiate a chat with the character agent
        await user_proxy.a_initiate_chat(
            character_agent, 
            message=character_query
        )
        
        # Get the response - updated for the 0.4.x API
        messages = user_proxy.chat_messages[character_agent.name]
        response = messages[-1]["content"] if messages else ""
        
        return response
    
    def generate_responses(self, messages):
        """
        Generate responses from AI characters based on the chat history
        
        Args:
            messages: The last few messages from the group chat
            
        Returns:
            A list of new AI messages to add to the chat
        """
        if not messages:
            return []
            
        # Extract the last message to determine context
        last_message = messages[-1]
        
        if last_message.get("sender", {}).get("type") != "user":
            # Don't respond to AI messages with more AI messages
            return []
            
        # Format messages for autogen
        chat_history = self._format_messages_for_autogen(messages)
        
        # Create a list of available AI character names to help the orchestrator decide
        ai_names = [p.get("name") for p in self.ai_participants]
        
        # Create a human query agent for the orchestrator to respond to using updated API
        user_proxy = UserProxyAgent(
            name="user_proxy",
            human_input_mode="NEVER",
            code_execution_config=False
        )
        
        # Ask the orchestrator which characters should respond
        query = f"""
        Here is the recent conversation in a group chat:
        
        {chat_history}
        
        The available AI characters who can respond are: {', '.join(ai_names)}.
        
        Which character(s) should respond next? Choose either one character or a sequence of characters 
        that would create a natural conversation flow. For each character, explain briefly why they should respond 
        and what the general tone/content of their response should be.
        
        Format your response as:
        CHARACTER_NAME: reason for response and general guidance on tone/content
        [Next CHARACTER_NAME if multiple]: reason and guidance
        """
        
        # Using asyncio to run the async methods
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Get orchestrator response using async API
        loop.run_until_complete(user_proxy.a_initiate_chat(self.agents["orchestrator"], message=query))
        
        # Parse the orchestrator's response to determine which characters should respond
        orchestrator_response = user_proxy.chat_messages[self.agents["orchestrator"].name][-1]["content"]
        selected_characters = self._parse_orchestrator_response(orchestrator_response)
        
        # Generate responses from selected characters
        new_messages = []
        running_history = chat_history
        
        for character_info in selected_characters:
            character_name = character_info["name"]
            character_uid = character_info["uid"]
            
            # Find the agent for this character
            character_agent = self.agents.get(character_uid)
            
            if not character_agent:
                continue
                
            # Generate the character's response using async API
            response = loop.run_until_complete(
                self._get_character_response(character_agent, character_name, running_history)
            )
            
            # Create a new message object
            sender = {
                "uid": character_uid,
                "name": character_name,
                "type": "ai"
            }
            
            # Make sure we don't include any metadata or name prefix in the response
            clean_response = self._clean_response(response, character_name)
            
            new_message = self._create_message_object(sender, clean_response)
            new_messages.append(new_message)
            
            # Update running history
            running_history += f"\n{character_name}: {clean_response}"
        
        # Clean up the event loop
        loop.close()
            
        return new_messages
        
    def _parse_orchestrator_response(self, response):
        """Parse the orchestrator's response to get the characters that should respond"""
        selected = []
        
        # Split by lines and look for character names
        lines = response.split('\n')
        current_character = None
        
        for line in lines:
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
                
            # Check for character name at the start of a line
            for participant in self.ai_participants:
                name = participant.get("name")
                
                # Check if line starts with the character name followed by a colon
                if name and (line.startswith(f"{name}:") or line.startswith(f"{name.upper()}:")):
                    current_character = {
                        "name": name,
                        "uid": participant.get("uid")
                    }
                    selected.append(current_character)
                    break
                    
        # If no explicit character names found, try to extract them from the text
        if not selected:
            for participant in self.ai_participants:
                name = participant.get("name")
                
                if name in response:
                    selected.append({
                        "name": name,
                        "uid": participant.get("uid")
                    })
                    
        # If still no characters found, select the first one as default
        if not selected and self.ai_participants:
            first = self.ai_participants[0]
            selected.append({
                        "name": first.get("name"),
                        "uid": first.get("uid")
                    })
            
        return selected
        
    def _clean_response(self, response, character_name):
        """Clean the response to remove any metadata or name prefix"""
        # Remove character name if it starts the response
        if response.startswith(f"{character_name}:"):
            response = response[len(character_name) + 1:].strip()
            
        # Remove any other references like "As [character name]:"
        prefixes = [
            f"As {character_name}:",
            f"As {character_name},",
            f"{character_name} says:",
            f"{character_name} responds:",
        ]
        
        for prefix in prefixes:
            if response.startswith(prefix):
                response = response[len(prefix):].strip()
                
        return response