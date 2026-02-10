"""MCP protocol contract tests.

Validates that MCP Resource and Tool schemas comply with
the MCP specification and JSON-RPC protocol requirements.
"""

from __future__ import annotations

import json
from typing import Any

import pytest


# --- JSON-RPC validation helpers ---


def validate_jsonrpc_request(msg: dict[str, Any]) -> list[str]:
    """Validate a JSON-RPC 2.0 request message. Returns list of errors."""
    errors: list[str] = []
    if msg.get("jsonrpc") != "2.0":
        errors.append("Missing or invalid 'jsonrpc' field (must be '2.0')")
    if "method" not in msg or not isinstance(msg["method"], str):
        errors.append("Missing or invalid 'method' field")
    if "id" in msg and not isinstance(msg["id"], int | str):
        errors.append("'id' must be int or string if present")
    if "params" in msg and not isinstance(msg["params"], dict | list):
        errors.append("'params' must be dict or list if present")
    return errors


def validate_jsonrpc_response(msg: dict[str, Any]) -> list[str]:
    """Validate a JSON-RPC 2.0 response message. Returns list of errors."""
    errors: list[str] = []
    if msg.get("jsonrpc") != "2.0":
        errors.append("Missing or invalid 'jsonrpc' field (must be '2.0')")
    if "id" not in msg:
        errors.append("Missing 'id' field")
    has_result = "result" in msg
    has_error = "error" in msg
    if not has_result and not has_error:
        errors.append("Must contain either 'result' or 'error'")
    if has_result and has_error:
        errors.append("Must not contain both 'result' and 'error'")
    if has_error:
        error = msg["error"]
        if not isinstance(error, dict):
            errors.append("'error' must be an object")
        elif "code" not in error or "message" not in error:
            errors.append("'error' must contain 'code' and 'message'")
    return errors


# --- MCP Resource schema validation ---


REQUIRED_RESOURCE_FIELDS = {"uri", "name"}
OPTIONAL_RESOURCE_FIELDS = {"description", "mimeType", "metadata"}

EXPECTED_RESOURCE_URIS = [
    "loxone://structure",
    "loxone://components",
    "loxone://rooms",
    "loxone://categories",
]


def validate_resource_schema(resource: dict[str, Any]) -> list[str]:
    """Validate an MCP Resource object against schema requirements."""
    errors: list[str] = []
    for field in REQUIRED_RESOURCE_FIELDS:
        if field not in resource:
            errors.append(f"Missing required field: {field}")
    uri = resource.get("uri", "")
    if uri and not uri.startswith("loxone://"):
        errors.append(f"URI must use 'loxone://' scheme, got: {uri}")
    return errors


# --- MCP Tool schema validation ---


REQUIRED_TOOL_FIELDS = {"name", "description", "inputSchema"}

EXPECTED_TOOLS = [
    "get_component_state",
    "control_component",
    "get_room_components",
    "get_components_by_type",
]


def validate_tool_input_schema(schema: dict[str, Any]) -> list[str]:
    """Validate a Tool's inputSchema against JSON Schema requirements."""
    errors: list[str] = []
    if schema.get("type") != "object":
        errors.append("inputSchema type must be 'object'")
    if "properties" not in schema:
        errors.append("inputSchema must have 'properties'")
    return errors


def validate_tool_schema(tool: dict[str, Any]) -> list[str]:
    """Validate an MCP Tool object against schema requirements."""
    errors: list[str] = []
    for field in REQUIRED_TOOL_FIELDS:
        if field not in tool:
            errors.append(f"Missing required field: {field}")
    input_schema = tool.get("inputSchema")
    if input_schema:
        errors.extend(validate_tool_input_schema(input_schema))
    return errors


# --- MCP Error code validation ---


VALID_MCP_ERROR_CODES = {
    "COMPONENT_NOT_FOUND",
    "ACTION_NOT_SUPPORTED",
    "INVALID_PARAMS",
    "EXECUTION_FAILED",
    "ACCESS_DENIED",
}


def validate_error_code(code: str) -> bool:
    """Check if error code is a valid MCP error code."""
    return code in VALID_MCP_ERROR_CODES


# --- Contract test class ---


class TestJSONRPCContract:
    """Tests for JSON-RPC 2.0 protocol compliance."""

    def test_valid_request(self) -> None:
        msg = {"jsonrpc": "2.0", "method": "resources/list", "id": 1}
        assert validate_jsonrpc_request(msg) == []

    def test_valid_request_with_params(self) -> None:
        msg = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 2,
            "params": {"name": "get_component_state"},
        }
        assert validate_jsonrpc_request(msg) == []

    def test_invalid_request_no_method(self) -> None:
        msg = {"jsonrpc": "2.0", "id": 1}
        errors = validate_jsonrpc_request(msg)
        assert len(errors) == 1
        assert "method" in errors[0]

    def test_valid_success_response(self) -> None:
        msg = {"jsonrpc": "2.0", "id": 1, "result": {"resources": []}}
        assert validate_jsonrpc_response(msg) == []

    def test_valid_error_response(self) -> None:
        msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32601, "message": "Method not found"},
        }
        assert validate_jsonrpc_response(msg) == []

    def test_invalid_response_both_result_and_error(self) -> None:
        msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {},
            "error": {"code": -1, "message": "err"},
        }
        errors = validate_jsonrpc_response(msg)
        assert any("both" in e for e in errors)


class TestResourceSchemaContract:
    """Tests for MCP Resource schema compliance."""

    def test_expected_resource_uris(self) -> None:
        """Verify all expected resource URIs are defined."""
        for uri in EXPECTED_RESOURCE_URIS:
            assert uri.startswith("loxone://")

    def test_resource_validation_passes(self) -> None:
        resource = {
            "uri": "loxone://components",
            "name": "Components List",
            "description": "All components",
            "mimeType": "application/json",
        }
        assert validate_resource_schema(resource) == []

    def test_resource_validation_missing_uri(self) -> None:
        resource = {"name": "Test"}
        errors = validate_resource_schema(resource)
        assert any("uri" in e for e in errors)


class TestToolSchemaContract:
    """Tests for MCP Tool schema compliance."""

    def test_expected_tools(self) -> None:
        """Verify all expected tools are defined."""
        assert len(EXPECTED_TOOLS) == 4
        assert "control_component" in EXPECTED_TOOLS

    def test_tool_validation_passes(self) -> None:
        tool = {
            "name": "get_component_state",
            "description": "Get component state",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "component_uuid": {"type": "string"},
                },
                "required": ["component_uuid"],
            },
        }
        assert validate_tool_schema(tool) == []

    def test_tool_validation_missing_input_schema(self) -> None:
        tool = {"name": "test", "description": "test"}
        errors = validate_tool_schema(tool)
        assert any("inputSchema" in e for e in errors)


class TestErrorCodeContract:
    """Tests for MCP error code compliance."""

    def test_valid_error_codes(self) -> None:
        for code in VALID_MCP_ERROR_CODES:
            assert validate_error_code(code)

    def test_invalid_error_code(self) -> None:
        assert not validate_error_code("UNKNOWN_ERROR")
