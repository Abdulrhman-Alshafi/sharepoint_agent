from openai import OpenAI
from typing import Tuple, Any, Optional
import os
import json
from pydantic import BaseModel

from src.infrastructure.config import settings

# Module-level cache to avoid re-creating the client on every call
_cached_instructor_client: Optional[Tuple[Any, Optional[str]]] = None


class GenAICompletions:
    """Completions interface for Google Gen AI SDK (Gemini / Vertex AI)."""
    
    def __init__(self, client, model_name: str):
        self._client = client
        self._model_name = model_name
    
    def create(self, messages: list, response_model: type[BaseModel], **kwargs):
        """Create a structured response using Google Gen AI SDK."""
        # Convert messages to a single prompt
        prompt_parts = []
        for msg in messages:
            if isinstance(msg, dict):
                role = msg.get("role", "user")
                content = msg.get("content", "")
                prompt_parts.append(f"{role}: {content}")
            else:
                prompt_parts.append(str(msg))
        
        prompt = "\n".join(prompt_parts)
        
        # Add schema instruction — be very explicit so the model doesn't return plain text.
        schema = response_model.model_json_schema()
        full_prompt = (
            f"{prompt}\n\n"
            f"IMPORTANT: You MUST respond with ONLY a valid JSON object — no markdown, no prose, "
            f"no code fences, no explanation. The JSON must match this schema exactly:\n"
            f"{json.dumps(schema, indent=2)}\n\n"
            f"Output only the raw JSON object starting with '{{' and ending with '}}'."
        )
        
        # Generate content using the new google-genai SDK
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=full_prompt,
        )
        
        # Parse JSON response
        response_text = response.text.strip()
        
        # Clean markdown code blocks if present
        if response_text.startswith("```json"):
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif response_text.startswith("```"):
            response_text = response_text.split("```")[1].split("```")[0].strip()

        # If not already a bare JSON object, try to extract the first {...} block
        if not response_text.startswith("{"):
            import re as _re
            m = _re.search(r'\{.*\}', response_text, _re.DOTALL)
            if m:
                response_text = m.group(0).strip()
        
        # Parse and validate with Pydantic
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            # Model returned plain text / markdown instead of JSON.
            # Try to construct the model using the text as the primary text field.
            import typing
            fields = response_model.model_fields
            primary_field = next(
                (f for f in ("answer", "reply", "text", "content", "message") if f in fields),
                None,
            )
            if primary_field:
                fallback: dict = {}
                for field_name, field_info in fields.items():
                    if field_name == primary_field:
                        fallback[field_name] = response_text
                    elif field_info.default is not None:
                        fallback[field_name] = field_info.default
                    elif field_info.default_factory is not None:  # type: ignore[attr-defined]
                        fallback[field_name] = field_info.default_factory()  # type: ignore[misc]
                    else:
                        # Infer a sensible empty value from the annotation
                        ann = field_info.annotation
                        origin = getattr(ann, "__origin__", None)
                        if origin is list or ann is list:
                            fallback[field_name] = []
                        elif origin is dict or ann is dict:
                            fallback[field_name] = {}
                        elif ann is str:
                            fallback[field_name] = ""
                        elif ann is bool:
                            fallback[field_name] = False
                        elif ann is int or ann is float:
                            fallback[field_name] = 0
                        # else leave missing and let Pydantic raise if required
                try:
                    return response_model(**fallback)
                except Exception:
                    pass
            raise ValueError(f"Model returned invalid JSON: {response_text[:200]}")
        return response_model(**data)


class GenAIChat:
    """Chat interface for Google Gen AI SDK."""
    
    def __init__(self, client, model_name: str):
        self.completions = GenAICompletions(client, model_name)


class GenAIInstructorWrapper:
    """Wrapper to make Google Gen AI SDK compatible with instructor pattern."""
    
    def __init__(self, client, model_name: str):
        self._client = client
        self._model_name = model_name
        self.chat = GenAIChat(client, model_name)
    
    def create(self, response_model: type[BaseModel], messages: list, **kwargs):
        """Create a structured response using Google Gen AI SDK (direct interface)."""
        return self.chat.completions.create(messages=messages, response_model=response_model, **kwargs)

    def generate_content(self, prompt: str, **kwargs):
        """Generate raw text content (used by document_intelligence theme analysis)."""
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=prompt,
        )
        return response


def get_instructor_client() -> Tuple[Any, Optional[str]]:
    """
    Returns a configured instructor client and the designated model string.
    Supports 'gemini', 'vertexai', or 'openai' (which handles OpenAI, Groq, Ollama, etc.).
    Caches the client at module level to avoid connection pool exhaustion.
    """
    global _cached_instructor_client
    if _cached_instructor_client is not None:
        return _cached_instructor_client
    _cached_instructor_client = _build_instructor_client()
    return _cached_instructor_client


def _build_instructor_client() -> Tuple[Any, Optional[str]]:
    if settings.AI_PROVIDER.lower() == "gemini":
        # Use the new unified google-genai SDK with API key
        import instructor
        from google import genai

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        patched = instructor.from_genai(
            client=client,
            mode=instructor.Mode.GENAI_TOOLS,
        )
        # For Gemini via instructor, the model is passed to create() calls
        model = settings.GEMINI_MODEL
        return patched, model
    
    elif settings.AI_PROVIDER.lower() == "vertexai":
        # Use the new unified google-genai SDK with Vertex AI backend
        from google import genai

        # Set credentials if path is provided
        if settings.VERTEXAI_CREDENTIALS_PATH:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = settings.VERTEXAI_CREDENTIALS_PATH
        
        # Initialize the unified genai client for Vertex AI
        client = genai.Client(
            vertexai=True,
            project=settings.VERTEXAI_PROJECT_ID,
            location=settings.VERTEXAI_LOCATION,
        )
        
        # Create wrapper for Vertex AI
        wrapper = GenAIInstructorWrapper(client, settings.VERTEXAI_MODEL)
        model = None
        return wrapper, model
    
    else:
        # Default to OpenAI-compatible provider (OpenAI, Groq, local Ollama)
        import instructor
        
        args = {}
        if settings.OPENAI_API_KEY:
            args["api_key"] = settings.OPENAI_API_KEY
        elif settings.OPENAI_BASE_URL:
            # Local or proxy server (e.g. Ollama, LiteLLM) — API key not required
            args["api_key"] = "dummy_key_for_local"
        else:
            raise ValueError(
                "OPENAI_API_KEY is required when using the OpenAI provider. "
                "Set it in your environment or .env file. "
                "If you are using a local server, also set OPENAI_BASE_URL."
            )
            
        if settings.OPENAI_BASE_URL:
            args["base_url"] = settings.OPENAI_BASE_URL
            
        openai_client = OpenAI(**args)
        client = instructor.from_openai(
            client=openai_client,
            mode=instructor.Mode.JSON,
        )
        model = settings.OPENAI_MODEL
        return client, model
