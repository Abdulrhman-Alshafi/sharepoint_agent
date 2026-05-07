"""Web part decision engine for choosing between built-in and custom SPFx web parts."""

from typing import List, Optional
from src.domain.entities.preview import (
    WebPartCatalogEntry,
    WebPartCapability,
    WebPartDecision,
    WebPartType
)
from src.infrastructure.external_services.ai_client_factory import get_instructor_client
from src.infrastructure.logging import get_logger
from pydantic import BaseModel, Field

logger = get_logger(__name__)


class WebPartRequirementAnalysis(BaseModel):
    """AI analysis of web part requirement."""
    complexity_score: float = Field(description="Complexity 0.0-1.0 (0=simple, 1=very complex)", ge=0.0, le=1.0)
    requires_custom_logic: bool = Field(description="Whether custom business logic is needed")
    requires_unique_ui: bool = Field(description="Whether unique UI design is needed")
    requires_advanced_interaction: bool = Field(description="Whether advanced user interaction is needed")
    matched_builtin: Optional[str] = Field(description="Name of matching built-in web part if found", default=None)
    custom_features: List[str] = Field(description="List of features that require custom development")
    reasoning: str = Field(description="Explanation of the analysis")


class WebPartDecisionEngine:
    """Service for deciding between built-in and custom SPFx web parts."""
    
    def __init__(self):
        """Initialize decision engine with built-in web part catalog."""
        self.catalog = self._build_catalog()
    
    def _build_catalog(self) -> List[WebPartCatalogEntry]:
        """Build catalog of built-in SharePoint web parts."""
        return [
            WebPartCatalogEntry(
                web_part_name="Text",
                web_part_type="TextWebPart",
                category="content",
                capabilities=[
                    WebPartCapability(
                        name="Rich Text Editing",
                        description="Format text with headings, bold, italic, lists, etc.",
                        supports_customization=True
                    )
                ],
                common_use_cases=[
                    "display formatted text",
                    "show descriptions",
                    "add headings and paragraphs",
                    "display instructions",
                    "welcome message"
                ]
            ),
            WebPartCatalogEntry(
                web_part_name="Image",
                web_part_type="ImageWebPart",
                category="media",
                capabilities=[
                    WebPartCapability(
                        name="Image Display",
                        description="Display images with alt text and captions",
                        supports_customization=True
                    )
                ],
                common_use_cases=[
                    "display logo",
                    "show banner image",
                    "display photo",
                    "add visual content",
                    "show illustration"
                ]
            ),
            WebPartCatalogEntry(
                web_part_name="Hero",
                web_part_type="HeroWebPart",
                category="content",
                capabilities=[
                    WebPartCapability(
                        name="Hero Tiles",
                        description="Display up to 5 tiles with images, titles, and links",
                        supports_customization=True
                    )
                ],
                common_use_cases=[
                    "hero section",
                    "featured content",
                    "highlight key areas",
                    "call to action tiles",
                    "banner with links"
                ]
            ),
            WebPartCatalogEntry(
                web_part_name="Quick Links",
                web_part_type="QuickLinksWebPart",
                category="navigation",
                capabilities=[
                    WebPartCapability(
                        name="Link Collection",
                        description="Display links with icons, descriptions, and layouts (compact, filmstrip, button, list)",
                        supports_customization=True,
                        supports_data_source=False
                    )
                ],
                common_use_cases=[
                    "navigation links",
                    "quick access links",
                    "resource links",
                    "policy links",
                    "useful links section",
                    "external resources"
                ]
            ),
            WebPartCatalogEntry(
                web_part_name="List",
                web_part_type="ListWebPart",
                category="data",
                capabilities=[
                    WebPartCapability(
                        name="List Display",
                        description="Display SharePoint list items with filtering and sorting",
                        supports_data_source=True,
                        supports_customization=True
                    )
                ],
                common_use_cases=[
                    "show list items",
                    "display announcements",
                    "show tasks",
                    "display data from list",
                    "announcements feed"
                ]
            ),
            WebPartCatalogEntry(
                web_part_name="Document Library",
                web_part_type="DocumentLibraryWebPart",
                category="data",
                capabilities=[
                    WebPartCapability(
                        name="Document Display",
                        description="Display documents from a library with search and filtering",
                        supports_data_source=True,
                        supports_customization=True
                    )
                ],
                common_use_cases=[
                    "show documents",
                    "display files",
                    "document repository",
                    "file library",
                    "shared documents"
                ]
            ),
            WebPartCatalogEntry(
                web_part_name="News",
                web_part_type="NewsWebPart",
                category="content",
                capabilities=[
                    WebPartCapability(
                        name="News Display",
                        description="Display news posts with layouts (hub, list, carousel, tile)",
                        supports_data_source=True
                    )
                ],
                common_use_cases=[
                    "news feed",
                    "latest news",
                    "announcements carousel",
                    "company news",
                    "updates section"
                ]
            ),
            WebPartCatalogEntry(
                web_part_name="People",
                web_part_type="PeopleWebPart",
                category="social",
                capabilities=[
                    WebPartCapability(
                        name="People Cards",
                        description="Display people profiles with photos and contact info",
                        supports_data_source=True
                    )
                ],
                common_use_cases=[
                    "team directory",
                    "show team members",
                    "contact list",
                    "department staff",
                    "leadership team"
                ]
            ),
            WebPartCatalogEntry(
                web_part_name="Events",
                web_part_type="EventsWebPart",
                category="data",
                capabilities=[
                    WebPartCapability(
                        name="Calendar Events",
                        description="Display events from a calendar list with different views",
                        supports_data_source=True
                    )
                ],
                common_use_cases=[
                    "upcoming events",
                    "calendar",
                    "event list",
                    "schedule",
                    "meetings calendar"
                ]
            ),
            WebPartCatalogEntry(
                web_part_name="Button",
                web_part_type="ButtonWebPart",
                category="navigation",
                capabilities=[
                    WebPartCapability(
                        name="Clickable Button",
                        description="Single button with customizable text, icon, and link",
                        supports_customization=True
                    )
                ],
                common_use_cases=[
                    "call to action",
                    "submit button",
                    "link button",
                    "action button"
                ]
            ),
            WebPartCatalogEntry(
                web_part_name="Embed",
                web_part_type="EmbedWebPart",
                category="media",
                capabilities=[
                    WebPartCapability(
                        name="Embed External Content",
                        description="Embed websites, videos (YouTube, Vimeo), Forms, Stream videos",
                        supports_customization=False,
                        limitations=["Depends on external service availability", "Limited control over styling"]
                    )
                ],
                common_use_cases=[
                    "embed video",
                    "show form",
                    "embed external content",
                    "youtube video",
                    "power bi report"
                ]
            ),
            WebPartCatalogEntry(
                web_part_name="File Viewer",
                web_part_type="FileViewerWebPart",
                category="media",
                capabilities=[
                    WebPartCapability(
                        name="File Preview",
                        description="Preview Office documents, PDFs, images inline",
                        supports_data_source=True
                    )
                ],
                common_use_cases=[
                    "show pdf",
                    "display document",
                    "preview file",
                    "show policy document"
                ]
            ),
            WebPartCatalogEntry(
                web_part_name="Divider",
                web_part_type="DividerWebPart",
                category="content",
                capabilities=[
                    WebPartCapability(
                        name="Visual Separator",
                        description="Simple line or space to separate content sections",
                        supports_customization=True
                    )
                ],
                common_use_cases=[
                    "section divider",
                    "visual separator",
                    "spacing"
                ]
            ),
            WebPartCatalogEntry(
                web_part_name="Highlighted Content",
                web_part_type="HighlightedContentWebPart",
                category="data",
                capabilities=[
                    WebPartCapability(
                        name="Dynamic Content Query",
                        description="Query and display content based on filters (document type, modified date, tags)",
                        supports_data_source=True,
                        supports_customization=True
                    )
                ],
                common_use_cases=[
                    "recent documents",
                    "filtered content",
                    "dynamic document list",
                    "show tagged items"
                ]
            ),
            WebPartCatalogEntry(
                web_part_name="Spacer",
                web_part_type="SpacerWebPart",
                category="content",
                capabilities=[
                    WebPartCapability(
                        name="Adjustable Space",
                        description="Add customizable vertical space between web parts",
                        supports_customization=True
                    )
                ],
                common_use_cases=[
                    "add space",
                    "vertical spacing",
                    "layout spacing"
                ]
            )
        ]
    
    async def decide_web_part_type(self, requirement: str) -> WebPartDecision:
        """Decide whether to use built-in or custom web part for a requirement.
        
        Args:
            requirement: User's web part requirement description
            
        Returns:
            WebPartDecision with recommendation
        """
        # First, try simple keyword matching with catalog
        matched_entry = self._find_matching_builtin(requirement)
        
        # Use AI to analyze requirement complexity
        analysis = await self._analyze_requirement(requirement, matched_entry)
        
        # Make decision based on analysis
        if analysis.matched_builtin and not analysis.requires_custom_logic and analysis.complexity_score < 0.6:
            # Use built-in
            builtin = next((entry for entry in self.catalog if entry.web_part_name == analysis.matched_builtin), matched_entry)
            
            return WebPartDecision(
                requirement=requirement,
                recommended_type=WebPartType.BUILTIN,
                builtin_option=builtin,
                reasoning=analysis.reasoning or f"Built-in '{builtin.web_part_name}' web part provides the needed functionality without custom development.",
                confidence=1.0 - analysis.complexity_score
            )
        else:
            # Use custom
            return WebPartDecision(
                requirement=requirement,
                recommended_type=WebPartType.CUSTOM,
                custom_features_needed=analysis.custom_features,
                reasoning=analysis.reasoning or "This requirement needs custom development for specialized functionality.",
                confidence=analysis.complexity_score
            )
    
    def _find_matching_builtin(self, requirement: str) -> Optional[WebPartCatalogEntry]:
        """Find matching built-in web part using keyword matching.
        
        Args:
            requirement: Requirement description
            
        Returns:
            Matching WebPartCatalogEntry or None
        """
        requirement_lower = requirement.lower()
        
        # Try to match with use cases
        for entry in self.catalog:
            if entry.matches_requirement(requirement):
                return entry
        
        return None
    
    async def _analyze_requirement(self, requirement: str, matched_builtin: Optional[WebPartCatalogEntry]) -> WebPartRequirementAnalysis:
        """Use AI to analyze requirement complexity and needs.
        
        Args:
            requirement: User's requirement
            matched_builtin: Catalog entry if keyword match found
            
        Returns:
            WebPartRequirementAnalysis with AI insights
        """
        try:
            client, model = get_instructor_client()
            
            builtin_context = ""
            if matched_builtin:
                builtin_context = f"\n\nPotential match found: {matched_builtin.web_part_name} - {', '.join(matched_builtin.common_use_cases)}"
            
            prompt = f"""Analyze this web part requirement for a SharePoint page:

Requirement: "{requirement}"{builtin_context}

SharePoint has many built-in web parts like Text, Image, Hero, Quick Links, List, Document Library, News, People, Events, Button, Embed, etc.

Determine:
1. Complexity score (0.0-1.0): How complex is this requirement?
2. Does it require custom business logic or data processing?
3. Does it need a unique UI design not available in built-in web parts?
4. Does it need advanced user interaction (drag-drop, complex forms, animations)?
5. Which built-in web part matches best (if any)?
6. What features would require custom development?
7. Your reasoning

Simple requirements like "show text", "display links", "list items", "show documents" should use built-in web parts.
Complex requirements like "interactive timeline with animations", "custom data visualization", "complex workflow forms" need custom development."""

            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a SharePoint and SPFx expert who knows when to use built-in web parts vs custom development."},
                    {"role": "user", "content": prompt}
                ],
                response_model=WebPartRequirementAnalysis,
                max_retries=2
            )
            
            return response
        
        except Exception as e:
            logger.warning("AI requirement analysis failed: %s", e)
            # Fallback to simple heuristic
            is_simple = any(keyword in requirement.lower() for keyword in [
                "text", "image", "link", "list", "document", "news", "people", "event", "button"
            ])
            
            return WebPartRequirementAnalysis(
                complexity_score=0.3 if is_simple else 0.7,
                requires_custom_logic=not is_simple,
                requires_unique_ui=not is_simple,
                requires_advanced_interaction=not is_simple,
                matched_builtin=matched_builtin.web_part_name if matched_builtin else None,
                custom_features=["Custom implementation needed"] if not is_simple else [],
                reasoning="Automatic analysis based on keywords"
            )
    
    def get_catalog(self) -> List[WebPartCatalogEntry]:
        """Get the full catalog of built-in web parts.
        
        Returns:
            List of WebPartCatalogEntry
        """
        return self.catalog
    
    def get_web_part_by_name(self, name: str) -> Optional[WebPartCatalogEntry]:
        """Get a specific web part from catalog by name.
        
        Args:
            name: Web part name
            
        Returns:
            WebPartCatalogEntry if found
        """
        return next((entry for entry in self.catalog if entry.web_part_name.lower() == name.lower()), None)
