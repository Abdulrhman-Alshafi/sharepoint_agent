"""Page provisioner for SharePoint pages."""

from typing import List, Tuple, Dict, Any, Optional
from src.domain.entities import ProvisioningBlueprint, ActionType
from src.domain.repositories import IPageRepository
from src.domain.exceptions import SharePointProvisioningException
from src.infrastructure.logging import get_logger
from src.domain.services.page_purpose_detector import PagePurposeDetector
from src.infrastructure.services.content_template_manager import ContentTemplateManager
from src.infrastructure.services.page_content_generator import PageContentGenerator
from src.infrastructure.repositories.utils.webpart_composer import WebPartComposer

logger = get_logger(__name__)


class PageProvisioner:
    """Handles provisioning of SharePoint pages.
    
    Also populates pages with content based on their detected purpose (ENTRY POINT 2).
    """

    def __init__(
        self,
        repository: IPageRepository,
        purpose_detector: Optional[PagePurposeDetector] = None,
        template_manager: Optional[ContentTemplateManager] = None,
        content_generator: Optional[PageContentGenerator] = None,
    ):
        """Initialize page provisioner.
        
        Args:
            repository: Page repository for page operations
            purpose_detector: Service for detecting page purpose
            template_manager: Service for retrieving content templates
            content_generator: Service for generating page content
        """
        self.repository = repository
        self.purpose_detector = purpose_detector or PagePurposeDetector()
        self.template_manager = template_manager or ContentTemplateManager()
        self.content_generator = content_generator or PageContentGenerator()

    async def provision(self, blueprint: ProvisioningBlueprint, site_id: Optional[str] = None) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
        """Provision all pages from the blueprint.
        
        Also populates pages with content based on their detected purpose (ENTRY POINT 2).
        
        Args:
            blueprint: Provisioning blueprint containing pages
            site_id: Optional SharePoint site ID to target
            
        Returns:
            Tuple of (created pages list, list of resource links, list of warnings)
        """
        logger.info(f"[PageProvisioner.provision] Starting page provisioning")
        logger.debug(f"[PageProvisioner.provision] Pages to process: {len(blueprint.pages)}, Site ID: {site_id}")
        created_pages = []
        resource_links = []
        warnings = []

        for idx, sp_page in enumerate(blueprint.pages):
            try:
                logger.debug(f"[PageProvisioner.provision] Processing page {idx+1}/{len(blueprint.pages)}: {sp_page.title}")
                
                if sp_page.action == ActionType.CREATE:
                    logger.info(f"[PageProvisioner.provision] Creating page: {sp_page.title}")
                    
                    result = await self.repository.create_page(sp_page, site_id=site_id)
                    created_pages.append(result)
                    resource_links.append(result.get("resource_link", ""))
                    logger.info(f"[PageProvisioner.provision] Page created: {sp_page.title}")
                    
                elif sp_page.action == ActionType.UPDATE:
                    if sp_page.page_id:
                        logger.info(f"[PageProvisioner.provision] Updating page: {sp_page.title}")

                        result = await self.repository.update_page_content(sp_page.page_id, sp_page)
                        resource_links.append(result.get("resource_link", ""))
                        logger.info(f"[PageProvisioner.provision] Page updated: {sp_page.title}")
                        
                elif sp_page.action == ActionType.DELETE:
                    if sp_page.page_id:
                        logger.info(f"[PageProvisioner.provision] Deleting page: {sp_page.title}")
                        await self.repository.delete_page(sp_page.page_id)
                        logger.info(f"[PageProvisioner.provision] Page deleted: {sp_page.title}")
                        
            except SharePointProvisioningException as e:
                # Log error and add to warnings
                warning_msg = f"Failed to provision page '{sp_page.title}': {str(e)}"
                logger.warning("%s", warning_msg)
                warnings.append(warning_msg)
                continue
            except Exception as e:
                # Log any other errors
                warning_msg = f"Unexpected error provisioning page '{sp_page.title}': {str(e)}"
                logger.error(f"[PageProvisioner.provision] {warning_msg}", exc_info=True)
                warnings.append(warning_msg)
                continue

        logger.info(f"[PageProvisioner.provision] Provisioning complete. Created: {len(created_pages)}, Warnings: {len(warnings)}")
        return created_pages, resource_links, warnings

    async def _populate_page_content(self, sp_page: Any) -> None:
        """Populate a page with content based on its purpose.
        
        Detects page purpose, retrieves template, generates content,
        and composes final webparts for the page.
        
        Args:
            sp_page: SPPage entity to populate
        """
        logger.info("[PageProvisioner] Page content population is temporarily disabled")
        return

        try:
            logger.info(f"[PageProvisioner] Starting content population for page: '{sp_page.title}'")
            logger.debug(f"[PageProvisioner] Current webparts count: {len(sp_page.webparts)}")
            
            # Detect page purpose
            logger.debug(f"[PageProvisioner] Detecting page purpose...")
            purpose, confidence = await self.purpose_detector.detect_purpose(
                sp_page.title,
                getattr(sp_page, "description", ""),
            )
            logger.info(f"[PageProvisioner] Page purpose detected: {purpose.value} (confidence: {confidence})")
            
            # Get template for purpose
            logger.debug(f"[PageProvisioner] Retrieving template for purpose: {purpose.value}")
            template = self.template_manager.get_template(purpose)
            if not template:
                logger.error(f"[PageProvisioner] No template found for purpose {purpose}")
                return
            
            logger.debug(f"[PageProvisioner] Template retrieved with {len(template.webparts)} webparts")
            
            # Generate content for the page
            logger.debug(f"[PageProvisioner] Generating page content...")
            generated_content = await self.content_generator.generate_page_content(
                sp_page.title,
                getattr(sp_page, "description", ""),
                purpose,
            )
            logger.debug(f"[PageProvisioner] Content generated. Keys: {list(generated_content.keys())}")
            logger.debug(f"[PageProvisioner] Content preview: {str(generated_content)[:200]}...")
            
            # Compose webparts from template + generated content
            logger.debug(f"[PageProvisioner] Composing webparts...")
            composed_webparts = WebPartComposer.compose_webparts(
                template.webparts,
                generated_content,
            )
            logger.info(f"[PageProvisioner] Webparts composed successfully: {len(composed_webparts)} webparts")
            
            # Validate composed webparts
            logger.debug(f"[PageProvisioner] Validating composed webparts...")
            validation_errors = WebPartComposer.validate_webparts(composed_webparts)
            if validation_errors:
                for error in validation_errors:
                    logger.warning(f"[PageProvisioner] Validation warning: {error}")
            else:
                logger.debug(f"[PageProvisioner] Webpart validation passed")
            
            # Update page with composed webparts
            logger.debug(f"[PageProvisioner] Assigning composed webparts to page...")
            sp_page.webparts = composed_webparts
            logger.info(f"[PageProvisioner] Page '{sp_page.title}' successfully populated. Webparts: {len(sp_page.webparts)}")
            
        except Exception as e:
            logger.error(f"[PageProvisioner] Failed to populate content for page '{sp_page.title}': {str(e)}", exc_info=True)
            # Don't raise, allow page creation to continue with original webparts
