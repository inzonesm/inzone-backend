import pyautogen
from autogen_agentchat.agents import AssistantAgent, UserProxyAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
import os
import datetime
from typing import List, Dict, Any
import uuid
import asyncio
import re
from collections import OrderedDict

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
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")

        self.model_client = OpenAIChatCompletionClient(
            model=self.openai_model,
            api_key=self.openai_api_key,
        )

        self.user_proxy = self._create_user_proxy()
        self.agents = self._create_agents()

    def _create_agents(self):
        """Create autogen agents for each AI character"""
        agents = {}
        agents["orchestrator"] = self._create_orchestrator_agent()

        for participant in self.ai_participants:
            uid = participant.get("uid")
            name = participant.get("name")
            if uid and name:
                agents[uid] = self._create_character_agent(uid, name)

        return agents

    def _create_user_proxy(self):
        return UserProxyAgent(
            name="user_proxy",
            input_func=lambda _: ""
        )

    def _create_orchestrator_agent(self):
        """Create orchestrator agent that selects who should respond"""
        return AssistantAgent(
            name="orchestrator",
            model_client=self.model_client,
            system_message="""You are an orchestrator for a group chat with AI characters.
            Your job is to:
            1. Analyze the group chat conversation
            2. Decide which AI character should respond next based on the context
            3. You can have multiple AI characters respond in sequence if appropriate
            4. Make decisions that create a natural, engaging conversation flow

            Be strategic about which characters respond to make the conversation feel authentic.
            Prefer 1 responder for direct/specific questions, and 2 for broader discussion.
            Prefer characters who have not spoken recently when choices are equivalent.
            """
        )

    def _to_valid_agent_name(self, display_name: str, uid: str) -> str:
        base_name = re.sub(r"\W+", "_", display_name or "agent")
        if not base_name:
            base_name = "agent"
        if not re.match(r"^[A-Za-z_]", base_name):
            base_name = f"agent_{base_name}"

        uid_part = re.sub(r"\W+", "_", uid or "")
        if uid_part:
            return f"{base_name}_{uid_part[:12]}"
        return base_name

    def _create_character_agent(self, uid, name):
        """Create agent for a specific AI character"""
        """
        Possible additional parameters for agent:
        Try to reply in 1 or 2 sentences, ideally 8-19 words, max 25 words.
        Avoid long explanations, avoid multi-question follow-ups, and keep it punchy.
        """
        safe_agent_name = self._to_valid_agent_name(name, uid)
        return AssistantAgent(
            name=safe_agent_name,
            model_client=self.model_client,
            system_message=f"""You are {name}, an AI character in a group chat.
            Respond authentically as {name} would, maintaining your unique personality, knowledge, and speech patterns.
            Keep responses conversational, engaging, and appropriate for a group chat setting.
            You should reference the conversation history to maintain context.
            Answer the user's latest question directly and concretely first, then add personality.
            Keep it concise: 1-2 short sentences.
            """
        )

    def _run_agent_task(self, loop: asyncio.AbstractEventLoop, agent: AssistantAgent, task: str, user_proxy: UserProxyAgent | None = None) -> str:
        proxy = user_proxy or self.user_proxy
        composed_task = task
        if proxy:
            composed_task = f"[From {proxy.name}]\n{task}"

        result = loop.run_until_complete(agent.run(task=composed_task))

        if result.messages:
            latest_content = getattr(result.messages[-1], "content", None)
            if isinstance(latest_content, str):
                return latest_content

        for message in reversed(result.messages):
            source = getattr(message, "source", None)
            content = getattr(message, "content", None)
            if source == agent.name and isinstance(content, str):
                return content

        for message in reversed(result.messages):
            content = getattr(message, "content", None)
            if isinstance(content, str):
                return content

        return ""

    def _format_messages_for_autogen(self, messages):
        """Format Firestore messages for orchestration context"""
        formatted = []
        for msg in messages:
            sender_name = msg.get("sender", {}).get("name", "Unknown")
            content = msg.get("content", "")
            formatted.append(f"{sender_name}: {content}")
        return "\n".join(formatted)

    def _create_message_object(self, sender, content):
        """Create Firestore message object"""
        current_time = datetime.datetime.now()
        return {
            "id": current_time.strftime("%Y%m%d%H%M%S") + str(uuid.uuid4())[:8],
            "sender": sender,
            "content": content,
            "isProcessed": True
        }

    def _get_character_response(
        self,
        loop: asyncio.AbstractEventLoop,
        character_agent,
        character_name,
        chat_history,
        latest_user_message: str,
    ):
        """Get a response from a character agent"""
        """ 
        Possible additional parameters for character responses:        
        Try to reply in 1 or 2 sentences, ideally 8-19 words, max 25 words.
        Avoid long explanations, avoid multi-question follow-ups, and keep it punchy.
        """
        user_proxy = self._create_user_proxy()
        character_query = f"""
        Here is the recent conversation in a group chat:

        {chat_history}

        Latest user message to answer:
        {latest_user_message}

        Please respond as {character_name} to the conversation above.
        Answer the latest user message directly and stay consistent with prior context.
        """
        response = self._run_agent_task(loop, character_agent, character_query, user_proxy)
        return self._shorten_response(response)

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

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return self._generate_responses_impl(loop, messages)
        finally:
            try:
                pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
                for task in pending:
                    task.cancel()
                if pending:
                    print(f"[orchestrator] cancelling {len(pending)} pending async task(s) before loop shutdown")
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.run_until_complete(loop.shutdown_asyncgens())
            except RuntimeError as exc:
                if "Event loop is closed" not in str(exc):
                    raise
            finally:
                if not loop.is_closed():
                    loop.close()
                asyncio.set_event_loop(None)

    def _generate_responses_impl(self, loop: asyncio.AbstractEventLoop, messages):
        if not messages:
            return []

        last_message = messages[-1]
        if last_message.get("sender", {}).get("type") != "user":
            return []

        chat_history = self._format_messages_for_autogen(messages)
        ai_names = [p.get("name") for p in self.ai_participants]
        latest_user_message = last_message.get("content", "")

        selected_characters = self._select_target_characters(
            loop=loop,
            messages=messages,
            chat_history=chat_history,
            ai_names=ai_names,
            latest_user_message=latest_user_message,
        )

        new_messages = []
        running_history = chat_history

        for character_info in selected_characters:
            character_name = character_info["name"]
            character_uid = character_info["uid"]
            character_agent = self.agents.get(character_uid)

            if not character_agent:
                continue

            response = self._get_character_response(
                loop,
                character_agent,
                character_name,
                running_history,
                latest_user_message,
            )

            sender = {
                "uid": character_uid,
                "name": character_name,
                "type": "ai"
            }

            clean_response = self._clean_response(response, character_name)
            new_message = self._create_message_object(sender, clean_response)
            new_messages.append(new_message)
            running_history += f"\n{character_name}: {clean_response}"

        return new_messages

    def _select_target_characters(self, loop, messages, chat_history, ai_names, latest_user_message):
        directly_targeted = self._extract_targeted_participants(latest_user_message)
        if directly_targeted:
            return directly_targeted

        if self._is_broadcast_message(latest_user_message):
            return [
                {"name": p.get("name"), "uid": p.get("uid")}
                for p in self.ai_participants
                if p.get("uid") and p.get("name")
            ]

        query = f"""
        Here is the recent conversation in a group chat:

        {chat_history}

        The latest user message is:
        {latest_user_message}

        The available AI characters who can respond are: {', '.join(ai_names)}.

        Choose who should respond next.
        Prefer 1 responder for specific user prompts and up to 2 responders for broad prompts.
        Format your response as:
        CHARACTER_NAME: brief reason
        [Next CHARACTER_NAME if needed]: brief reason
        """

        user_proxy = self._create_user_proxy()
        orchestrator_response = self._run_agent_task(loop, self.agents["orchestrator"], query, user_proxy)
        selected_characters = self._parse_orchestrator_response(orchestrator_response)
        selected_characters = self._dedupe_selected(selected_characters)

        if not selected_characters:
            fallback = self._least_recent_ai_participant(messages)
            if fallback:
                return [fallback]
            return []

        return selected_characters[:2]

    def _normalize_text(self, text: str) -> str:
        lowered = (text or "").lower()
        lowered = lowered.replace("-", " ")
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", lowered)).strip()

    def _participant_aliases(self, name: str):
        normalized_name = self._normalize_text(name)
        compact_name = normalized_name.replace(" ", "")
        aliases = {normalized_name, compact_name}

        special_aliases = {
            "captain america": {"captain", "cap", "steve", "steve rogers"},
            "spider man": {"spiderman", "spider man", "spidey", "peter", "peter parker"},
            "iron man": {"ironman", "iron man", "tony", "stark", "tony stark"},
        }
        if normalized_name in special_aliases:
            aliases.update(special_aliases[normalized_name])

        return {alias for alias in aliases if alias}

    def _extract_targeted_participants(self, latest_user_message: str):
        text = self._normalize_text(latest_user_message)
        if not text:
            return []

        selected = []
        for participant in self.ai_participants:
            participant_name = participant.get("name")
            participant_uid = participant.get("uid")
            if not participant_name or not participant_uid:
                continue

            aliases = self._participant_aliases(participant_name)
            matched = any(
                re.search(rf"\\b{re.escape(alias)}\\b", text)
                for alias in aliases
            )
            if matched:
                selected.append({"name": participant_name, "uid": participant_uid})

        return self._dedupe_selected(selected)

    def _is_broadcast_message(self, latest_user_message: str) -> bool:
        text = self._normalize_text(latest_user_message)
        if not text:
            return False

        broadcast_phrases = [
            "everyone",
            "everybody",
            "all of you",
            "you all",
            "team",
            "entire team",
            "all heroes",
            "avengers",
        ]
        return any(phrase in text for phrase in broadcast_phrases)

    def _least_recent_ai_participant(self, messages):
        last_seen_index = {}
        for index, message in enumerate(messages):
            sender = message.get("sender", {})
            if sender.get("type") == "ai":
                uid = sender.get("uid")
                if uid:
                    last_seen_index[uid] = index

        ranked = []
        for participant in self.ai_participants:
            uid = participant.get("uid")
            name = participant.get("name")
            if not uid or not name:
                continue
            ranked.append((last_seen_index.get(uid, -1), {"name": name, "uid": uid}))

        if not ranked:
            return None

        ranked.sort(key=lambda item: item[0])
        return ranked[0][1]

    def _dedupe_selected(self, selected):
        deduped = OrderedDict()
        for entry in selected:
            uid = entry.get("uid")
            name = entry.get("name")
            if uid and name and uid not in deduped:
                deduped[uid] = {"name": name, "uid": uid}
        return list(deduped.values())

    def _parse_orchestrator_response(self, response):
        """Parse orchestrator text response and choose characters"""
        selected = []
        lines = response.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            for participant in self.ai_participants:
                name = participant.get("name")
                if name and (line.startswith(f"{name}:") or line.startswith(f"{name.upper()}:")):
                    selected.append({
                        "name": name,
                        "uid": participant.get("uid")
                    })
                    break

        if not selected:
            for participant in self.ai_participants:
                name = participant.get("name")
                if name in response:
                    selected.append({
                        "name": name,
                        "uid": participant.get("uid")
                    })

        if not selected and self.ai_participants:
            first = self.ai_participants[0]
            selected.append({
                "name": first.get("name"),
                "uid": first.get("uid")
            })

        return selected

    def _clean_response(self, response, character_name):
        """Clean response to remove metadata or name prefix"""
        if response.startswith(f"{character_name}:"):
            response = response[len(character_name) + 1:].strip()

        prefixes = [
            f"As {character_name}:",
            f"As {character_name},",
            f"{character_name} says:",
            f"{character_name} responds:",
        ]

        for prefix in prefixes:
            if response.startswith(prefix):
                response = response[len(prefix):].strip()

        return self._shorten_response(response)

    def _shorten_response(self, response, max_words: int = 40, max_sentences: int = 2):
        text = (response or "").strip()
        if not text:
            return text

        sentence_split = [part.strip() for part in re.split(r'(?<=[.!?])\s+', text) if part.strip()]
        if sentence_split:
            shortened = " ".join(sentence_split[:max_sentences])
        else:
            shortened = text

        words = shortened.split()
        if len(words) > max_words:
            shortened = " ".join(words[:max_words]).rstrip(".,!?") + "..."
        return shortened