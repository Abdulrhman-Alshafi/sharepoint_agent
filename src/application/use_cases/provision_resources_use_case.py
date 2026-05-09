"""Provision resources use case - refactored with provisioners."""

import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

from src.domain.entities import ProvisioningBlueprint, ActionType
from src.domain.entities.core import SPPermissionMask
from src.domain.repositories import SharePointRepository
from src.domain.services import BlueprintGeneratorService
from src.domain.exceptions import (
    InvalidBlueprintException,
    SharePointProvisioningException,
    HighRiskBlueprintException
)
from src.application.commands import ProvisionResourcesCommand
from src.application.dtos import ProvisionResourcesResponseDTO
from src.application.converters import BlueprintConverter

# Import provisioners directly from their files
# These are imported after the package is already initialized
from src.application.use_cases.provisioners.list_provisioner import ListProvisioner
from src.application.use_cases.provisioners.page_provisioner import PageProvisioner
from src.application.use_cases.provisioners.library_provisioner import LibraryProvisioner
from src.application.use_cases.provisioners.group_provisioner import GroupProvisioner
from src.application.use_cases.provisioners.enterprise_provisioner import EnterpriseProvisioner
from src.application.use_cases.provisioners.site_provisioner import SiteProvisioner

# Import content generation services
from src.domain.services.page_purpose_detector import PagePurposeDetector
from src.infrastructure.services.content_template_manager import ContentTemplateManager
from src.infrastructure.services.page_content_generator import PageContentGenerator


