"""Tests for FieldValidator service."""

import pytest
from src.infrastructure.services.field_validator import FieldValidator, FieldValidationError


def _schema(*cols):
    return {"columns": list(cols)}


def _col(name, col_type, required=False, **extra):
    return {"name": name, "type": col_type, "required": required, **extra}


class TestValidateItemData:
    def test_valid_item_passes(self):
        schema = _schema(_col("Title", "text", required=True), _col("Status", "text"))
        warnings = FieldValidator.validate_item_data({"Title": "My Task", "Status": "Active"}, schema)
        assert warnings == []

    def test_missing_required_field_raises_on_create(self):
        schema = _schema(_col("Status", "text", required=True))
        with pytest.raises(FieldValidationError) as exc_info:
            FieldValidator.validate_item_data({}, schema, is_update=False)
        assert "Status" in str(exc_info.value)

    def test_missing_required_field_ok_on_update(self):
        schema = _schema(_col("Status", "text", required=True))
        # Should not raise
        warnings = FieldValidator.validate_item_data({}, schema, is_update=True)
        assert warnings == []

    def test_system_fields_skipped_in_required_check(self):
        schema = _schema(_col("Title", "text", required=True))
        # Title is a system field — should not raise
        warnings = FieldValidator.validate_item_data({}, schema, is_update=False)
        assert warnings == []

    def test_unknown_field_produces_warning(self):
        schema = _schema(_col("Status", "text"))
        warnings = FieldValidator.validate_item_data({"UnknownField": "Value"}, schema)
        assert any("UnknownField" in w for w in warnings)

    def test_unknown_field_does_not_raise(self):
        schema = _schema(_col("Status", "text"))
        warnings = FieldValidator.validate_item_data({"Ghost": "value"}, schema)
        assert isinstance(warnings, list)


class TestTextFieldValidation:
    def test_valid_string_passes(self):
        schema = _schema(_col("Title", "text"))
        warnings = FieldValidator.validate_item_data({"Title": "My Task"}, schema)
        assert warnings == []

    def test_non_string_raises(self):
        schema = _schema(_col("Title", "text"))
        with pytest.raises(FieldValidationError):
            FieldValidator.validate_item_data({"Title": 42}, schema)

    def test_exceeds_max_length_raises(self):
        schema = _schema(_col("Title", "text", maxLength=10))
        with pytest.raises(FieldValidationError, match="maximum length"):
            FieldValidator.validate_item_data({"Title": "A" * 11}, schema)

    def test_within_max_length_passes(self):
        schema = _schema(_col("Title", "text", maxLength=10))
        warnings = FieldValidator.validate_item_data({"Title": "Short"}, schema)
        assert warnings == []


class TestNumberFieldValidation:
    def test_valid_int_passes(self):
        schema = _schema(_col("Score", "number"))
        warnings = FieldValidator.validate_item_data({"Score": 42}, schema)
        assert warnings == []

    def test_valid_float_passes(self):
        schema = _schema(_col("Score", "number"))
        warnings = FieldValidator.validate_item_data({"Score": 3.14}, schema)
        assert warnings == []

    def test_non_numeric_string_raises(self):
        schema = _schema(_col("Score", "number"))
        with pytest.raises(FieldValidationError):
            FieldValidator.validate_item_data({"Score": "abc"}, schema)

    def test_below_min_raises(self):
        schema = _schema(_col("Score", "number", min=0))
        with pytest.raises(FieldValidationError, match="below minimum"):
            FieldValidator.validate_item_data({"Score": -1}, schema)

    def test_above_max_raises(self):
        schema = _schema(_col("Score", "number", max=100))
        with pytest.raises(FieldValidationError, match="exceeds maximum"):
            FieldValidator.validate_item_data({"Score": 101}, schema)


class TestDatetimeFieldValidation:
    def test_valid_iso_string_passes(self):
        schema = _schema(_col("DueDate", "datetime"))
        warnings = FieldValidator.validate_item_data({"DueDate": "2024-03-15T10:30:00Z"}, schema)
        assert warnings == []

    def test_valid_datetime_object_passes(self):
        from datetime import datetime
        schema = _schema(_col("DueDate", "datetime"))
        warnings = FieldValidator.validate_item_data({"DueDate": datetime.now()}, schema)
        assert warnings == []

    def test_invalid_format_raises(self):
        schema = _schema(_col("DueDate", "datetime"))
        with pytest.raises(FieldValidationError, match="Invalid date"):
            FieldValidator.validate_item_data({"DueDate": "not-a-date"}, schema)


