"""Site provisioner for SharePoint sites."""

from typing import List, Tuple, Dict, Any, Callable, Awaitable, Optional
import time
from src.domain.entities import ProvisioningBlueprint, ActionType
from src.domain.repositories import ISiteRepository, IPageRepository
from src.domain.exceptions import SharePointProvisioningException
from src.infrastructure.logging import get_logger
from src.domain.services.page_purpose_detector import PagePurposeDetector
from src.infrastructure.services.content_template_manager import ContentTemplateManager
from src.infrastructure.services.page_content_generator import PageContentGenerator
from src.infrastructure.repositories.utils.webpart_composer import WebPartComposer

logger = get_logger(__name__)

# Type alias for post-provision hook: receives site result dict, returns nothing
PostProvisionHook = Callable[[Dict[str, Any]], Awaitable[None]]

# Registry of hooks to run after every successful site creation
_POST_PROVISION_HOOKS: List[PostProvisionHook] = []


def register_post_provision_hook(hook: PostProvisionHook) -> None:
    """Register a coroutine to run after every site is created."""
    _POST_PROVISION_HOOKS.append(hook)


class SiteProvisioner:
    """Handles provisioning of SharePoint sites.
    
    Also manages page content population for pages included in site blueprints.
    """

    def __init__(
        self,
        repository: ISiteRepository,
        page_repository: Optional[IPageRepository] = None,
        purpose_detector: Optional[PagePurposeDetector] = None,
        template_manager: Optional[ContentTemplateManager] = None,
        content_generator: Optional[PageContentGenerator] = None,
    ):
        self.repository = repository
        self.page_repository = page_repository
        self.purpose_detector = purpose_detector or PagePurposeDetector()
        self.template_manager = template_manager or ContentTemplateManager()
        self.content_generator = content_generator or PageContentGenerator()

    async def _run_post_provision_hooks(self, site_result: Dict[str, Any]) -> None:
        """Run all registered post-provision hooks for a newly created site."""
        for hook in _POST_PROVISION_HOOKS:
            try:
                await hook(site_result)
            except Exception as exc:
                logger.warning("Post-provision hook %s failed: %s", hook.__name__, exc)

    async def _populate_blueprint_pages(
        self,
        pages: List[Any],
        site_id: str,
    ) -> List[str]:
        """Populate blueprint pages with content based on their purpose.
        
        Args:
            pages: List of pages from blueprint
            site_id: ID of the site to which pages belong
            
        Returns:
            List of warnings from page population
        """
        logger.info(f"[SiteProvisioner] Starting page content population for {len(pages)} pages")
        logger.debug(f"[SiteProvisioner] Site ID: {site_id}")
        warnings = []
        
        for idx, page in enumerate(pages):
            if page.action != ActionType.CREATE:
                logger.debug(f"[SiteProvisioner] Page {idx+1}: Skipping (action={page.action})")
                continue
            
            try:
                logger.info(f"[SiteProvisioner] Page {idx+1}/{len(pages)}: Populating content for '{page.title}'")
                logger.debug(f"[SiteProvisioner] Page current webparts: {len(page.webparts)}")
                
                # Detect page purpose
                logger.debug(f"[SiteProvisioner] Detecting purpose...")
                purpose, confidence = await self.purpose_detector.detect_purpose(
                    page.title,
                    getattr(page, "description", ""),
                )
                logger.info(f"[SiteProvisioner] Page purpose: {purpose.value} (confidence: {confidence})")
                
                # Get template for purpose
                logger.debug(f"[SiteProvisioner] Retrieving template for purpose {purpose.value}")
                template = self.template_manager.get_template(purpose)
                if not template:
                    logger.error(f"[SiteProvisioner] No template found for purpose {purpose}")
                    warnings.append(f"No template found for page '{page.title}' (purpose: {purpose.value})")
                    continue
                
                logger.debug(f"[SiteProvisioner] Template retrieved with {len(template.webparts)} webparts")
                
                # Generate content for the page
                logger.debug(f"[SiteProvisioner] Generating content...")
                generated_content = await self.content_generator.generate_page_content(
                    page.title,
                    getattr(page, "description", ""),
                    purpose,
                )
                logger.debug(f"[SiteProvisioner] Content generated. Keys: {list(generated_content.keys())}")
                
                # Compose webparts from template + generated content
                logger.debug(f"[SiteProvisioner] Composing webparts...")
                composed_webparts = WebPartComposer.compose_webparts(
                    template.webparts,
                    generated_content,
                )
                logger.info(f"[SiteProvisioner] Webparts composed: {len(composed_webparts)} webparts")
                
                # Validate composed webparts
                logger.debug(f"[SiteProvisioner] Validating webparts...")
                validation_errors = WebPartComposer.validate_webparts(composed_webparts)
                if validation_errors:
                    for error in validation_errors:
                        logger.warning(f"[SiteProvisioner] Validation warning: {error}")
                else:
                    logger.debug(f"[SiteProvisioner] Webpart validation passed")
                
                # Update page with composed webparts
                logger.debug(f"[SiteProvisioner] Updating page.webparts...")
                page.webparts = composed_webparts
                logger.info(f"[SiteProvisioner] Page {idx+1} successfully populated with {len(page.webparts)} webparts")
                
            except Exception as e:
                warning_msg = f"Failed to populate content for page '{page.title}': {str(e)}"
                logger.error(f"[SiteProvisioner] {warning_msg}", exc_info=True)
                warnings.append(warning_msg)
                continue
        
        logger.info(f"[SiteProvisioner] Page population complete. Warnings: {len(warnings)}")
        return warnings

    async def provision(self, blueprint: ProvisioningBlueprint) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
        """Provision all sites from the blueprint.
        
        Also populates pages with content based on their purpose.
        """
        logger.info(f"[SiteProvisioner.provision] Starting site provisioning from blueprint")
        logger.debug(f"[SiteProvisioner.provision] Blueprint sites: {len(blueprint.sites)}, pages: {len(blueprint.pages)}")
        created_sites = []
        resource_links = []
        warnings = []

        for site in blueprint.sites:
            try:
                if site.action == ActionType.CREATE:
                    logger.info("Creating site: %s", site.title)
                    result = await self.repository.create_site(site)
                    created_sites.append(result)
                    
                    # Get site ID or fallback to webUrl for identification
                    site_id = result.get("id") or result.get("resource_id")
                    site_link = result.get("webUrl") or result.get("resource_link", "")
                    
                    # Log site creation with available identifiers
                    if site_id:
                        logger.info(f"[SiteProvisioner.provision] Site created: {site.title} (ID: {site_id})")
                    elif site_link:
                        logger.info(f"[SiteProvisioner.provision] Site created: {site.title} (Link: {site_link})")
                    else:
                        logger.warning(f"[SiteProvisioner.provision] Site created: {site.title} (No ID or link available)")
                    
                    # Track site link for user response
                    if site_link:
                        resource_links.append(site_link)

                    # Run post-provision hooks (branding, settings, etc.)
                    await self._run_post_provision_hooks(result)
                    
                    # Populate pages with content (ENTRY POINT 1)
                    logger.info(f"[SiteProvisioner.provision] Checking for page population...")
                    logger.debug(f"[SiteProvisioner.provision] Pages in blueprint: {len(blueprint.pages)}")
                    logger.debug(f"[SiteProvisioner.provision] Page repository available: {self.page_repository is not None}")
                    
                    # Use site_id for page population if available, otherwise use site_link as context
                    site_context_id = site_id or site_link
                    
                    if blueprint.pages and self.page_repository:
                        logger.info(f"[SiteProvisioner.provision] Populating {len(blueprint.pages)} blueprint pages")
                        page_warnings = await self._populate_blueprint_pages(
                            blueprint.pages,
                            site_context_id,
                        )
                        warnings.extend(page_warnings)
                    elif blueprint.pages:
                        logger.warning(f"[SiteProvisioner.provision] Pages exist but page_repository is None - skipping population")
                    else:
                        logger.debug(f"[SiteProvisioner.provision] No pages in blueprint to populate")
                    
                elif site.action == ActionType.DELETE:
                    warnings.append(f"Skipping delete action for site '{site.title}' during general provisioning. Use explicit delete command.")

            except SharePointProvisioningException as e:
                warning_msg = f"Failed to provision site '{site.title}': {str(e)}"
                logger.warning("%s", warning_msg)
                warnings.append(warning_msg)
                continue
            except Exception as e:
                warning_msg = f"Unexpected error creating site '{site.title}': {str(e)}"
                logger.warning("%s", warning_msg)
                warnings.append(warning_msg)
                continue

        logger.info(f"[SiteProvisioner.provision] Provisioning complete. Sites: {len(created_sites)}, Warnings: {len(warnings)}")
        return created_sites, resource_links, warnings