class ProvisionResourcesUseCase:
    """Use case for provisioning SharePoint resources using specialized provisioners."""

    def __init__(
        self,
        blueprint_generator: BlueprintGeneratorService,
        sharepoint_repository: SharePointRepository
    ):
        self.blueprint_generator = blueprint_generator
        self.sharepoint_repository = sharepoint_repository
        
        # Initialize content generation services
        logger.info("[ProvisionResourcesUseCase] Initializing content generation services")
        self.purpose_detector = PagePurposeDetector()
        self.template_manager = ContentTemplateManager()
        self.content_generator = PageContentGenerator()
        
        # Initialize provisioners
        logger.info("[ProvisionResourcesUseCase] Initializing resource provisioners")
        self.list_provisioner = ListProvisioner(sharepoint_repository)
        
        # PageProvisioner with content services
        self.page_provisioner = PageProvisioner(
            sharepoint_repository,
            purpose_detector=self.purpose_detector,
            template_manager=self.template_manager,
            content_generator=self.content_generator,
        )
        logger.debug("[ProvisionResourcesUseCase] PageProvisioner initialized with content services")
        
        self.library_provisioner = LibraryProvisioner(sharepoint_repository)
        self.group_provisioner = GroupProvisioner(sharepoint_repository)
        self.enterprise_provisioner = EnterpriseProvisioner(sharepoint_repository)
        
        # SiteProvisioner with content services
        self.site_provisioner = SiteProvisioner(
            sharepoint_repository,
            page_repository=sharepoint_repository,
            purpose_detector=self.purpose_detector,
            template_manager=self.template_manager,
            content_generator=self.content_generator,
        )
        logger.debug("[ProvisionResourcesUseCase] SiteProvisioner initialized with content services")

    async def execute(self, command: ProvisionResourcesCommand, skip_high_risk_check: bool = False, skip_collision_check: bool = False, user_token: str = "") -> ProvisionResourcesResponseDTO:
        """Execute the provision resources use case.
        
        Args:
            command: Provisioning command with user prompt
            skip_high_risk_check: If True, bypass high-risk validation (user already confirmed)
            skip_collision_check: If True, skip auto-conversion of CREATE to UPDATE on name collision
            user_token: Optional raw bearer token for OBO authentication in permission checks
            
        Returns:
            Response DTO with provisioned resources
        """
        from src.domain.exceptions import PermissionDeniedException
        from src.infrastructure.repositories import GraphAPISharePointRepository

        # 1. Enforce user permissions using OBO repository if token provided
        user_identity = command.user_login_name or command.user_email
        if not user_identity:
            raise PermissionDeniedException(
                "No user identity provided. Authentication is required to provision resources."
            )
        
        # Create user-aware repository for permission checks when user token available
        perm_repository = self.sharepoint_repository
        if user_token:
            perm_repository = GraphAPISharePointRepository(user_token=user_token, site_id=command.target_site_id)
            
        has_perms = await perm_repository.check_user_permission(
            user_identity, SPPermissionMask.MANAGE_WEB
        )
        if not has_perms:
            raise PermissionDeniedException(
                f"User '{user_identity}' does not have sufficient SharePoint permissions (ManageWeb) to provision new resources."
            )

        # IMPORTANT: execute provisioning with the same repository context used
        # for permission checks. This ensures OBO user-token calls are used for
        # tenant-scoped operations like site creation.
        execution_repository = perm_repository if user_token else self.sharepoint_repository

        site_provisioner = SiteProvisioner(
            execution_repository,
            page_repository=execution_repository,
            purpose_detector=self.purpose_detector,
            template_manager=self.template_manager,
            content_generator=self.content_generator,
        )
        list_provisioner = ListProvisioner(execution_repository)
        page_provisioner = PageProvisioner(
            execution_repository,
            purpose_detector=self.purpose_detector,
            template_manager=self.template_manager,
            content_generator=self.content_generator,
        )
        library_provisioner = LibraryProvisioner(execution_repository)
        group_provisioner = GroupProvisioner(execution_repository)
        enterprise_provisioner = EnterpriseProvisioner(execution_repository)
        
        # 2. Validate and generate blueprint
        await self._validate_prompt(command.prompt, skip_high_risk_check=skip_high_risk_check)
        blueprint = await self._generate_blueprint(
            command.prompt,
            target_site_id=command.target_site_id or None,
            fallback_user_email=command.user_email or command.user_login_name or None,
        )

        # If the user explicitly requested default/open access for libraries,
        # suppress AI-generated group permission assignments for libraries.
        self._suppress_library_permission_assignments(blueprint, command.prompt)
        
        # 2. Auto-correct collisions with existing resources (unless explicitly skipped)
        if not skip_collision_check:
            await self._correct_blueprint_collisions(blueprint, target_site_id=command.target_site_id or None)
            
        # Ensure user identity is set as the site owner if not explicitly provided
        for sp_site in blueprint.get_all_sites():
            if not sp_site.owner_email and user_identity:
                sp_site.owner_email = user_identity

        # 3. Provision enterprise features first (dependencies for lists)
        from src.domain.exceptions import DomainException
        warnings: List[str] = []
        created_term_sets: List[Dict[str, Any]] = []
        created_content_types: List[Dict[str, Any]] = []
        try:
            created_term_sets = await enterprise_provisioner.provision_term_sets(blueprint)
        except (DomainException, SharePointProvisioningException) as err:
            warnings.append(f"Term set provisioning skipped: {err}")
            logger.warning("Term set provisioning skipped: %s", err)
        try:
            created_content_types = await enterprise_provisioner.provision_content_types(blueprint)
        except (DomainException, SharePointProvisioningException) as err:
            warnings.append(f"Content type provisioning skipped: {err}")
            logger.warning("Content type provisioning skipped: %s", err)

        # 4. Provision core resources
        created_sites, site_links, site_warnings = await site_provisioner.provision(blueprint)
        warnings.extend(site_warnings)
        
        # Determine target site ID for subsequent resources
        # If a site was just created, use its ID. Otherwise, use the command's target_site_id or None.
        target_site_id = command.target_site_id if command.target_site_id else None
        if created_sites:
            site_result = created_sites[0]
            target_site_id = site_result.get("id") or site_result.get("resource_id")
            
            # If ID is missing OR is just a GUID (doesn't contain commas), we need to resolve the full Graph ID
            needs_resolution = not target_site_id or "," not in target_site_id
            
            if needs_resolution:
                logger.info("Site ID missing or incomplete. Attempting to resolve full Graph ID...")
                resolved = None
                
                # 1. Try resolving by GUID if we have one
                if target_site_id and "," not in target_site_id:
                    try:
                        logger.info("Attempting to resolve full Graph ID using GUID: %s", target_site_id)
                        resolved = await execution_repository.get_site(target_site_id)
                    except Exception as e:
                        logger.warning("Could not resolve new site ID from GUID: %s", e)
                
                # 2. Try resolving by URL
                if (not resolved or not resolved.get("id")) and site_result.get("webUrl"):
                    try:
                        resolved = await execution_repository.get_site_by_url(site_result["webUrl"])
                    except Exception as e:
                        logger.warning("Could not resolve new site ID from URL: %s", e)
                
                # 3. If URL/GUID resolution failed, poll by search (name)
                if not resolved or not resolved.get("id"):
                    try:
                        logger.info("Polling Graph API to find newly created site by name: '%s'...", site_result.get("displayName", ""))
                        import asyncio
                        # Poll for up to 15 seconds
                        for attempt in range(3):
                            await asyncio.sleep(5)
                            found = await execution_repository.search_sites(site_result.get("displayName", ""))
                            # Exact match is preferred, or just take first
                            if found:
                                resolved = found[0]
                                break
                    except Exception as e:
                        logger.warning("Could not resolve new site ID via search polling: %s", e)
                
                if resolved and resolved.get("id"):
                    target_site_id = resolved["id"]
                    logger.info("Successfully resolved full target site ID: %s", target_site_id)
                else:
                    # Clear incomplete target_site_id so we fallback to default site
                    if not target_site_id or "," not in target_site_id:
                        logger.warning("Failed to resolve full Graph ID. Clearing invalid target_site_id.")
                        target_site_id = None

            if target_site_id:
                logger.info("Using newly created site '%s' as target for content.", target_site_id)
            else:
                logger.warning("No new site ID resolved. Subsequent content will be provisioned on the DEFAULT site.")
        
        principal_resolver_repo = None
        if user_token:
            principal_resolver_repo = GraphAPISharePointRepository(
                user_token=user_token,
                site_id=target_site_id or command.target_site_id,
            )

        created_lists, list_links, list_warnings = await list_provisioner.provision(
            blueprint,
            site_id=target_site_id,
            principal_resolver_repo=principal_resolver_repo,
            fallback_user_email=command.user_email or command.user_login_name or None,
        )
        warnings.extend(list_warnings)
        
        created_pages, page_links, page_warnings = await page_provisioner.provision(blueprint, site_id=target_site_id)
        warnings.extend(page_warnings)
        
        created_libs, deleted_libs, lib_title_to_id, lib_links, lib_warnings = await library_provisioner.provision(blueprint, site_id=target_site_id)
        warnings.extend(lib_warnings)

        # 5. Provision groups and permissions
        created_groups, group_warnings = await group_provisioner.provision(
            blueprint,
            lib_title_to_id
        )
        warnings.extend(group_warnings)

        # 6. Provision views and workflows
        created_views = await enterprise_provisioner.provision_views(blueprint)
        created_workflows = await enterprise_provisioner.scaffold_workflows(blueprint)

        # 6a. Upload workflow JSON templates to the first provisioned DocumentLibrary
        #     so users can download and import them into Power Automate directly.
        if created_workflows and created_libs:
            target_lib_id = created_libs[0].get("id", "")
            target_lib_name = created_libs[0].get("displayName", "document library")
            if target_lib_id:
                import json as _json
                for wf in created_workflows:
                    wf_name = wf.get("name", "workflow")
                    file_name = f"{wf_name.replace(' ', '_')}_flow_template.json"
                    try:
                        file_bytes = _json.dumps(wf["template"], indent=2).encode("utf-8")
                        await execution_repository.upload_file(
                            target_lib_id, file_name, file_bytes
                        )
                        wf["artifact_saved_to"] = target_lib_name
                        wf["artifact_file"] = file_name
                        logger.info(
                            "Uploaded workflow template '%s' to library '%s'",
                            file_name, target_lib_name,
                        )
                    except Exception as upload_err:
                        warning_msg = (
                            f"Could not save workflow template '{file_name}' "
                            f"to '{target_lib_name}': {upload_err}"
                        )
                        warnings.append(warning_msg)
                        logger.warning("%s", warning_msg)

        # 7. Aggregate results
        # Only return the primary site link to prevent UI spam, or fallback to the first created resource
        resource_links = []
        if site_links:
            resource_links = [site_links[0]]
        elif page_links:
            resource_links = [page_links[0]]
        elif list_links:
            resource_links = [list_links[0]]
        elif lib_links:
            resource_links = [lib_links[0]]

        return ProvisionResourcesResponseDTO(
            blueprint=BlueprintConverter.to_dto(blueprint),
            created_sites=created_sites,
            created_lists=created_lists,
            created_pages=created_pages,
            resource_links=resource_links,
            created_document_libraries=created_libs,
            deleted_document_libraries=deleted_libs,
            created_groups=created_groups,
            created_term_sets=created_term_sets,
            created_content_types=created_content_types,
            created_views=created_views,
            created_workflows=created_workflows,
            warnings=warnings
        )

    async def _validate_prompt(self, prompt: str, skip_high_risk_check: bool = False) -> None:
        """Validate user prompt before blueprint generation.
        
        Args:
            prompt: User's provisioning request
            skip_high_risk_check: If True, bypass high-risk validation (user already confirmed)
            
        Raises:
            InvalidBlueprintException: If prompt fails validation
            HighRiskBlueprintException: If prompt has high-risk warnings
        """
        validation = await self.blueprint_generator.validate_prompt(prompt)
        
        if not validation.is_valid:
            raise InvalidBlueprintException(
                f"Request rejected: {validation.rejection_reason}"
            )
            
        # Skip high-risk check if user already confirmed
        if not skip_high_risk_check and validation.risk_level == "high" and validation.warnings:
            raise HighRiskBlueprintException(
                warnings=validation.warnings,
                original_prompt=prompt
            )

    async def _generate_blueprint(
        self,
        prompt: str,
        target_site_id: str = None,
        fallback_user_email: str = None,
    ) -> ProvisioningBlueprint:
        """Generate provisioning blueprint from user prompt.
        
        Fetches real tenant users and passes them to the blueprint generator
        so that ``personOrGroup`` columns in seed data use real emails.
        
        Args:
            prompt: User's provisioning request
            target_site_id: Optional site context for fetching site members
            fallback_user_email: Authenticated user email used when tenant directory
                cannot be fetched (prevents fabricated person emails)
            
        Returns:
            Generated blueprint
            
        Raises:
            InvalidBlueprintException: If generated blueprint is invalid
        """
        # Fetch real tenant users for person column seed data
        tenant_users = []
        try:
            from src.infrastructure.services.tenant_users_service import TenantUsersService
            tenant_users = await TenantUsersService.get_tenant_users(
                self.sharepoint_repository,
                site_id=target_site_id,
            )
        except Exception as e:
            logger.debug("Could not fetch tenant users for blueprint (non-fatal): %s", e)

        # If tenant directory lookup fails, still provide at least the current
        # authenticated user so personOrGroup seed-data can use a valid account.
        if not tenant_users and fallback_user_email:
            tenant_users = [{"displayName": fallback_user_email, "email": fallback_user_email}]
            logger.info("_generate_blueprint: using authenticated user fallback for tenant users")
        
        blueprint = await self.blueprint_generator.generate_blueprint(
            prompt, tenant_users=tenant_users
        )
        
        logger.info("_generate_blueprint: sites=%d lists=%d pages=%d libs=%d",
                    len(blueprint.sites), len(blueprint.lists), len(blueprint.pages),
                    len(blueprint.document_libraries))
        
        if not blueprint.is_valid():
            raise InvalidBlueprintException(
                "Generated blueprint is not valid for provisioning"
            )
            
        return blueprint

    def _suppress_library_permission_assignments(self, blueprint: ProvisioningBlueprint, prompt: str) -> None:
        """Remove all library-targeted groups — library permissions are not supported."""
        if not blueprint.groups:
            return

        before = len(blueprint.groups)
        blueprint.groups = [g for g in blueprint.groups if not getattr(g, "target_library_title", "")]
        removed = before - len(blueprint.groups)
        if removed > 0:
            logger.info("Suppressed %d library permission group assignment(s) (library permissions disabled)", removed)

    async def _correct_blueprint_collisions(self, blueprint: ProvisioningBlueprint, target_site_id: str = None) -> None:
        """Auto-correct blueprint to UPDATE existing resources instead of CREATE.
        
        Args:
            blueprint: Blueprint to check and correct
            target_site_id: Site to check collisions against (defaults to main site)
        """
        try:
            existing_lists = await self.sharepoint_repository.get_all_lists(site_id=target_site_id or None)
            existing_titles = {
                lst.get("displayName", "").lower(): str(lst.get("id", ""))
                for lst in existing_lists
                if lst.get("displayName")
            }
            logger.info("collision_check: %d existing lists on site_id=%s", len(existing_lists), target_site_id)

            # Correct list collisions
            for sp_list in blueprint.get_all_lists():
                title_lower = sp_list.title.lower()
                if sp_list.action == ActionType.CREATE and title_lower in existing_titles:
                    logger.info("collision_check: '%s' already exists → flipping to UPDATE", sp_list.title)
                    sp_list.action = ActionType.UPDATE
                    sp_list.list_id = existing_titles[title_lower]

            # Correct library collisions
            for lib in blueprint.get_all_document_libraries():
                title_lower = lib.title.lower()
                if lib.action == ActionType.CREATE and title_lower in existing_titles:
                    logger.info(
                        "collision_check: library '%s' already exists — skipping UPDATE (will be renamed on creation)",
                        lib.title,
                    )
                    
        except Exception:
            # If we can't fetch existing lists, proceed without corrections
            pass