class TestBooleanFieldValidation:
    def test_true_passes(self):
        schema = _schema(_col("Active", "boolean"))
        warnings = FieldValidator.validate_item_data({"Active": True}, schema)
        assert warnings == []

    def test_false_passes(self):
        schema = _schema(_col("Active", "boolean"))
        warnings = FieldValidator.validate_item_data({"Active": False}, schema)
        assert warnings == []

    def test_non_boolean_raises(self):
        schema = _schema(_col("Active", "boolean"))
        with pytest.raises(FieldValidationError):
            FieldValidator.validate_item_data({"Active": "yes_indeed"}, schema)

    def test_string_true_passes(self):
        schema = _schema(_col("Active", "boolean"))
        warnings = FieldValidator.validate_item_data({"Active": "true"}, schema)
        assert warnings == []


class TestChoiceFieldValidation:
    def test_valid_choice_passes(self):
        schema = _schema(_col("Status", "choice", choices=["Active", "Done", "Blocked"]))
        warnings = FieldValidator.validate_item_data({"Status": "Active"}, schema)
        assert warnings == []

    def test_invalid_choice_produces_warning(self):
        schema = _schema(_col("Status", "choice", choices=["Active", "Done"]))
        warnings = FieldValidator.validate_item_data({"Status": "Unknown"}, schema)
        assert any("not in predefined choices" in w for w in warnings)

    def test_invalid_choice_does_not_raise(self):
        schema = _schema(_col("Status", "choice", choices=["Active", "Done"]))
        warnings = FieldValidator.validate_item_data({"Status": "Unknown"}, schema)
        assert isinstance(warnings, list)

    def test_non_string_choice_raises(self):
        schema = _schema(_col("Status", "choice", choices=["Active"]))
        with pytest.raises(FieldValidationError):
            FieldValidator.validate_item_data({"Status": 42}, schema)


class TestUserFieldValidation:
    def test_valid_email_string_passes(self):
        schema = _schema(_col("Owner", "user"))
        warnings = FieldValidator.validate_item_data({"Owner": "alice@contoso.com"}, schema)
        assert warnings == []

    def test_invalid_email_format_raises(self):
        # Only strings containing '@' are checked for email format
        schema = _schema(_col("Owner", "user"))
        with pytest.raises(FieldValidationError):
            FieldValidator.validate_item_data({"Owner": "notvalid@"}, schema)

    def test_plain_string_without_at_does_not_raise(self):
        # Strings without '@' are not email-validated
        schema = _schema(_col("Owner", "user"))
        warnings = FieldValidator.validate_item_data({"Owner": "just-a-name"}, schema)
        assert warnings == []

    def test_dict_with_email_passes(self):
        schema = _schema(_col("Owner", "user"))
        warnings = FieldValidator.validate_item_data({"Owner": {"email": "alice@contoso.com"}}, schema)
        assert warnings == []

    def test_dict_without_email_or_id_raises(self):
        schema = _schema(_col("Owner", "user"))
        with pytest.raises(FieldValidationError):
            FieldValidator.validate_item_data({"Owner": {"name": "Alice"}}, schema)


class TestUrlFieldValidation:
    def test_valid_https_url_passes(self):
        schema = _schema(_col("Link", "url"))
        warnings = FieldValidator.validate_item_data({"Link": "https://contoso.com"}, schema)
        assert warnings == []

    def test_valid_http_url_passes(self):
        schema = _schema(_col("Link", "url"))
        warnings = FieldValidator.validate_item_data({"Link": "http://example.com"}, schema)
        assert warnings == []

    def test_invalid_url_raises(self):
        schema = _schema(_col("Link", "url"))
        with pytest.raises(FieldValidationError):
            FieldValidator.validate_item_data({"Link": "not-a-url"}, schema)

    def test_dict_with_url_key_passes(self):
        schema = _schema(_col("Link", "url"))
        warnings = FieldValidator.validate_item_data({"Link": {"Url": "https://example.com"}}, schema)
        assert warnings == []


class TestFieldValidationError:
    def test_is_sharepoint_provisioning_exception(self):
        from src.domain.exceptions import SharePointProvisioningException
        err = FieldValidationError("Status", "Invalid value")
        assert isinstance(err, SharePointProvisioningException)

    def test_stores_field_name(self):
        err = FieldValidationError("Status", "Invalid")
        assert err.field_name == "Status"

    def test_message_includes_field_name(self):
        err = FieldValidationError("Status", "Invalid value")
        assert "Status" in str(err)
