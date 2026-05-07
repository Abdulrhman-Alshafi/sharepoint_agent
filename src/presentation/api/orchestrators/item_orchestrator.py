"""Handler for SharePoint list item operations (CRUD, attachments, views)."""

from typing import List, Dict, Any, Optional
from src.presentation.api.schemas.chat_schemas import ChatResponse
from src.presentation.api.orchestrators.orchestrator_utils import get_logger, error_response
from src.domain.exceptions import PermissionDeniedException, AuthenticationException

logger = get_logger(__name__)

_PENDING_ITEM_OPS: Dict[str, dict] = {}

# SharePoint / Graph API fields that must NEVER be sent in item create/update payloads.
# Sending any of these causes a 400 "Field is not recognized" error.
_SYSTEM_FIELDS = {
    "id", "created", "modified", "author", "editor",
    "content type", "contenttype", "contenttypeid", "_uitype",
    "attachments", "fileref", "filesystemobjecttype", "serverredirectedembedurl",
    "guid", "owshiddenversion", "version", "path", "etag",
    "@odata.etag", "@odata.id", "@odata.type", "@odata.context",
}


_SYSTEM_COLUMN_INTERNALS = {
    "contenttype",
    "contenttypeid",
    "attachments",
    "_uiversionstring",
    "edit",
    "linktitlenomenu",
    "linktitle",
    "docicon",
    "itemchildcount",
    "folderchildcount",
    "_complianceflags",
    "_compliancetag",
    "_compliancetagwrittentime",
    "_compliancetaguserid",
}


def _column_type_label(column: Dict[str, Any]) -> str:
    """Return a user-friendly SharePoint column type label."""
    if column.get("personOrGroup") is not None:
        return "person"
    if column.get("choice") is not None:
        return "choice"
    if column.get("boolean") is not None:
        return "boolean"
    if column.get("dateTime") is not None:
        return "dateTime"
    if column.get("number") is not None:
        return "number"
    if column.get("currency") is not None:
        return "currency"
    if column.get("lookup") is not None:
        return "lookup"
    if column.get("text") is not None:
        return "text"
    if column.get("note") is not None:
        return "note"
    return "text"


