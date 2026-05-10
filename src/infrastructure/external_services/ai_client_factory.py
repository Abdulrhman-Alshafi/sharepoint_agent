from openai import OpenAI
from typing import Tuple, Any, Optional
import os
import json
from pydantic import BaseModel
from pydantic_core import PydanticUndefinedType
try:
    from pydantic.fields import PydanticUndefined
except ImportError:
    from pydantic.fields import Undefined as PydanticUndefined  # pydantic v1 fallback

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
        
        # Build a concrete example object from the model's field types.
        # Showing an example instance (not the JSON Schema) prevents Gemini from
        # echoing back the schema structure itself as its response.
        import typing as _typing
        example_obj: dict = {}
        for field_name, field_info in response_model.model_fields.items():
            ann = field_info.annotation
            # Unwrap Optional[X] → X so we can inspect the inner type
            origin = getattr(ann, "__origin__", None)
            args = getattr(ann, "__args__", ())
            inner = ann
            if origin is _typing.Union and args:
                # Optional[X] == Union[X, None]; take the first non-None arg
                non_none = [a for a in args if a is not type(None)]
                if non_none:
                    inner = non_none[0]
            inner_origin = getattr(inner, "__origin__", None)
            # If a default value is provided, use it as the example
            if field_info.default is not None and field_info.default is not PydanticUndefined:
                example_obj[field_name] = field_info.default
            elif field_info.default_factory is not None:  # type: ignore[attr-defined]
                example_obj[field_name] = field_info.default_factory()  # type: ignore[misc]
            elif inner_origin is list or inner is list:
                example_obj[field_name] = ["example value 1", "example value 2"]
            elif inner is str:
                example_obj[field_name] = "your answer here"
            elif inner is bool:
                example_obj[field_name] = False
            elif inner is int or inner is float:
                example_obj[field_name] = 0
            elif inner_origin is dict or inner is dict:
                example_obj[field_name] = {}
            else:
                example_obj[field_name] = ""

        full_prompt = (
            f"{prompt}\n\n"
            f"IMPORTANT: You MUST respond with ONLY a valid JSON object — no markdown, no prose, "
            f"no code fences, no explanation.\n"
            f"The JSON must contain exactly these fields (fill them with real values):\n"
            f"{json.dumps(example_obj, indent=2)}\n\n"
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
            # Attempt a single correction retry.
            retry_prompt = (
                f"Your previous response was invalid JSON. Please return ONLY valid JSON "
                f"matching this exact structure:\n{json.dumps(example_obj, indent=2)}\n\n"
                f"Do not include any other text.\n\nPrevious response:\n{response_text[:1000]}"
            )
            retry_response = self._client.models.generate_content(
                model=self._model_name,
                contents=retry_prompt,
            )
            retry_text = retry_response.text.strip()
            
            if retry_text.startswith("```json"):
                retry_text = retry_text.split("```json")[1].split("```")[0].strip()
            elif retry_text.startswith("```"):
                retry_text = retry_text.split("```")[1].split("```")[0].strip()
                
            if not retry_text.startswith("{"):
                import re as _re
                m = _re.search(r'\{.*\}', retry_text, _re.DOTALL)
                if m:
                    retry_text = m.group(0).strip()
            
            try:
                data = json.loads(retry_text)
            except json.JSONDecodeError:
                raise ValueError(f"Model returned invalid JSON after retry: {retry_text[:200]}")
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


def generate_text(prompt: str) -> str:
    """Generate raw text from a prompt using the configured AI provider.

    Used for free-form JSON generation where instructor's strict schema conversion
    (GENAI_TOOLS mode) would fail on open-ended types like Dict[str, Any].
    """
    from src.infrastructure.config import settings as _s

    if _s.AI_PROVIDER.lower() == "gemini":
        from google import genai as _genai
        try:
            _client = _genai.Client(api_key=_s.GEMINI_API_KEY)
            response = _client.models.generate_content(
                model=_s.GEMINI_MODEL,
                contents=prompt,
            )
            # Check if response was blocked by safety filters
            if hasattr(response, 'candidates') and response.candidates and hasattr(response.candidates[0], 'finish_reason'):
                if response.candidates[0].finish_reason == 'SAFETY':
                    from src.infrastructure.logging import get_logger
                    logger = get_logger(__name__)
                    logger.warning("Gemini API blocked response for safety reasons")
                    return ""
            result = response.text if hasattr(response, 'text') else ""
            return result or ""
        except Exception as e:
            from src.infrastructure.logging import get_logger
            logger = get_logger(__name__)
            logger.error("Gemini API call failed: %s", e)
            return ""

    if _s.AI_PROVIDER.lower() == "vertexai":
        # Reuse the cached wrapper which already has generate_content
        wrapper, _ = get_instructor_client()
        response = wrapper.generate_content(prompt)
        return response.text or ""

    # OpenAI-compatible provider
    from openai import OpenAI as _OpenAI
    _args: dict = {}
    if _s.OPENAI_API_KEY:
        _args["api_key"] = _s.OPENAI_API_KEY
    else:
        _args["api_key"] = "dummy_key_for_local"
    if _s.OPENAI_BASE_URL:
        _args["base_url"] = _s.OPENAI_BASE_URL
    _oa = _OpenAI(**_args)
    resp = _oa.chat.completions.create(
        model=_s.OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content or ""


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

        # Set credentials from env vars (no JSON file needed)
        if settings.VERTEXAI_CLIENT_EMAIL and settings.VERTEXAI_PRIVATE_KEY:
            from google.oauth2 import service_account
            credentials = service_account.Credentials.from_service_account_info(
                {
                    "type": "service_account",
                    "project_id": settings.VERTEXAI_PROJECT_ID,
                    "private_key": settings.VERTEXAI_PRIVATE_KEY.replace("\\n", "\n"),
                    "client_email": settings.VERTEXAI_CLIENT_EMAIL,
                    "token_uri": "https://oauth2.googleapis.com/token",
                },
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
        else:
            credentials = None

        # Initialize the unified genai client for Vertex AI
        client_kwargs = {
            "vertexai": True,
            "project": settings.VERTEXAI_PROJECT_ID,
            "location": settings.VERTEXAI_LOCATION,
        }
        if credentials:
            client_kwargs["credentials"] = credentials
        
        client = genai.Client(**client_kwargs)

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
