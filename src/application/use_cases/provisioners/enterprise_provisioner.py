"""Enterprise provisioner for content types, term sets, and views."""

from typing import List, Tuple, Dict, Any
from src.domain.entities import ProvisioningBlueprint, ActionType
from src.domain.repositories import IEnterpriseRepository
from src.domain.exceptions import SharePointProvisioningException
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class EnterpriseProvisioner:
    """Handles provisioning of enterprise SharePoint features."""

    def __init__(self, repository: IEnterpriseRepository):
        """Initialize enterprise provisioner.
        
        Args:
            repository: Enterprise repository for content type, term set, and view operations
        """
        self.repository = repository

    async def provision_term_sets(self, blueprint: ProvisioningBlueprint) -> List[Dict[str, Any]]:
        """Provision term sets from the blueprint.
        
        Args:
            blueprint: Provisioning blueprint containing term sets
            
        Returns:
            List of created term sets
        """
        created_term_sets = []
        
        for term_set in blueprint.term_sets:
            try:
                if term_set.action == ActionType.CREATE:
                    result = await self.repository.create_term_set(term_set)
                    created_term_sets.append(result or {})
            except SharePointProvisioningException as e:
                logger.warning("Failed to create term set '%s': %s", term_set.name, str(e))
                continue
                
        return created_term_sets

    async def provision_content_types(self, blueprint: ProvisioningBlueprint) -> List[Dict[str, Any]]:
        """Provision content types from the blueprint.
        
        Args:
            blueprint: Provisioning blueprint containing content types
            
        Returns:
            List of created content types
        """
        created_content_types = []
        
        for content_type in blueprint.content_types:
            try:
                if content_type.action == ActionType.CREATE:
                    result = await self.repository.create_content_type(content_type)
                    created_content_types.append(result or {})
            except SharePointProvisioningException as e:
                logger.warning("Failed to create content type '%s': %s", content_type.name, str(e))
                continue
                
        return created_content_types

    async def provision_views(self, blueprint: ProvisioningBlueprint) -> List[Dict[str, Any]]:
        """Provision views from the blueprint.
        
        Args:
            blueprint: Provisioning blueprint containing views
            
        Returns:
            List of created views
        """
        created_views = []
        
        for view in blueprint.views:
            try:
                if view.action == ActionType.CREATE:
                    result = await self.repository.create_view(view)
                    created_views.append(result or {})
            except SharePointProvisioningException as e:
                logger.warning("Failed to create view '%s': %s", view.title, str(e))
                continue
                
        return created_views

    async def scaffold_workflows(self, blueprint: ProvisioningBlueprint) -> List[Dict[str, Any]]:
        """Generate Power Automate workflow template definitions from the blueprint.

        Produces a structured workflow definition for each workflow in the blueprint.
        These definitions follow the Power Automate flow JSON schema basics and can be
        imported into Power Automate or stored for later use. Full automated deployment
        via Microsoft Graph API requires the Power Platform connector scope which may
        not be available in all tenants; this method returns the generated definitions
        and signals whether each was provisioned automatically.

        Args:
            blueprint: Provisioning blueprint containing workflow scaffolds

        Returns:
            List of workflow result dicts containing name, template, and status.
        """
        results = []

        for wf in blueprint.workflows:
            wf_name = getattr(wf, "name", "Unnamed Workflow")
            trigger_type = getattr(wf, "trigger", "manual")
            list_binding = getattr(wf, "list_id", None) or getattr(wf, "list_name", None)
            description = getattr(wf, "description", f"Automated workflow: {wf_name}")

            # Build a minimal Power Automate flow definition template
            flow_template: Dict[str, Any] = {
                "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
                "contentVersion": "1.0.0.0",
                "metadata": {
                    "operationMetadataId": wf_name,
                },
                "definition": {
                    "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
                    "actions": {},
                    "contentVersion": "1.0.0.0",
                    "outputs": {},
                    "parameters": {
                        "$connections": {"defaultValue": {}, "type": "Object"}
                    },
                    "triggers": {
                        "When_an_item_is_created_or_modified" if trigger_type in ("item_created", "item_modified", "manual") else "Recurrence": {
                            "type": "ApiConnectionWebhook" if trigger_type != "scheduled" else "Recurrence",
                            "inputs": {
                                "body": {"NotificationUrl": "@{listCallbackUrl()}"},
                                "host": {
                                    "connection": {"name": "@parameters('$connections')['sharepointonline']['connectionId']"}
                                },
                                "path": f"/datasets/@{{encodeURIComponent(encodeURIComponent('default'))}}/tables/@{{encodeURIComponent(encodeURIComponent('{list_binding or 'unknown'}'))}}/onchangeditems",
                            } if trigger_type != "scheduled" else {
                                "interval": {"count": 1, "unit": "Day"}
                            },
                        }
                    },
                },
                "parameters": {
                    "$connections": {
                        "value": {
                            "sharepointonline": {
                                "connectionId": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
                                "connectionName": "sharepointonline",
                                "id": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
                            }
                        }
                    }
                },
            }

            results.append({
                "name": wf_name,
                "description": description,
                "trigger": trigger_type,
                "list_binding": list_binding,
                "template": flow_template,
                "status": "definition_generated",
                "note": (
                    "Flow definition generated. Automated deployment requires Power Platform connector scope. "
                    "Import the 'template' field into Power Automate manually if needed."
                ),
            })

            logger.info("Scaffolded workflow definition for '%s' (trigger=%s)", wf_name, trigger_type)

        return results
