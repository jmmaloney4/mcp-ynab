import os

import httpx
import yaml
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError


async def sanitize_headers(request):
    # seeing x-forwarded headers being carried over.
    # strip them out before making a request to YNAB.
    strip_headers = [
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-port",
        "x-forwarded-proto",
        "x-forwarded-server",
        "x-real-ip",
    ]
    for header in strip_headers:
        request.headers.pop(header, None)


def schema_is_nullable(schema):
    schema_type = schema.get("type")
    if isinstance(schema_type, list) and "null" in schema_type:
        return True

    for key in ("anyOf", "oneOf"):
        variants = schema.get(key, [])
        if any(variant.get("type") == "null" for variant in variants):
            return True

    return False


def relax_nullable_string_formats(node):
    if isinstance(node, dict):
        node_format = node.get("format")
        if (
            isinstance(node_format, str)
            and node_format in {"date", "date-time"}
            and schema_is_nullable(node)
        ):
            node.pop("format", None)

        for value in node.values():
            relax_nullable_string_formats(value)
    elif isinstance(node, list):
        for value in node:
            relax_nullable_string_formats(value)


def sanitize_openapi_spec(openapi_spec):
    relax_nullable_string_formats(openapi_spec)
    return openapi_spec


if __name__ == "__main__":
    ynab_token = os.getenv("YNAB_TOKEN") or os.getenv("YNAB_API_KEY")
    transport = os.getenv("TRANSPORT") or "http"

    if not ynab_token:
        raise ToolError("YNAB_TOKEN or YNAB_API_KEY is missing!")

    openapi_spec_response = httpx.get(
        "https://api.ynab.com/papi/open_api_spec.yaml", timeout=10.0
    )
    openapi_spec_response.raise_for_status()
    openapi_spec = yaml.safe_load(openapi_spec_response.text)
    openapi_spec = sanitize_openapi_spec(openapi_spec)

    client = httpx.AsyncClient(
        base_url="https://api.ynab.com/v1",
        headers={"Authorization": f"Bearer {ynab_token}"},
        event_hooks={"request": [sanitize_headers]},
    )

    mcp = FastMCP.from_openapi(
        openapi_spec=openapi_spec,
        client=client,
        name="YNAB MCP Server",
        validate_output=False,
    )
    if transport == "http":
        mcp.run(transport="http", host="0.0.0.0", port=8080)
    elif transport == "stdio":
        mcp.run()
    else:
        raise ToolError(f"Unknown transport: {transport}!")
