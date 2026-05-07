"""Page content generator service using LLM."""

from typing import Dict, Any, List
from src.domain.value_objects.page_purpose import PagePurpose
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class PageContentGenerator:
    """Generates purpose-appropriate content for SharePoint pages using LLM.
    
    Generates Hero titles, descriptions, Quick Links, and main content text
    based on the page's detected purpose.
    
    Automatically initializes with the configured AI provider (Gemini, Vertex AI, or OpenAI).
    """

    def __init__(self, llm_service=None):
        """Initialize content generator.
        
        Args:
            llm_service: Optional LLM service for content generation.
                        If None, will auto-initialize from ai_client_factory.
        """
        self.llm_service = llm_service
        self._client = None
        self._model = None
        self._initialized = False

    def _ensure_llm_initialized(self):
        """Lazily initialize the LLM client from the app's AI client factory."""
        if self._initialized:
            return
        self._initialized = True
        
        if self.llm_service:
            return  # External service provided
        
        try:
            from src.infrastructure.external_services.ai_client_factory import get_instructor_client
            self._client, self._model = get_instructor_client()
            logger.info("[PageContentGenerator] LLM client initialized successfully")
        except Exception as e:
            logger.warning("[PageContentGenerator] Could not initialize LLM client: %s. Will use fallback templates.", e)

    async def generate_page_content(
        self,
        title: str,
        description: str,
        purpose: PagePurpose,
    ) -> Dict[str, Any]:
        """Generate all page content (Hero, description, quick links, main text).
        
        Args:
            title: Page title
            description: Page description/context
            purpose: Detected or specified page purpose
            
        Returns:
            Dictionary with keys:
                - hero_title: Hero webpart title
                - hero_description: Hero subtitle/description
                - hero_image_url: Hero image source URL
                - page_content: Main page HTML content
                - quick_links: List of quick link items
        """
        logger.info(f"[PageContentGenerator] Generating content for page: '{title}'")
        logger.debug(f"[PageContentGenerator] Purpose: {purpose.value}")
        
        # Ensure LLM is initialized
        self._ensure_llm_initialized()
        
        try:
            if self._client:
                logger.debug(f"[PageContentGenerator] Using LLM for content generation")
                content = await self._generate_with_llm_client(title, description, purpose)
                logger.info(f"[PageContentGenerator] LLM content generated successfully")
                logger.debug(f"[PageContentGenerator] Generated keys: {list(content.keys())}")
                return content
            elif self.llm_service:
                logger.debug(f"[PageContentGenerator] Using external LLM service")
                content = await self._generate_with_llm(title, description, purpose)
                logger.info(f"[PageContentGenerator] External LLM content generated successfully")
                return content
        except Exception as e:
            logger.warning(f"[PageContentGenerator] LLM generation failed: {e}. Using fallback content.")

        # Fallback: hardcoded content
        logger.info(f"[PageContentGenerator] Using fallback hardcoded content for purpose: {purpose.value}")
        content = self._generate_fallback_content(title, description, purpose)
        logger.info(f"[PageContentGenerator] Fallback content generated. Keys: {list(content.keys())}")
        logger.debug(f"[PageContentGenerator] Content: {content}")
        return content

    async def _generate_with_llm_client(
        self,
        title: str,
        description: str,
        purpose: PagePurpose,
    ) -> Dict[str, Any]:
        """Generate content using the app's AI client (GenAI / Vertex AI / OpenAI).
        
        Args:
            title: Page title
            description: Page description
            purpose: Page purpose
            
        Returns:
            Dictionary with generated content
        """
        import json as _json
        
        prompt = self._build_generation_prompt(title, description, purpose)
        
        try:
            # Use the GenAI client's generate_content method
            if hasattr(self._client, 'generate_content'):
                # GenAIInstructorWrapper (Vertex AI)
                response = self._client.generate_content(prompt)
                response_text = response.text.strip()
            elif hasattr(self._client, 'chat'):
                # Instructor-wrapped client — use raw completion
                from pydantic import BaseModel
                from typing import List as TypingList
                
                class PageContentModel(BaseModel):
                    hero_title: str = ""
                    hero_description: str = ""
                    hero_image_theme: str = "professional"
                    main_content: str = ""
                    quick_links: TypingList[Dict[str, str]] = []
                
                result = self._client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    response_model=PageContentModel,
                )
                
                return {
                    "hero_title": result.hero_title or title,
                    "hero_description": result.hero_description or "",
                    "hero_image_theme": result.hero_image_theme or "professional",
                    "hero_image_url": self._generate_unsplash_url(result.hero_image_theme or "professional"),
                    "page_content": result.main_content or "",
                    "quick_links": result.quick_links or [],
                }
            else:
                raise ValueError("Unknown client type — cannot generate content")
        except Exception as e:
            logger.warning(f"[PageContentGenerator] Structured generation failed: {e}. Trying raw text generation.")
            # Try raw text generation as fallback
            if hasattr(self._client, 'generate_content'):
                response = self._client.generate_content(prompt)
                response_text = response.text.strip()
            else:
                raise
        
        # Parse raw text response
        return self._parse_llm_content(response_text, title, purpose)

    @staticmethod
    def _build_generation_prompt(title: str, description: str, purpose: PagePurpose) -> str:
        """Build LLM prompt for content generation.
        
        Args:
            title: Page title
            description: Page description
            purpose: Page purpose
            
        Returns:
            Formatted prompt for LLM
        """
        purpose_context = {
            PagePurpose.HOME: "a welcoming landing page that introduces the site and provides navigation",
            PagePurpose.TEAM: "a team information page that describes the team, its mission, and resources",
            PagePurpose.NEWS: "a news article that announces updates and important information",
            PagePurpose.DOCUMENTATION: "a documentation page with guides, tutorials, and helpful information",
            PagePurpose.PROJECT_STATUS: "a project status page that reports progress and next steps",
            PagePurpose.RESOURCE_LIBRARY: "a resource library page that organizes and provides access to materials",
            PagePurpose.FAQ: "a FAQ page that answers common questions",
            PagePurpose.ANNOUNCEMENT: "an announcement page for important information or alerts",
        }
        
        context = purpose_context.get(purpose, "an informational page")
        
        return f"""Generate engaging content for a SharePoint page.

Page Title: {title}
Page Description: {description if description else "(No description provided)"}
Page Purpose: {context}

Generate content in the following JSON format:
{{
    "hero_title": "Compelling hero title (max 10 words)",
    "hero_description": "Hero subtitle or tagline (max 20 words)",
    "hero_image_theme": "Single word theme for hero image search (e.g., 'teamwork', 'growth', 'technology')",
    "main_content": "2-3 paragraph HTML content describing the page topic, wrapped in <p> tags",
    "quick_links": [
        {{"title": "Link Title 1", "url": "#"}},
        {{"title": "Link Title 2", "url": "#"}},
        {{"title": "Link Title 3", "url": "#"}}
    ]
}}

Generate natural, professional content suitable for a business intranet.
Ensure all text is appropriate and constructive.
IMPORTANT: Do NOT use placeholders like {{{{title}}}} or [Insert Name Here]. Generate the actual, final content.
Return ONLY valid JSON, no additional text."""

    def _parse_llm_content(self, response: str, title: str, purpose: PagePurpose) -> Dict[str, Any]:
        """Parse LLM-generated content.
        
        Args:
            response: Raw LLM response
            title: Original page title (fallback)
            purpose: Page purpose (for fallback)
            
        Returns:
            Dictionary with parsed content
        """
        try:
            import json
            # Clean markdown code blocks if present
            clean_response = response.strip()
            if clean_response.startswith("```json"):
                clean_response = clean_response.split("```json")[1].split("```")[0].strip()
            elif clean_response.startswith("```"):
                clean_response = clean_response.split("```")[1].split("```")[0].strip()
            
            # Try to extract JSON from response
            json_start = clean_response.find('{')
            json_end = clean_response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = clean_response[json_start:json_end]
                content = json.loads(json_str)
                
                # Validate and normalize
                hero_theme = content.get("hero_image_theme", "professional")
                result = {
                    "hero_title": content.get("hero_title", title),
                    "hero_description": content.get("hero_description", ""),
                    "hero_image_theme": hero_theme,
                    "hero_image_url": self._generate_unsplash_url(hero_theme),
                    "page_content": content.get("main_content", ""),
                    "quick_links": content.get("quick_links", []),
                }
                return result
        except Exception as e:
            logger.warning(f"Failed to parse LLM content: {e}. Using fallback.")
        
        # Return fallback if parsing fails
        return self._generate_fallback_content(title, "", purpose)

    def _generate_fallback_content(
        self,
        title: str,
        description: str,
        purpose: PagePurpose,
    ) -> Dict[str, Any]:
        """Generate fallback content when LLM is unavailable.
        
        Args:
            title: Page title
            description: Page description
            purpose: Page purpose
            
        Returns:
            Dictionary with fallback content
        """
        fallback_templates = {
            PagePurpose.HOME: {
                "hero_title": f"Welcome to {title}",
                "hero_description": "Your gateway to collaboration and success",
                "hero_image_theme": "welcome",
                "page_content": f"""<p>Welcome to {title}!</p>
<p>This is the central hub for team collaboration and information sharing. Explore the resources below to get started.</p>
<p>Browse the quick links to find relevant information and tools for your work.</p>""",
                "quick_links": [
                    {"title": "Getting Started", "url": "#"},
                    {"title": "Team Policies", "url": "#"},
                    {"title": "Contact Us", "url": "#"},
                ],
            },
            PagePurpose.TEAM: {
                "hero_title": f"{title} Team",
                "hero_description": "Working together for excellence",
                "hero_image_theme": "teamwork",
                "page_content": f"""<p>Meet the {title} team.</p>
<p>Our team is dedicated to delivering exceptional results and supporting each other's success.</p>
<p>Find team resources, schedules, and contact information below.</p>""",
                "quick_links": [
                    {"title": "Team Members", "url": "#"},
                    {"title": "Team Calendar", "url": "#"},
                    {"title": "Resources", "url": "#"},
                ],
            },
            PagePurpose.NEWS: {
                "hero_title": f"{title}",
                "hero_description": "Latest updates and announcements",
                "hero_image_theme": "news",
                "page_content": f"""<p>{title}</p>
<p>Stay informed about the latest developments and important updates in our organization.</p>
<p>Explore the announcements and news items below to learn more.</p>""",
                "quick_links": [
                    {"title": "Latest News", "url": "#"},
                    {"title": "Archives", "url": "#"},
                    {"title": "Subscribe", "url": "#"},
                ],
            },
            PagePurpose.DOCUMENTATION: {
                "hero_title": f"{title}",
                "hero_description": "Guides, tutorials, and helpful resources",
                "hero_image_theme": "documentation",
                "page_content": f"""<p>{title}</p>
<p>Find comprehensive guides and documentation to help you succeed.</p>
<p>Browse the available resources and tutorials below.</p>""",
                "quick_links": [
                    {"title": "Getting Started", "url": "#"},
                    {"title": "FAQ", "url": "#"},
                    {"title": "Support", "url": "#"},
                ],
            },
            PagePurpose.PROJECT_STATUS: {
                "hero_title": f"{title}",
                "hero_description": "Track progress and milestones",
                "hero_image_theme": "progress",
                "page_content": f"""<p>{title} Status</p>
<p>Stay updated on project progress, milestones, and next steps.</p>
<p>View details and access resources below.</p>""",
                "quick_links": [
                    {"title": "Progress Overview", "url": "#"},
                    {"title": "Milestones", "url": "#"},
                    {"title": "Team", "url": "#"},
                ],
            },
            PagePurpose.RESOURCE_LIBRARY: {
                "hero_title": f"{title}",
                "hero_description": "Access tools, templates, and materials",
                "hero_image_theme": "resources",
                "page_content": f"""<p>{title}</p>
<p>Browse our collection of resources, templates, and tools designed to support your work.</p>
<p>Find what you need using the categories and links below.</p>""",
                "quick_links": [
                    {"title": "Templates", "url": "#"},
                    {"title": "Tools", "url": "#"},
                    {"title": "Guidelines", "url": "#"},
                ],
            },
            PagePurpose.FAQ: {
                "hero_title": f"{title}",
                "hero_description": "Answers to your common questions",
                "hero_image_theme": "help",
                "page_content": f"""<p>{title}</p>
<p>Find answers to the most frequently asked questions below.</p>
<p>If you don't find what you're looking for, please contact our support team.</p>""",
                "quick_links": [
                    {"title": "General Questions", "url": "#"},
                    {"title": "Technical Help", "url": "#"},
                    {"title": "Contact Support", "url": "#"},
                ],
            },
            PagePurpose.ANNOUNCEMENT: {
                "hero_title": f"{title}",
                "hero_description": "Important information and updates",
                "hero_image_theme": "announcement",
                "page_content": f"""<p>{title}</p>
<p>Please read the important information below carefully.</p>
<p>For questions or more details, click the links provided.</p>""",
                "quick_links": [
                    {"title": "Details", "url": "#"},
                    {"title": "FAQ", "url": "#"},
                    {"title": "Contact Us", "url": "#"},
                ],
            },
        }
        
        content = fallback_templates.get(purpose, fallback_templates[PagePurpose.HOME])
        
        # Generate hero_image_url from theme
        hero_theme = content.get("hero_image_theme", "professional")
        content["hero_image_url"] = self._generate_unsplash_url(hero_theme)
        
        return content

    async def generate_hero_content(
        self,
        title: str,
        purpose: PagePurpose,
    ) -> Dict[str, str]:
        """Generate hero webpart content.
        
        Args:
            title: Page title
            purpose: Page purpose
            
        Returns:
            Dictionary with keys: hero_title, hero_description, hero_image_url
        """
        full_content = await self.generate_page_content(title, "", purpose)
        
        # Generate image URL (Unsplash search by theme)
        hero_theme = full_content.get("hero_image_theme", "professional")
        image_url = self._generate_unsplash_url(hero_theme)
        
        return {
            "hero_title": full_content.get("hero_title", title),
            "hero_description": full_content.get("hero_description", ""),
            "hero_image_url": image_url,
        }

    async def generate_description(
        self,
        title: str,
        description: str,
        purpose: PagePurpose,
    ) -> str:
        """Generate main page description/content.
        
        Args:
            title: Page title
            description: Page description
            purpose: Page purpose
            
        Returns:
            HTML content string
        """
        full_content = await self.generate_page_content(title, description, purpose)
        return full_content.get("page_content", "")

    async def generate_quick_links(
        self,
        title: str,
        purpose: PagePurpose,
    ) -> List[Dict[str, str]]:
        """Generate quick links for a page.
        
        Args:
            title: Page title
            purpose: Page purpose
            
        Returns:
            List of quick link items with title and url
        """
        full_content = await self.generate_page_content(title, "", purpose)
        return full_content.get("quick_links", [])

    @staticmethod
    def _generate_unsplash_url(theme: str) -> str:
        """Generate Unsplash image URL for a given theme.
        
        Args:
            theme: Image theme keyword
            
        Returns:
            Unsplash image URL
        """
        # Unsplash random image by search query
        # Format: https://source.unsplash.com/800x400/?keyword
        theme_safe = theme.lower().replace(" ", "-")
        return f"https://source.unsplash.com/800x400/?{theme_safe},professional"
