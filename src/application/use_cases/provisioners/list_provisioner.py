"""List provisioner for SharePoint lists."""

from typing import List, Tuple, Dict, Any, Optional
from src.domain.entities import ProvisioningBlueprint, ActionType
from src.domain.repositories import IListRepository
from src.domain.exceptions import SharePointProvisioningException
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class ListProvisioner:
    """Handles provisioning of SharePoint lists."""

    def __init__(self, repository: IListRepository):
        """Initialize list provisioner.
        
        Args:
            repository: List repository for list operations
        """
        self.repository = repository

    async def provision(
        self,
        blueprint: ProvisioningBlueprint,
        site_id: Optional[str] = None,
        principal_resolver_repo: Optional[Any] = None,
        fallback_user_email: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
        """Provision all lists from the blueprint.
        
        Args:
            blueprint: Provisioning blueprint containing lists
            site_id: Optional SharePoint site ID to target
            principal_resolver_repo: Optional repository used to resolve
                person principals for seed-data fields. When omitted, falls
                back to this provisioner's repository.
            fallback_user_email: Optional authenticated user email used as a
                fallback principal when AI-generated user emails are invalid.
            
        Returns:
            Tuple of (created lists, list of resource links, list of warnings)
        """
        created_lists = []
        resource_links = []
        warnings = []

        logger.info("list_provisioner: %d lists in blueprint (site_id=%s)", len(blueprint.lists), site_id)
        for sp_list in blueprint.lists:
            logger.info("list_provisioner: processing list '%s' action=%s", sp_list.title, sp_list.action)
            try:
                if sp_list.action == ActionType.CREATE:
                    result = await self.repository.create_list(sp_list, site_id=site_id)
                    created_lists.append(result)
                    resource_links.append(result.get("resource_link", ""))
                    
                    # Seed data if provided
                    if sp_list.seed_data:
                        list_id = result.get("id", "")
                        if list_id:
                            columns = []
                            try:
                                columns = await self.repository.get_list_columns(list_id, site_id=site_id)
                                # Build lookup: any reasonable variant → internal name
                                _name_map: Dict[str, str] = {}
                                for col in columns:
                                    internal = col.get("name", "")
                                    display = col.get("displayName", internal)
                                    if not internal:
                                        continue
                                    for variant in (
                                        display.lower(),
                                        internal.lower(),
                                        display.lower().replace(" ", ""),
                                        display.lower().replace(" ", "_"),
                                    ):
                                        _name_map.setdefault(variant, internal)

                                def _remap(item: Dict[str, Any]) -> Dict[str, Any]:
                                    remapped: Dict[str, Any] = {}
                                    for k, v in item.items():
                                        internal_key = _name_map.get(k.lower(), _name_map.get(k.lower().replace(" ", ""), k))
                                        remapped[internal_key] = v
                                    return remapped

                                remapped_seed = [_remap(item) for item in sp_list.seed_data]
                            except Exception as _col_err:
                                logger.warning("Could not fetch columns for seed remapping (%s); using original keys.", _col_err)
                                remapped_seed = sp_list.seed_data

                            # ── Resolve personOrGroup fields to LookupId format ──
                            # SharePoint Graph API expects person fields as:
                            #   {"FieldNameLookupId": <numeric_principal_id>}
                            person_columns = set()
                            for col in columns:
                                if col.get("personOrGroup") is not None:
                                    person_columns.add(col.get("name", ""))
                            
                            if person_columns:
                                _principal_repo = principal_resolver_repo or self.repository
                                resolved_seed = []
                                for item in remapped_seed:
                                    resolved_item = {}
                                    for k, v in item.items():
                                        if k in person_columns and isinstance(v, str) and v:
                                            # Try to resolve email/UPN to SharePoint principal ID
                                            try:
                                                principal_id = await _principal_repo.ensure_user_principal_id(v, site_id=site_id)
                                                resolved_item[f"{k}LookupId"] = principal_id
                                                logger.debug("Resolved person '%s' → principal %d for column '%s'", v, principal_id, k)
                                            except Exception as _resolve_err:
                                                # If seed-data email is invalid, fall back to current authenticated user.
                                                if fallback_user_email and fallback_user_email.lower() != v.lower():
                                                    try:
                                                        fallback_principal_id = await _principal_repo.ensure_user_principal_id(
                                                            fallback_user_email, site_id=site_id
                                                        )
                                                        resolved_item[f"{k}LookupId"] = fallback_principal_id
                                                        logger.info(
                                                            "Resolved fallback user '%s' for unresolved value '%s' in column '%s'",
                                                            fallback_user_email,
                                                            v,
                                                            k,
                                                        )
                                                    except Exception as _fallback_err:
                                                        logger.warning(
                                                            "Could not resolve user '%s' for column '%s': %s; fallback '%s' also failed: %s — skipping field",
                                                            v,
                                                            k,
                                                            _resolve_err,
                                                            fallback_user_email,
                                                            _fallback_err,
                                                        )
                                                else:
                                                    logger.warning("Could not resolve user '%s' for column '%s': %s — skipping field", v, k, _resolve_err)
                                        else:
                                            resolved_item[k] = v
                                    resolved_seed.append(resolved_item)
                                remapped_seed = resolved_seed

                            await self.repository.seed_list_data(list_id, remapped_seed, site_id=site_id)
                            
                elif sp_list.action == ActionType.UPDATE:
                    _update_list_id = sp_list.list_id
                    if not _update_list_id:
                        # AI generated UPDATE but didn't supply list_id — resolve by name
                        _all_site_lists = await self.repository.get_all_lists(site_id=site_id)
                        for _sl in _all_site_lists:
                            if _sl.get("displayName", "").lower() == sp_list.title.lower():
                                _update_list_id = str(_sl.get("id", ""))
                                break
                        if not _update_list_id:
                            logger.warning("list_provisioner: UPDATE skipped for '%s' — list not found on site", sp_list.title)
                            warnings.append(f"Could not find list '{sp_list.title}' to update.")
                    if _update_list_id:
                        result = await self.repository.update_list(_update_list_id, sp_list, site_id=site_id)
                        created_lists.append(result)
                        resource_links.append(result.get("resource_link", ""))
                        
                elif sp_list.action == ActionType.DELETE:
                    if sp_list.list_id:
                        await self.repository.delete_list(sp_list.list_id)
                        
            except SharePointProvisioningException as e:
                # Log error and add to warnings
                warning_msg = f"Failed to provision list '{sp_list.title}': {str(e)}"
                logger.warning("%s", warning_msg)
                warnings.append(warning_msg)
                continue

        logger.info("list_provisioner: done — %d created/updated, %d warnings", len(created_lists), len(warnings))
        return created_lists, resource_links, warnings
