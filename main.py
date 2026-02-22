import os
import httpx
import yaml
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

if __name__ == "__main__":
    ynab_token = os.getenv('YNAB_TOKEN')
    transport = os.getenv('TRANSPORT') or 'http'

    if not ynab_token:
        raise ToolError("YNAB_TOKEN is missing!")

    openapi_spec_response = httpx.get("https://api.ynab.com/papi/open_api_spec.yaml", timeout=10.0)
    openapi_spec_response.raise_for_status()
    openapi_spec = yaml.safe_load(openapi_spec_response.text)

    client = httpx.AsyncClient(
        base_url="https://api.ynab.com/v1",
        headers={"Authorization": f"Bearer {ynab_token}"},
    )

    mcp = FastMCP.from_openapi(openapi_spec=openapi_spec, client=client, name="YNAB MCP Server")
    if transport == 'http':
        mcp.run(transport="http", host="0.0.0.0", port=8080)
    elif transport == 'stdio':
        mcp.run()
    else:
        raise ToolError(f"Unknown transport: {transport}!")
