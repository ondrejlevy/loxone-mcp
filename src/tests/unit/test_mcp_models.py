"""Unit tests for MCP domain models (mcp/models.py).

Tests MCPResource, MCPTool, MCPNotification dataclasses,
ResourceMimeType enum, and predefined RESOURCES/TOOLS lists.
"""

from __future__ import annotations

from loxone_mcp.mcp.models import (
    MCPNotification,
    MCPResource,
    MCPTool,
    RESOURCES,
    ResourceMimeType,
    TOOLS,
)


class TestResourceMimeType:
    def test_json_value(self) -> None:
        assert ResourceMimeType.JSON == "application/json"

    def test_text_value(self) -> None:
        assert ResourceMimeType.TEXT == "text/plain"

    def test_str_enum(self) -> None:
        assert isinstance(ResourceMimeType.JSON, str)


class TestMCPResource:
    def test_create(self) -> None:
        r = MCPResource(
            uri="loxone://test",
            name="Test",
            description="A test resource",
        )
        assert r.uri == "loxone://test"
        assert r.name == "Test"
        assert r.description == "A test resource"
        assert r.mime_type == ResourceMimeType.JSON  # default

    def test_custom_mime_type(self) -> None:
        r = MCPResource(
            uri="loxone://text",
            name="Text",
            description="Text resource",
            mime_type=ResourceMimeType.TEXT,
        )
        assert r.mime_type == ResourceMimeType.TEXT


class TestMCPTool:
    def test_create(self) -> None:
        t = MCPTool(
            name="test_tool",
            description="A test tool",
        )
        assert t.name == "test_tool"
        assert t.description == "A test tool"
        assert t.input_schema == {}

    def test_with_schema(self) -> None:
        schema = {"type": "object", "properties": {"a": {"type": "string"}}}
        t = MCPTool(
            name="tool",
            description="desc",
            input_schema=schema,
        )
        assert t.input_schema == schema


class TestMCPNotification:
    def test_create(self) -> None:
        n = MCPNotification(method="notifications/resources/updated")
        assert n.method == "notifications/resources/updated"
        assert n.params == {}

    def test_with_params(self) -> None:
        n = MCPNotification(
            method="notifications/resources/updated",
            params={"uri": "loxone://components"},
        )
        assert n.params["uri"] == "loxone://components"


class TestPredefinedResources:
    def test_resources_count(self) -> None:
        assert len(RESOURCES) == 4

    def test_resource_uris(self) -> None:
        uris = {r.uri for r in RESOURCES}
        assert "loxone://structure" in uris
        assert "loxone://components" in uris
        assert "loxone://rooms" in uris
        assert "loxone://categories" in uris

    def test_all_have_names(self) -> None:
        for r in RESOURCES:
            assert r.name, f"Resource {r.uri} missing name"
            assert r.description, f"Resource {r.uri} missing description"


class TestPredefinedTools:
    def test_tools_count(self) -> None:
        assert len(TOOLS) == 4

    def test_tool_names(self) -> None:
        names = {t.name for t in TOOLS}
        assert "get_component_state" in names
        assert "control_component" in names
        assert "get_room_components" in names
        assert "get_components_by_type" in names

    def test_all_have_schemas(self) -> None:
        for t in TOOLS:
            assert t.input_schema, f"Tool {t.name} missing input_schema"
            assert t.input_schema["type"] == "object"
            assert "properties" in t.input_schema
            assert "required" in t.input_schema

    def test_control_component_params(self) -> None:
        tool = next(t for t in TOOLS if t.name == "control_component")
        assert "component_uuid" in tool.input_schema["properties"]
        assert "action" in tool.input_schema["properties"]
        assert "component_uuid" in tool.input_schema["required"]
        assert "action" in tool.input_schema["required"]