def _user_writable_columns(columns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter out hidden/system/read-only columns that users should not fill manually."""
    filtered: List[Dict[str, Any]] = []
    for c in columns:
        internal_name = (c.get("name") or "").strip()
        display_name = (c.get("displayName") or internal_name or "").strip()
        internal_lower = internal_name.lower()
        display_lower = display_name.lower()

        if not display_name:
            continue
        if c.get("readOnly", False) or c.get("hidden", False):
            continue
        if internal_lower in _SYSTEM_COLUMN_INTERNALS:
            continue
        if internal_lower.startswith("_"):
            continue
        if display_lower in {"content type", "content type id", "attachments"}:
            continue

        filtered.append(c)
    return filtered


def _clean_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
    """Remove SharePoint system/read-only fields that cannot be written via the API."""
    return {
        k: v for k, v in fields.items()
        if k.lower().strip() not in _SYSTEM_FIELDS and not k.startswith("@")
    }


def _build_column_name_map(columns: List[Dict[str, Any]]) -> Dict[str, str]:
    """Build lookup variants (display/internal) to canonical internal name."""
    name_map: Dict[str, str] = {}
    for col in columns:
        internal = col.get("name", "")
        display = col.get("displayName", internal)
        if not internal:
            continue
        variants = {
            internal.lower(),
            display.lower(),
            internal.lower().replace(" ", ""),
            display.lower().replace(" ", ""),
            internal.lower().replace("_", ""),
            display.lower().replace("_", ""),
            internal.lower().replace("_x0020_", " "),
            display.lower().replace("_x0020_", " "),
        }
        for variant in variants:
            name_map.setdefault(variant, internal)
    return name_map


def _remap_to_internal_fields(item: Dict[str, Any], name_map: Dict[str, str]) -> Dict[str, Any]:
    """Remap item keys from user/display names to internal SharePoint names."""
    remapped: Dict[str, Any] = {}
    for key, value in item.items():
        key_lower = key.lower()
        internal_key = (
            name_map.get(key_lower)
            or name_map.get(key_lower.replace(" ", ""))
            or name_map.get(key_lower.replace("_", ""))
            or key
        )
        remapped[internal_key] = value
    return remapped


async def _resolve_person_fields(
    item: Dict[str, Any],
    columns: List[Dict[str, Any]],
    repository: Any,
) -> Dict[str, Any]:
    """Convert person field values to <FieldName>LookupId when possible."""
    person_columns = {
        c.get("name", "") for c in columns if c.get("personOrGroup") is not None and c.get("name")
    }
    if not person_columns:
        return item

    resolved: Dict[str, Any] = {}
    for key, value in item.items():
        if key in person_columns and isinstance(value, str) and value:
            try:
                principal_id = await repository.ensure_user_principal_id(value)
                resolved[f"{key}LookupId"] = principal_id
            except Exception as resolve_err:
                logger.warning(
                    "Could not resolve user '%s' for column '%s': %s — skipping field",
                    value,
                    key,
                    resolve_err,
                )
        else:
            resolved[key] = value
    return resolved

async def _generate_sample_items(
    list_name: str,
    columns: List[Dict[str, Any]],
    quantity: int,
    repository: Any = None,
) -> List[Dict[str, Any]]:
    """Use AI to generate realistic sample items for a given list schema."""
    from pydantic import BaseModel
    from src.infrastructure.external_services.ai_client_factory import get_instructor_client

    # Build a column description string
    _skip = {"id", "created", "modified", "author", "editor", "_uitype", "attachments", "contenttypeid"}
    col_descriptions = []
    has_person_columns = False
    for c in _user_writable_columns(columns):
        name = c.get("name") or ""
        display = c.get("displayName") or name
        col_type = _column_type_label(c)
        if col_type == "person":
            has_person_columns = True
        choices = c.get("choice", {}).get("choices", []) if c.get("choice") else []
        if name.lower() in _skip or c.get("readOnly") or c.get("hidden"):
            continue
        entry = f"- {display} (type: {col_type}"
        if choices:
            entry += f", options: {', '.join(choices)}"
        entry += ")"
        col_descriptions.append(entry)

    schema_text = "\n".join(col_descriptions) if col_descriptions else "- Title (type: text)"

    # Fetch real tenant users for person columns
    user_context = ""
    if has_person_columns and repository:
        try:
            from src.infrastructure.services.tenant_users_service import TenantUsersService
            tenant_users = await TenantUsersService.get_tenant_users(repository)
            if tenant_users:
                user_context = TenantUsersService.format_for_prompt(tenant_users)
        except Exception:
            pass  # Non-fatal

    class _SampleItems(BaseModel):
        items: List[Dict[str, Any]]

    prompt = (
        f"Generate exactly {quantity} realistic sample item(s) for a SharePoint list called '{list_name}'.\n\n"
        f"List columns:\n{schema_text}\n\n"
        f"Rules:\n"
        f"- Return only the field names as they appear above (use displayName).\n"
        f"- For choice fields, pick only from the listed options.\n"
        f"- For dateTime fields, use ISO format like '2026-06-30'.\n"
        f"- For personOrGroup fields, use the person's EMAIL ADDRESS as the value.\n"
        f"- Make values realistic and varied (no 'Sample 1', 'Sample 2' placeholders).\n"
        f"- Do NOT include read-only fields like Id, Created, Modified, Author.\n"
    )
    if user_context:
        prompt += (
            f"\n{user_context}\n"
            f"IMPORTANT: For any personOrGroup column, use ONLY emails from the real users above. "
            f"Do NOT invent user names or emails.\n"
        )
    prompt += f"\nReturn a JSON object with key 'items' containing a list of {quantity} item dict(s)."

    try:
        client, model = get_instructor_client()
        kwargs = {
            "messages": [{"role": "user", "content": prompt}],
            "response_model": _SampleItems,
            "temperature": 0.8,
        }
        if model:
            kwargs["model"] = model
        import inspect
        result = client.chat.completions.create(**kwargs)
        if inspect.isawaitable(result):
            result = await result
        # fall through to the clean-fields return below
    except Exception as e:
        logger.error("Sample item generation failed: %s", e)
        return []  # Signal failure — caller will ask user for input instead
    # Strip system fields from every generated item before returning
    return [_clean_fields(item) for item in result.items]


def _item_suggested_actions(list_name: str) -> List[str]:
    """Return smart call-to-action suggestions after adding items to a list."""
    return [
        f"Show me all items in '{list_name}'",
        f"Add another item to '{list_name}'",
        f"Update an item in '{list_name}'",
        f"Delete an item from '{list_name}'",
    ]


async def handle_item_operations(message: str, session_id: str, site_id: str, user_token: str = None, last_created: tuple = None, user_login_name: str = "") -> ChatResponse:
    """Handle list item CRUD operations (add/update/delete/query records) plus attachments and views."""
    from src.presentation.api import get_repository
    from src.infrastructure.external_services.list_item_parser import ListItemParserService
    from src.application.use_cases.list_item_operations_use_case import ListItemOperationsUseCase
    from src.infrastructure.services.field_validator import FieldValidationError

    try:
        # Use OBO (per-user) repository when token is available
        repository = get_repository(user_token=user_token)
        item_operations = ListItemOperationsUseCase(repository)
        # Prefer the site where the list was created (from last_created[2]) over the request site
        _item_site_id = (last_created[2] if (last_created and len(last_created) > 2 and last_created[2]) else None) or site_id

        # ── Resolve pronouns using last_created context ───────────────────────
        # When the user says "add an item to it", "show items in it", OR uses a
        # field-filter pattern like "delete the one with title X" without naming
        # the list, inject [List: name] so the AI parser knows which list to use.
        _parse_message = message
        _list_context: Optional[str] = None
        if last_created and last_created[1] == "list" and last_created[0]:
            _last_list_name = last_created[0]
            _msg_lower_check = message.lower()

            # ── Inject [List: X] into message when needed ─────────────────────
            _PRONOUN_REFS = (" it", " this", " that", " the list", " this list", " that list")
            _has_pronoun = any(_msg_lower_check.endswith(ref) or f"{ref} " in _msg_lower_check for ref in _PRONOUN_REFS)
            _FIELD_FILTER_PATS = (" is ", " whose ", "where ", "with name", "with title",
                                  "the one ", "the entry ", "the record ", "the row ",
                                  "named ", "called ", "titled ", " with ")
            _has_filter = any(pat in _msg_lower_check for pat in _FIELD_FILTER_PATS)
            _list_name_in_msg = _last_list_name.lower() in _msg_lower_check
            if _has_pronoun or (_has_filter and not _list_name_in_msg):
                _parse_message = f"{message} [List: {_last_list_name}]"

            # ── Fetch schema to build rich list context for the AI parser ──────
            # Find the list, get its columns, then pass them as structured context
            # so the AI can map "with the Tecate Original title" → Title='Tecate Original'
            try:
                _ctx_all_lists = await repository.get_all_lists(_item_site_id)
                _ctx_list = None
                _lname_lower = _last_list_name.lower()
                for _lst in _ctx_all_lists:
                    _dname = _lst.get("displayName", "").lower()
                    if _lname_lower in _dname or _dname in _lname_lower:
                        _ctx_list = _lst
                        break
                if _ctx_list:
                    _ctx_list_id = _ctx_list.get("id")
                    _ctx_columns = await repository.get_list_columns(_ctx_list_id, site_id=_item_site_id)
                    # Filter out hidden/system columns
                    _SYSTEM_COLS = frozenset({"ContentType", "Attachments", "_UIVersionString",
                                             "Edit", "LinkTitleNoMenu", "LinkTitle", "DocIcon",
                                             "ItemChildCount", "FolderChildCount", "_ComplianceFlags",
                                             "_ComplianceTag", "_ComplianceTagWrittenTime",
                                             "_ComplianceTagUserId"})
                    _col_display = [
                        f"{c.get('displayName', c.get('name', ''))} (internal: {c.get('name', '')})"
                        for c in _ctx_columns
                        if not c.get("hidden", False) and c.get("name", "") not in _SYSTEM_COLS
                    ]
                    _list_context = (
                        f"[Active list: '{_last_list_name}']\n"
                        f"[Columns: {', '.join(_col_display[:25])}]\n"
                        f"Use '{_last_list_name}' as the list_name. "
                        f"Map the user's natural-language field references to the actual column names above."
                    )
            except Exception as _ctx_err:
                logger.debug("Schema fetch for list context failed (non-critical): %s", _ctx_err)

        # ── Confirmation check: resume a pending operation ────────────────────
        _CONFIRM_PHRASES = {"yes", "confirm", "proceed", "do it", "go ahead"}
        msg_lower = message.lower().strip()
        is_confirmation = (
            msg_lower in _CONFIRM_PHRASES
            or msg_lower.startswith("yes ")
            or msg_lower.startswith("yes,")
            or msg_lower == "yes delete the item"
            or msg_lower == "yes delete this item"
            or "yes, delete" in msg_lower
        )
        if is_confirmation and session_id and session_id in _PENDING_ITEM_OPS:
            pending = _PENDING_ITEM_OPS.pop(session_id)
            op_type = pending["operation"]
            list_id = pending["list_id"]
            list_name = pending["list_name"]
            items = pending["items"]
            pending_site_id = pending.get("site_id", site_id)

            if op_type == "delete":
                deleted_count = 0
                errors = []
                for item in items:
                    try:
                        await item_operations.delete_item(list_id, str(item.get("id")), pending_site_id, user_login=user_login_name)
                        deleted_count += 1
                    except Exception as e:
                        errors.append(f"#{item.get('id')}: {e}")
                _noun = "item" if deleted_count == 1 else "items"
                reply = f"✅ Deleted **{deleted_count}** {_noun} from **{list_name}**."
                if errors:
                    _enoun = "item" if len(errors) == 1 else "items"
                    reply += f"\n\n⚠️ {len(errors)} {_enoun} failed: {'; '.join(errors)}"
                return ChatResponse(
                    intent="item_operation",
                    reply=reply,
                    data_summary={"operation": "delete", "count": deleted_count, "list_name": list_name, "site_id": _item_site_id},
                    session_id=session_id,
                    suggested_actions=_item_suggested_actions(list_name),
                )

            if op_type == "update":
                updated_count = 0
                errors = []
                field_values = pending.get("field_values", {})
                clean_values = _clean_fields(field_values)
                for item in items:
                    try:
                        await item_operations.update_item_validated(list_id, str(item.get("id")), clean_values, pending_site_id, user_login=user_login_name)
                        updated_count += 1
                    except Exception as e:
                        errors.append(f"#{item.get('id')}: {e}")
                _noun = "item" if updated_count == 1 else "items"
                reply = f"✅ Updated **{updated_count}** {_noun} in **{list_name}**."
                if errors:
                    _enoun = "item" if len(errors) == 1 else "items"
                    reply += f"\n\n⚠️ {len(errors)} {_enoun} failed: {'; '.join(errors)}"
                return ChatResponse(
                    intent="item_operation",
                    reply=reply,
                    data_summary={"operation": "update", "count": updated_count, "list_name": list_name, "site_id": _item_site_id},
                    session_id=session_id,
                    suggested_actions=_item_suggested_actions(list_name),
                )
        
        # Parse the operation using AI — pass list schema context when available
        operation = await ListItemParserService.parse_item_operation(_parse_message, list_context=_list_context)
        
        if not operation:
            return ChatResponse(
                intent="chat",
                reply="I couldn't understand the item operation. Please try rephrasing.\n\n"
                       "Examples:\n"
                       "- 'Add a salary record for John with 5000 for March 2024'\n"
                       "- 'Update Abdulrahman Alshafi salary to 5500 in March'\n"
                       "- 'Show all salaries above 4000, sorted by salary descending'\n"
                       "- 'Show the top 10 tasks ordered by due date'\n"
                       "- 'Create a view showing active tasks with title and due date'"
            )
        
        # Find the list by name
        all_lists = await repository.get_all_lists(_item_site_id)
        target_list = None
        for lst in all_lists:
            list_name = lst.get("displayName", "").lower()
            if operation.list_name.lower() in list_name or list_name in operation.list_name.lower():
                target_list = lst
                break

        # Fallback: if not found by parsed name but we have a last_created list, try that name
        if not target_list and last_created and last_created[1] == "list" and last_created[0]:
            _fallback_name = last_created[0].lower()
            for lst in all_lists:
                list_name = lst.get("displayName", "").lower()
                if _fallback_name in list_name or list_name in _fallback_name:
                    target_list = lst
                    break

        if not target_list:
            return ChatResponse(
                intent="chat",
                reply=f"I couldn't find a list matching '{operation.list_name}'. Please check the list name and try again.\n\n"
                       f"Available lists: {', '.join([l.get('displayName', 'Unknown') for l in all_lists[:10]])}"
            )
        
        list_id = target_list.get("id")
        list_name = target_list.get("displayName")
        
        # ── CREATE OPERATION ────────────────────────────────
        if operation.operation == "create":
            # Fetch columns once — needed for both empty-data prompts and auto-generate
            try:
                columns = await repository.get_list_columns(list_id, _item_site_id)
            except Exception:
                columns = []
            name_map = _build_column_name_map(columns)

            # ── Auto-generate: AI makes up the data ────────
            if operation.auto_generate or (not operation.field_values and operation.quantity > 1):
                qty = max(1, min(operation.quantity or 1, 20))  # cap at 20
                generated = await _generate_sample_items(list_name, columns, qty, repository=repository)

                # If generation failed (empty list), fall through to ask user
                if not generated:
                    generated = []  # will be caught below

                created_count = 0
                errors = []
                for item_data in generated:
                    try:
                        clean = _clean_fields(item_data)
                        clean = _remap_to_internal_fields(clean, name_map)
                        clean = await _resolve_person_fields(clean, columns, repository)
                        await item_operations.create_item_validated(list_id, clean, _item_site_id, user_login=user_login_name)
                        created_count += 1
                    except Exception as e:
                        errors.append(str(e))

                if created_count == 0:
                    # AI failed or generated nothing — ask user for data with column format
                    user_cols = [
                        (c.get("displayName") or c.get("name", ""), _column_type_label(c))
                        for c in _user_writable_columns(columns)
                    ]
                    _col_format = ", ".join(f"**{name}** ({ctype})" for name, ctype in user_cols if name) or "**Title** (text)"
                    _example = ", ".join(
                        f"{name}: <value>" for name, _ in (user_cols[:4] if user_cols else [("Title", "text")])
                    )
                    _suggestions = [
                        f"Add 1 sample item to list {list_name}",
                        f"Add 3 sample items to list {list_name}",
                        f"Add 5 sample items to list {list_name}",
                        "I'll provide the data myself",
                    ]
                    return ChatResponse(
                        intent="chat",
                        reply=(
                            f"I wasn't able to auto-generate data for **{list_name}** right now.\n\n"
                            f"What would you like to add? This list has these columns:\n{_col_format}\n\n"
                            f"You can tell me the values like:\n> *{_example}*"
                        ),
                        quick_suggestions=_suggestions,
                        field_options=_suggestions,
                        session_id=session_id,
                    )

                _noun = "item" if created_count == 1 else "items"
                reply = f"✅ Sample data has been added to the **{list_name}** list!\n\nI've added **{created_count}** {_noun} with example data for your columns."
                if errors:
                    _enoun = "item" if len(errors) == 1 else "items"
                    reply += f"\n\n⚠️ {len(errors)} {_enoun} failed: {'; '.join(errors)}"

                return ChatResponse(
                    intent="item_operation",
                    reply=reply,
                    session_id=session_id,
                    suggested_actions=_item_suggested_actions(list_name),
                    data_summary={"operation": "create", "count": created_count, "list_name": list_name, "site_id": _item_site_id},
                )

            # ── No data supplied: ask the user ─────────────
            if not operation.field_values:
                user_cols = [
                    (c.get("displayName") or c.get("name", ""), _column_type_label(c))
                    for c in _user_writable_columns(columns)
                ]
                _col_format = ", ".join(f"**{name}** ({ctype})" for name, ctype in user_cols if name) or "**Title** (text)"
                _example = ", ".join(
                    f"{name}: <value>" for name, _ in (user_cols[:4] if user_cols else [("Title", "text")])
                )
                _suggestions = [
                    f"Add 1 sample item to list {list_name}",
                    f"Add 3 sample items to list {list_name}",
                    f"Add 5 sample items to list {list_name}",
                    "I'll provide the data myself",
                ]
                return ChatResponse(
                    intent="chat",
                    reply=(
                        f"Sure! What data would you like to add to **{list_name}**?\n\n"
                        f"This list has these columns:\n{_col_format}\n\n"
                        f"You can tell me the values like:\n> *{_example}*\n\n"
                        f"Or I can generate sample data for you."
                    ),
                    quick_suggestions=_suggestions,
                    field_options=_suggestions,
                    session_id=session_id,
                )

            # ── User provided field values ──────────────────
            try:
                clean_values = _clean_fields(operation.field_values)
                clean_values = _remap_to_internal_fields(clean_values, name_map)
                clean_values = await _resolve_person_fields(clean_values, columns, repository)
                # Use validated create for better error messages
                result = await item_operations.create_item_validated(list_id, clean_values, _item_site_id, user_login=user_login_name)

                reply = f"✅ Successfully added new item to **{list_name}**!\n\n**Values:**\n"
                reply += "\n".join([f"- **{k}**: {v}" for k, v in clean_values.items()])

                # Add validation warnings if any
                if result.get('validation_warnings'):
                    reply += "\n\n⚠️ **Warnings:**\n" + "\n".join([f"- {w}" for w in result['validation_warnings']])

                return ChatResponse(
                    intent="item_operation",
                    reply=reply,
                    data_summary={
                        **result,
                        "operation": "create",
                        "list_name": list_name,
                        "fields": clean_values,
                        "count": 1,
                    },
                    session_id=session_id,
                    suggested_actions=_item_suggested_actions(list_name),
                )
            except FieldValidationError as e:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ **Validation Error**: {str(e)}\n\nPlease correct the field value and try again."
                )
        
        # ── UPDATE OPERATION ────────────────────────────────
        elif operation.operation == "update":
            if not operation.filter_criteria and not operation.item_id:
                return ChatResponse(
                    intent="chat",
                    reply="To update item(s), please specify which one(s) — e.g., 'update the Done items to In Progress', 'update item id 5 Title to X'."
                )

            # If a direct ID was provided, skip querying
            if operation.item_id:
                items_to_update_ids = [str(operation.item_id)]
                items_display = [f"item #{operation.item_id}"]
            else:
                filter_query = ListItemParserService.build_odata_filter(operation.filter_criteria)
                raw_items = await item_operations.query_items(list_id, filter_query, _item_site_id, user_login=user_login_name)

                if not raw_items:
                    return ChatResponse(
                        intent="chat",
                        reply=f"No items found in **{list_name}** matching: {operation.filter_criteria}"
                    )

                # Single-item guard: if not bulk mode and more than 1 match, ask for confirmation
                if not operation.bulk and len(raw_items) > 1:
                    if session_id:
                        _PENDING_ITEM_OPS[session_id] = {
                            "operation": "update",
                            "list_id": list_id,
                            "list_name": list_name,
                            "items": raw_items,
                            "field_values": operation.field_values,
                            "site_id": _item_site_id,
                        }
                    return ChatResponse(
                        intent="chat",
                        reply=(
                            f"Found **{len(raw_items)}** matching items in **{list_name}**.\n\n"
                            f"Did you want to update **all {len(raw_items)} items**? "
                            f"If yes, say something like *\"yes update all of them\"* or repeat your request with the word **all**."
                        ),
                        field_options=[
                            f"Yes, update all {len(raw_items)} matching items",
                            "No, I'll be more specific",
                        ],
                        session_id=session_id,
                    )

                items_to_update_ids = [str(item.get("id")) for item in raw_items]
                items_display = [item.get("fields", {}).get("Title", f"item #{item.get('id')}") for item in raw_items]

            # Perform updates
            updated_count = 0
            errors = []
            clean_update_values = _clean_fields(operation.field_values)
            for iid in items_to_update_ids:
                try:
                    await item_operations.update_item_validated(list_id, iid, clean_update_values, _item_site_id, user_login=user_login_name)
                    updated_count += 1
                except FieldValidationError as e:
                    errors.append(f"#{iid}: {e}")
                except Exception as e:
                    errors.append(f"#{iid}: {e}")

            if updated_count == 0:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Failed to update items in **{list_name}**: {'; '.join(errors)}",
                    session_id=session_id,
                )

            changes = ", ".join(f"**{k}** → {v}" for k, v in clean_update_values.items())
            _noun = "item" if updated_count == 1 else "items"
            reply = f"✅ Updated **{updated_count}** {_noun} in **{list_name}**!\n\n**Change:** {changes}\n"
            if len(items_display) <= 10:
                reply += "\n**Items updated:**\n" + "\n".join(f"- {t}" for t in items_display)
            if errors:
                _enoun = "item" if len(errors) == 1 else "items"
                reply += f"\n\n⚠️ {len(errors)} {_enoun} failed: {'; '.join(errors)}"

            return ChatResponse(
                intent="item_operation",
                reply=reply,
                data_summary={"operation": "update", "count": updated_count, "list_name": list_name, "site_id": _item_site_id},
                session_id=session_id,
                suggested_actions=_item_suggested_actions(list_name),
            )
        
        # ── DELETE OPERATION ────────────────────────────────
        elif operation.operation == "delete":
            # Allow delete by direct ID with no filter
            if not operation.filter_criteria and not operation.item_id:
                return ChatResponse(
                    intent="chat",
                    reply="To delete item(s), please specify which — e.g. 'delete all done items', 'delete item id 5', 'delete the record for John'."
                )

            # Direct ID delete
            if operation.item_id:
                try:
                    await item_operations.delete_item(list_id, str(operation.item_id), _item_site_id, user_login=user_login_name)
                    return ChatResponse(
                        intent="item_operation",
                        reply=f"✅ Deleted item **#{operation.item_id}** from **{list_name}**.",
                        data_summary={"operation": "delete", "count": 1, "list_name": list_name, "site_id": _item_site_id},
                        session_id=session_id,
                        suggested_actions=_item_suggested_actions(list_name),
                    )
                except Exception as e:
                    return ChatResponse(
                        intent="chat",
                        reply=f"❌ Could not delete item #{operation.item_id}: {e}",
                        session_id=session_id,
                    )

            # Filter-based delete
            filter_query = ListItemParserService.build_odata_filter(operation.filter_criteria)
            items = await item_operations.query_items(list_id, filter_query, _item_site_id, user_login=user_login_name)

            if not items:
                return ChatResponse(
                    intent="chat",
                    reply=f"No items found in **{list_name}** matching: {operation.filter_criteria}"
                )

            # Single-item guard: if not bulk and more than 1 result, confirm first
            if not operation.bulk and len(items) > 1:
                # Store pending so "yes" can resume without re-parsing
                if session_id:
                    _PENDING_ITEM_OPS[session_id] = {
                        "operation": "delete",
                        "list_id": list_id,
                        "list_name": list_name,
                        "items": items,
                        "site_id": _item_site_id,
                    }
                return ChatResponse(
                    intent="chat",
                    reply=(
                        f"Found **{len(items)}** matching items in **{list_name}**.\n\n"
                        f"Do you want to delete **all {len(items)} items**? "
                        f"This cannot be undone."
                    ),
                    field_options=[
                        f"Yes, delete all {len(items)} matching items",
                        "No, I'll be more specific",
                    ],
                    session_id=session_id,
                )

            # Perform bulk or single delete
            deleted_count = 0
            errors = []
            for item in items:
                try:
                    await item_operations.delete_item(list_id, str(item.get("id")), _item_site_id, user_login=user_login_name)
                    deleted_count += 1
                except Exception as e:
                    errors.append(f"#{item.get('id')}: {e}")

            if deleted_count == 0:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Failed to delete items from **{list_name}**: {'; '.join(errors)}",
                    session_id=session_id,
                )

            _noun = "item" if deleted_count == 1 else "items"
            reply = f"✅ Deleted **{deleted_count}** {_noun} from **{list_name}**."
            if errors:
                _enoun = "item" if len(errors) == 1 else "items"
                reply += f"\n\n⚠️ {len(errors)} {_enoun} failed: {'; '.join(errors)}"

            return ChatResponse(
                intent="item_operation",
                reply=reply,
                data_summary={"operation": "delete", "count": deleted_count, "list_name": list_name, "site_id": _item_site_id},
                session_id=session_id,
                suggested_actions=_item_suggested_actions(list_name),
            )
        
        # ── QUERY OPERATION ─────────────────────────────────
        elif operation.operation == "query":
            # Check if advanced query features are requested
            if operation.select_fields or operation.order_by or operation.limit:
                # Use advanced query
                filter_query = None
                if operation.filter_criteria:
                    filter_query = ListItemParserService.build_odata_filter(operation.filter_criteria)
                
                result = await item_operations.query_items_advanced(
                    list_id=list_id,
                    filter_query=filter_query,
                    select_fields=operation.select_fields,
                    order_by=operation.order_by,
                    top=operation.limit,
                    site_id=_item_site_id
                )
                
                items = result.get('items', [])
                has_next = result.get('next_link') is not None
            else:
                # Use simple query
                filter_query = None
                if operation.filter_criteria:
                    filter_query = ListItemParserService.build_odata_filter(operation.filter_criteria)
                
                items = await item_operations.query_items(list_id, filter_query, _item_site_id, user_login=user_login_name)
                has_next = False
            
            if not items:
                return ChatResponse(
                    intent="chat",
                    reply=f"No items found in **{list_name}**" + (f" matching: {operation.filter_criteria}" if operation.filter_criteria else "")
                )
            
            # ── Resolve personOrGroup LookupId fields → display names ─────
            try:
                from src.infrastructure.services.person_field_resolver import resolve_person_fields
                _q_columns = await repository.get_list_columns(list_id, site_id=_item_site_id)
                _q_fields_list = [it.get("fields", {}) for it in items]
                graph_client = getattr(repository, "graph_client", None)
                if graph_client:
                    await resolve_person_fields(
                        _q_fields_list, _q_columns, graph_client,
                        _item_site_id or getattr(graph_client, "site_id", ""),
                    )
            except Exception as _pf_err:
                logger.debug("Person field resolution in query skipped: %s", _pf_err)
            
            # Format results
            _noun = "item" if len(items) == 1 else "items"
            reply = f"Found **{len(items)}** {_noun} in **{list_name}**"
            if operation.order_by:
                reply += f" (sorted by {operation.order_by})"
            if operation.limit:
                reply += f" (showing top {operation.limit})"
            reply += ":\n\n"
            
            for i, item in enumerate(items[:20], 1):
                fields = item.get("fields", {})
                
                # If select_fields specified, show only those fields
                if operation.select_fields:
                    field_summary = [f"{key}: {fields.get(key, 'N/A')}" for key in operation.select_fields if key in fields]
                else:
                    # Show key fields
                    field_summary = []
                    for key, value in list(fields.items())[:5]:
                        if not key.startswith("@") and key not in ["id", "ContentType", "Modified", "Created"]:
                            field_summary.append(f"{key}: {value}")
                
                reply += f"{i}. " + " | ".join(field_summary) + "\n"
            
            if len(items) > 20:
                reply += f"\n... and {len(items) - 20} more items"
            
            if has_next:
                reply += "\n\n💡 More results available. Use pagination to see all items."
            
            return ChatResponse(
                intent="chat",
                reply=reply,
                data_summary={"count": len(items), "items": items[:20], "list_name": list_name, "site_id": _item_site_id}
            )
        
        # ── ATTACHMENT OPERATION ────────────────────────────
        elif operation.operation == "attach":
            if not operation.attachment_operation:
                return ChatResponse(
                    intent="chat",
                    reply="Please specify what you want to do with attachments: add, list, or delete."
                )
            
            # Find the item
            if operation.filter_criteria:
                filter_query = ListItemParserService.build_odata_filter(operation.filter_criteria)
                items = await item_operations.query_items(list_id, filter_query, site_id, user_login=user_login_name)
                
                if not items:
                    return ChatResponse(
                        intent="chat",
                        reply=f"No items found in **{list_name}** matching: {operation.filter_criteria}"
                    )
                if len(items) > 1:
                    return ChatResponse(
                        intent="chat",
                        reply=f"Found {len(items)} matching items. Please be more specific."
                    )
                
                item_id = items[0].get("id")
            else:
                return ChatResponse(
                    intent="chat",
                    reply="Please specify which item to work with (e.g., 'item 5' or 'for John')."
                )
            
            if operation.attachment_operation == "list":
                attachments = await item_operations.get_attachments(list_id, item_id, site_id)
                
                if not attachments:
                    return ChatResponse(
                        intent="chat",
                        reply=f"No attachments found for this item in **{list_name}**."
                    )
                
                reply = f"**Attachments** for item in **{list_name}**:\n\n"
                for i, att in enumerate(attachments, 1):
                    reply += f"{i}. {att.get('fileName', 'Unknown')} ({att.get('size', 'Unknown size')})\n"
                
                return ChatResponse(
                    intent="chat",
                    reply=reply,
                    data_summary={"attachments": attachments}
                )
            
            elif operation.attachment_operation == "add":
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ File upload via chat is not yet supported. Please use the SharePoint interface to add attachments, or provide the file through the API."
                )
            
            elif operation.attachment_operation == "delete":
                if not operation.file_name:
                    return ChatResponse(
                        intent="chat",
                        reply="Please specify which attachment to delete by file name."
                    )
                
                # Get attachments to find the ID
                attachments = await item_operations.get_attachments(list_id, item_id, site_id)
                target_attachment = next((a for a in attachments if a.get('fileName') == operation.file_name), None)
                
                if not target_attachment:
                    return ChatResponse(
                        intent="chat",
                        reply=f"Attachment '{operation.file_name}' not found for this item."
                    )
                
                await item_operations.delete_attachment(list_id, item_id, target_attachment['id'], site_id)
                
                return ChatResponse(
                    intent="chat",
                    reply=f"✅ Successfully deleted attachment '{operation.file_name}' from item in **{list_name}**."
                )
        
        # ── VIEW OPERATION ──────────────────────────────────
        elif operation.operation == "view":
            if not operation.view_name:
                return ChatResponse(
                    intent="chat",
                    reply="Please specify a name for the view."
                )
            
            if not operation.view_fields:
                return ChatResponse(
                    intent="chat",
                    reply="Please specify which fields to include in the view."
                )
            
            # Create the view
            view_query = None
            if operation.filter_criteria:
                # Convert to CAML query (simplified - would need proper CAML builder)
                view_query = ListItemParserService.build_odata_filter(operation.filter_criteria)
            
            await item_operations.create_view(
                list_id=list_id,
                view_name=operation.view_name,
                view_fields=operation.view_fields,
                view_query=view_query,
                site_id=_item_site_id
            )
            
            reply = f"✅ Successfully created view **'{operation.view_name}'** for **{list_name}**!\n\n"
            reply += f"**Fields:** {', '.join(operation.view_fields)}"
            
            if operation.filter_criteria:
                reply += f"\n**Filter:** {operation.filter_criteria}"
            
            return ChatResponse(
                intent="chat",
                reply=reply
            )
        
        else:
            return ChatResponse(
                intent="chat",
                reply=f"Unknown operation: {operation.operation}"
            )
    
    except PermissionDeniedException:
        from src.presentation.api.orchestrators.orchestrator_utils import permission_denied_response
        return permission_denied_response(session_id=session_id)
    except AuthenticationException:
        from src.presentation.api.orchestrators.orchestrator_utils import auth_expired_response
        return auth_expired_response(session_id=session_id)
    except Exception as e:
        from src.domain.exceptions import DomainException
        from src.presentation.api.orchestrators.orchestrator_utils import domain_error_response
        if isinstance(e, DomainException):
            return domain_error_response(e, intent="chat", session_id=session_id)
        return error_response(logger, "chat", "Sorry, I couldn't complete that operation: {error}", e,
                              error_category="internal",
                              recovery_hint="Please try again. If this persists, contact your administrator.")
