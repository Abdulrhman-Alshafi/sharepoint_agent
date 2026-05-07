"""Page content templates with webpart structures per purpose."""

from dataclasses import dataclass, field
from typing import Dict, Any, List
from src.domain.value_objects import WebPart
from src.domain.value_objects.page_purpose import PagePurpose


@dataclass
class ContentTemplate:
    """Content template for a specific page purpose.
    
    Contains a predefined webpart structure with placeholder values
    that are replaced with AI-generated or actual content.
    """
    purpose: PagePurpose
    webparts: List[WebPart] = field(default_factory=list)
    description: str = ""


class PageContentTemplates:
    """Factory for creating content templates per page purpose."""

    @staticmethod
    def get_template(purpose: PagePurpose) -> ContentTemplate:
        """Get content template for a given page purpose.
        
        Returns a template with placeholder webparts that can be customized.
        Placeholders use {PLACEHOLDER_NAME} syntax.
        """
        
        if purpose == PagePurpose.HOME:
            return PageContentTemplates._home_template()
        elif purpose == PagePurpose.TEAM:
            return PageContentTemplates._team_template()
        elif purpose == PagePurpose.NEWS:
            return PageContentTemplates._news_template()
        elif purpose == PagePurpose.DOCUMENTATION:
            return PageContentTemplates._documentation_template()
        elif purpose == PagePurpose.PROJECT_STATUS:
            return PageContentTemplates._project_status_template()
        elif purpose == PagePurpose.RESOURCE_LIBRARY:
            return PageContentTemplates._resource_library_template()
        elif purpose == PagePurpose.FAQ:
            return PageContentTemplates._faq_template()
        elif purpose == PagePurpose.ANNOUNCEMENT:
            return PageContentTemplates._announcement_template()
        else:
            return PageContentTemplates._default_template()

    @staticmethod
    def _home_template() -> ContentTemplate:
        """Home/Welcome page template."""
        return ContentTemplate(
            purpose=PagePurpose.HOME,
            description="Welcome page with hero banner and navigation",
            webparts=[
                WebPart(
                    type="Hero",
                    webpart_type="Hero",
                    properties={
                        "title": "{PAGE_TITLE}",
                        "description": "{PAGE_DESCRIPTION}",
                        "imageSource": "{HERO_IMAGE_URL}",
                        "link": "",
                    }
                ),
                WebPart(
                    type="QuickLinks",
                    webpart_type="QuickLinks",
                    properties={
                        "items": "{QUICK_LINKS}",
                    }
                ),
                WebPart(
                    type="Text",
                    webpart_type="Text",
                    properties={
                        "content": "{PAGE_CONTENT}",
                    }
                ),
            ]
        )

    @staticmethod
    def _team_template() -> ContentTemplate:
        """Team page template."""
        return ContentTemplate(
            purpose=PagePurpose.TEAM,
            description="Team info page with members and resources",
            webparts=[
                WebPart(
                    type="Hero",
                    webpart_type="Hero",
                    properties={
                        "title": "{PAGE_TITLE}",
                        "description": "Team Information",
                        "imageSource": "{HERO_IMAGE_URL}",
                        "link": "",
                    }
                ),
                WebPart(
                    type="Text",
                    webpart_type="Text",
                    properties={
                        "content": "{PAGE_CONTENT}",
                    }
                ),
                WebPart(
                    type="QuickLinks",
                    webpart_type="QuickLinks",
                    properties={
                        "items": "{QUICK_LINKS}",
                    }
                ),
            ]
        )

    @staticmethod
    def _news_template() -> ContentTemplate:
        """News/Blog page template."""
        return ContentTemplate(
            purpose=PagePurpose.NEWS,
            description="News article with featured image",
            webparts=[
                WebPart(
                    type="Hero",
                    webpart_type="Hero",
                    properties={
                        "title": "{PAGE_TITLE}",
                        "description": "Latest News & Updates",
                        "imageSource": "{HERO_IMAGE_URL}",
                        "link": "",
                    }
                ),
                WebPart(
                    type="Text",
                    webpart_type="Text",
                    properties={
                        "content": "{PAGE_CONTENT}",
                    }
                ),
                WebPart(
                    type="QuickLinks",
                    webpart_type="QuickLinks",
                    properties={
                        "items": "{QUICK_LINKS}",
                    }
                ),
            ]
        )

    @staticmethod
    def _documentation_template() -> ContentTemplate:
        """Documentation/Guide page template."""
        return ContentTemplate(
            purpose=PagePurpose.DOCUMENTATION,
            description="Documentation with guide content and quick links",
            webparts=[
                WebPart(
                    type="Hero",
                    webpart_type="Hero",
                    properties={
                        "title": "{PAGE_TITLE}",
                        "description": "Documentation & Guides",
                        "imageSource": "{HERO_IMAGE_URL}",
                        "link": "",
                    }
                ),
                WebPart(
                    type="QuickLinks",
                    webpart_type="QuickLinks",
                    properties={
                        "items": "{QUICK_LINKS}",
                    }
                ),
                WebPart(
                    type="Text",
                    webpart_type="Text",
                    properties={
                        "content": "{PAGE_CONTENT}",
                    }
                ),
            ]
        )

    @staticmethod
    def _project_status_template() -> ContentTemplate:
        """Project status/update page template."""
        return ContentTemplate(
            purpose=PagePurpose.PROJECT_STATUS,
            description="Project status and progress tracking",
            webparts=[
                WebPart(
                    type="Hero",
                    webpart_type="Hero",
                    properties={
                        "title": "{PAGE_TITLE}",
                        "description": "Project Status",
                        "imageSource": "{HERO_IMAGE_URL}",
                        "link": "",
                    }
                ),
                WebPart(
                    type="Text",
                    webpart_type="Text",
                    properties={
                        "content": "{PAGE_CONTENT}",
                    }
                ),
                WebPart(
                    type="QuickLinks",
                    webpart_type="QuickLinks",
                    properties={
                        "items": "{QUICK_LINKS}",
                    }
                ),
            ]
        )

    @staticmethod
    def _resource_library_template() -> ContentTemplate:
        """Resource library page template."""
        return ContentTemplate(
            purpose=PagePurpose.RESOURCE_LIBRARY,
            description="Organized resource library with categories",
            webparts=[
                WebPart(
                    type="Hero",
                    webpart_type="Hero",
                    properties={
                        "title": "{PAGE_TITLE}",
                        "description": "Resource Library",
                        "imageSource": "{HERO_IMAGE_URL}",
                        "link": "",
                    }
                ),
                WebPart(
                    type="QuickLinks",
                    webpart_type="QuickLinks",
                    properties={
                        "items": "{QUICK_LINKS}",
                    }
                ),
                WebPart(
                    type="Text",
                    webpart_type="Text",
                    properties={
                        "content": "{PAGE_CONTENT}",
                    }
                ),
            ]
        )

    @staticmethod
    def _faq_template() -> ContentTemplate:
        """FAQ page template."""
        return ContentTemplate(
            purpose=PagePurpose.FAQ,
            description="FAQ page with common questions and answers",
            webparts=[
                WebPart(
                    type="Hero",
                    webpart_type="Hero",
                    properties={
                        "title": "{PAGE_TITLE}",
                        "description": "Frequently Asked Questions",
                        "imageSource": "{HERO_IMAGE_URL}",
                        "link": "",
                    }
                ),
                WebPart(
                    type="QuickLinks",
                    webpart_type="QuickLinks",
                    properties={
                        "items": "{QUICK_LINKS}",
                    }
                ),
                WebPart(
                    type="Text",
                    webpart_type="Text",
                    properties={
                        "content": "{PAGE_CONTENT}",
                    }
                ),
            ]
        )

    @staticmethod
    def _announcement_template() -> ContentTemplate:
        """Announcement/Alert page template."""
        return ContentTemplate(
            purpose=PagePurpose.ANNOUNCEMENT,
            description="Important announcement page",
            webparts=[
                WebPart(
                    type="Hero",
                    webpart_type="Hero",
                    properties={
                        "title": "{PAGE_TITLE}",
                        "description": "{PAGE_DESCRIPTION}",
                        "imageSource": "{HERO_IMAGE_URL}",
                        "link": "",
                    }
                ),
                WebPart(
                    type="Text",
                    webpart_type="Text",
                    properties={
                        "content": "{PAGE_CONTENT}",
                    }
                ),
                WebPart(
                    type="QuickLinks",
                    webpart_type="QuickLinks",
                    properties={
                        "items": "{QUICK_LINKS}",
                    }
                ),
            ]
        )

    @staticmethod
    def _default_template() -> ContentTemplate:
        """Default template for unknown page purposes."""
        return ContentTemplate(
            purpose=PagePurpose.OTHER,
            description="Default page template",
            webparts=[
                WebPart(
                    type="Hero",
                    webpart_type="Hero",
                    properties={
                        "title": "{PAGE_TITLE}",
                        "description": "{PAGE_DESCRIPTION}",
                        "imageSource": "{HERO_IMAGE_URL}",
                        "link": "",
                    }
                ),
                WebPart(
                    type="QuickLinks",
                    webpart_type="QuickLinks",
                    properties={
                        "items": "{QUICK_LINKS}",
                    }
                ),
                WebPart(
                    type="Text",
                    webpart_type="Text",
                    properties={
                        "content": "{PAGE_CONTENT}",
                    }
                ),
            ]
        )
