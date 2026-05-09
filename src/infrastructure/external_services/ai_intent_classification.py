"""Gemini AI implementation of intent classification."""

import logging
from typing import Literal, Optional, List, Dict, Any
from pydantic import BaseModel

from src.domain.services.intent_classification import IntentClassificationService
from src.infrastructure.external_services.ai_client_factory import get_instructor_client

logger = logging.getLogger(__name__)

INTENT_PROMPT = (
    "You are an intent classification engine for a SharePoint AI assistant. "
    "Read the user's message and return exactly one intent:\n\n"
    "  • 'query'     – user wants to RETRIEVE, SEARCH, COUNT, LIST, VIEW, LOOK UP, or ANALYSE data "
    "that already exists in SharePoint (lists, tasks, items, columns, documents, pages, sites). "
    "This INCLUDES questions about what resources exist, showing all resources, or getting metadata. "
    "This ALSO INCLUDES any question asking WHO, WHAT, WHEN, WHERE, or HOW about "
    "information that could live in SharePoint data — even if the user doesn't name a specific list or resource. "
    "These are INFORMATION-SEEKING questions and must be classified as 'query' so the system can search for answers.\n"
    "Examples: 'how many tasks?', 'show me the Onboarding list', 'what lists do I have?', "
    "'list all the lists', 'display all libraries', 'show me all pages', 'get all sites', "
    "'wats in the tasks list?', 'is that all?', 'are there more?', "
    "'who is the employee of the month?', 'what is the employee of the month?', "
    "'who won the latest award?', 'what are the latest announcements?', "
    "'who are the new hires?', 'what events do we have?', "
    "'what are the KPIs?', 'who is on the team?', "
    "'what is the company policy on X?', 'how many employees do we have?' (typos are fine).\n\n"
    "  • 'provision' – user expresses a clear command to CREATE, UPDATE, DELETE, BUILD, "
    "DEPLOY, or POPULATE a SharePoint resource or its data. "
    "This includes: creating/deleting lists, pages, libraries, groups; "
    "AND adding, inserting, or populating items/data/records inside a list or library. "
    "Examples: 'create a project tracker', 'delete the old page', 'add HR document webpart', "
    "'add data to the testing list', 'add items to X', 'add sample data', "
    "'insert a record', 'populate the list', 'add 3 items to X' (typos fine).\n\n"
    "  • 'chat'      – ONLY greetings, capability questions (e.g., 'what can you do?', 'what can I build?'), "
    "or truly off-topic messages unrelated to SharePoint data. "
    "Do NOT use 'chat' for information-seeking questions — those are ALWAYS 'query'.\n\n"
    "CRITICAL RULES:\n"
    "1. Phrases like 'list all', 'show all', 'display all', 'get all', 'what [resources] do I have' → QUERY.\n"
    "2. ANY question asking 'who is', 'what is', 'how is', 'who are', 'what are', 'when is', 'where is' about "
    "company/team/org data → QUERY (the system will search SharePoint for the answer).\n"
    "3. Questions about people, recognition, awards, events, policies, announcements → QUERY.\n"
    "4. When in doubt between 'query' and 'chat', choose 'query' — it's better to search and find nothing "
    "than to give a generic chat response when data exists.\n\n"
    "IMPORTANT: Use conversation history to understand follow-up questions like 'is that all?', 'show me more', etc. "
    "If they were just discussing lists/data, classify as 'query'. If they were provisioning, classify as 'chat' for clarification.\n\n"
    "Infer intent even when the message contains spelling mistakes or unusual phrasing."
)


class _IntentModel(BaseModel):
    intent: Literal["query", "provision", "chat"]


class GeminiIntentClassificationService(IntentClassificationService):
    """Implementation of intent classification using Gemini/Instructor."""

    async def classify_intent(self, message: str, history: Optional[List[Dict[str, Any]]] = None) -> Literal["query", "provision", "chat"]:
        import asyncio
        import random
        
        max_attempts = 4
        
        for attempt in range(max_attempts):
            try:
                client, model = get_instructor_client()
                history_text = ""
                if history:
                    history_text = "Recent Conversation History:\n" + "\n".join(
                        f"{msg.get('role', 'unknown')}: {msg.get('content', '')}" for msg in history
                    ) + "\n\n"
                
                kwargs = {
                    "messages": [{"role": "user", "content": f"{INTENT_PROMPT}\n\n{history_text}User message: {message}"}],
                    "response_model": _IntentModel,
                }
                if model:  # Only pass model for non-Gemini providers
                    kwargs["model"] = model
                result = client.chat.completions.create(**kwargs)
                return result.intent
            except Exception as exc:
                is_quota_error = "429" in str(exc) or "Resource exhausted" in str(exc) or "quota" in str(exc).lower()
                if is_quota_error and attempt < max_attempts - 1:
                    # Exponential backoff with jitter: 1s, 2s, 4s, ...
                    delay = (2 ** attempt) + random.uniform(0, 0.5)
                    logger.warning("Intent classification hit quota limit (429). Retrying in %.2fs (attempt %d/%d)...", delay, attempt + 1, max_attempts)
                    await asyncio.sleep(delay)
                else:
                    logger.warning("Intent classification failed (%s); defaulting to 'chat'.", exc)
                    return "chat"
        
        return "chat"
