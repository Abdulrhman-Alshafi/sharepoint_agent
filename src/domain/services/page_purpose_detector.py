"""Page purpose detection service using LLM."""

from typing import Tuple, Optional
from src.domain.value_objects.page_purpose import PagePurpose
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class PagePurposeDetector:
    """Detects the purpose of a page based on its title and description.
    
    Uses LLM to classify pages into predefined purpose categories:
    Home, Team, News, Documentation, ProjectStatus, ResourceLibrary, FAQ, Announcement, Other.
    """

    def __init__(self, llm_service=None):
        """Initialize detector.
        
        Args:
            llm_service: Optional LLM service for purpose detection.
                        If None, will use keyword-based fallback.
        """
        self.llm_service = llm_service

    async def detect_purpose(
        self, 
        title: str, 
        description: str = ""
    ) -> Tuple[PagePurpose, float]:
        """Detect page purpose from title and description.
        
        Args:
            title: Page title
            description: Optional page description
            
        Returns:
            Tuple of (detected PagePurpose, confidence score 0.0-1.0)
        """
        logger.info(f"[PagePurposeDetector] Detecting purpose for page: '{title}'")
        logger.debug(f"[PagePurposeDetector] Description: '{description}'")
        logger.debug(f"[PagePurposeDetector] LLM service available: {self.llm_service is not None}")
        
        try:
            # Try LLM-based detection if service is available
            if self.llm_service:
                logger.debug(f"[PagePurposeDetector] Attempting LLM-based detection")
                result = await self._detect_with_llm(title, description)
                logger.info(f"[PagePurposeDetector] LLM detected purpose: {result[0].value} (confidence: {result[1]})")
                return result
        except Exception as e:
            logger.warning(f"[PagePurposeDetector] LLM detection failed: {e}. Falling back to keyword detection.")

        # Fallback: keyword-based detection
        logger.debug(f"[PagePurposeDetector] Using keyword-based fallback detection")
        purpose, confidence = self._detect_with_keywords(title, description)
        logger.info(f"[PagePurposeDetector] Keyword detection result: {purpose.value} (confidence: {confidence})")
        return purpose, confidence

    async def _detect_with_llm(
        self, 
        title: str, 
        description: str
    ) -> Tuple[PagePurpose, float]:
        """Detect purpose using LLM.
        
        Args:
            title: Page title
            description: Optional page description
            
        Returns:
            Tuple of (detected PagePurpose, confidence score)
        """
        prompt = self._build_detection_prompt(title, description)
        
        response = await self.llm_service.generate_response(
            prompt=prompt,
            temperature=0.3,  # Low temperature for consistent classification
            max_tokens=100,
        )
        
        # Parse LLM response to extract purpose and confidence
        return self._parse_llm_response(response)

    @staticmethod
    def _build_detection_prompt(title: str, description: str) -> str:
        """Build LLM prompt for page purpose detection.
        
        Args:
            title: Page title
            description: Optional page description
            
        Returns:
            Formatted prompt for LLM
        """
        return f"""Classify the purpose of this SharePoint page based on its title and description.

Page Title: {title}
Page Description: {description if description else "(No description provided)"}

Classify into ONE of these purposes:
- Home: Welcome/landing page
- Team: Team information and resources
- News: News articles, announcements, blog posts
- Documentation: Guides, how-to, documentation
- ProjectStatus: Project updates, status reports
- ResourceLibrary: Organized resources, downloads, libraries
- FAQ: Frequently asked questions
- Announcement: Important announcements, alerts
- Other: Unclassifiable or generic page

Respond in this format:
PURPOSE: [one of the above]
CONFIDENCE: [0.0-1.0]

Do not include explanations or additional text."""

    @staticmethod
    def _parse_llm_response(response: str) -> Tuple[PagePurpose, float]:
        """Parse LLM response to extract purpose and confidence.
        
        Args:
            response: Raw LLM response text
            
        Returns:
            Tuple of (PagePurpose, confidence score)
        """
        try:
            lines = response.strip().split('\n')
            purpose_str = ""
            confidence = 0.5
            
            for line in lines:
                if line.startswith("PURPOSE:"):
                    purpose_str = line.replace("PURPOSE:", "").strip()
                elif line.startswith("CONFIDENCE:"):
                    try:
                        confidence = float(line.replace("CONFIDENCE:", "").strip())
                    except ValueError:
                        confidence = 0.5
            
            # Map string to PagePurpose enum
            purpose = PagePurposeDetector._map_to_purpose(purpose_str)
            return purpose, confidence
        except Exception as e:
            logger.warning(f"Failed to parse LLM response: {e}. Using fallback.")
            return PagePurpose.OTHER, 0.3

    def _detect_with_keywords(
        self, 
        title: str, 
        description: str
    ) -> Tuple[PagePurpose, float]:
        """Detect purpose using keyword matching.
        
        Fallback when LLM is unavailable. Uses scored keyword matching
        via :mod:`src.detection.classification.page_purpose_classifier`.
        
        Args:
            title: Page title
            description: Optional page description
            
        Returns:
            Tuple of (detected PagePurpose, confidence score)
        """
        from src.detection.classification.page_purpose_classifier import classify_page_purpose_enum
        return classify_page_purpose_enum(title, description)

    @staticmethod
    def _map_to_purpose(purpose_str: str) -> PagePurpose:
        """Map string to PagePurpose enum.
        
        Args:
            purpose_str: Purpose as string
            
        Returns:
            Matching PagePurpose enum or OTHER
        """
        purpose_str = purpose_str.strip().upper()
        
        mapping = {
            "HOME": PagePurpose.HOME,
            "TEAM": PagePurpose.TEAM,
            "NEWS": PagePurpose.NEWS,
            "DOCUMENTATION": PagePurpose.DOCUMENTATION,
            "PROJECTSTATUS": PagePurpose.PROJECT_STATUS,
            "PROJECT_STATUS": PagePurpose.PROJECT_STATUS,
            "RESOURCELIBRARY": PagePurpose.RESOURCE_LIBRARY,
            "RESOURCE_LIBRARY": PagePurpose.RESOURCE_LIBRARY,
            "FAQ": PagePurpose.FAQ,
            "ANNOUNCEMENT": PagePurpose.ANNOUNCEMENT,
        }
        
        return mapping.get(purpose_str, PagePurpose.OTHER)
