# mcp-ynab

FastMCP server that exposes the [YNAB API](https://api.ynab.com/) via MCP using YNAB's published OpenAPI spec.

## Requirements

- Python 3.12+
- A YNAB personal access token
- `uv` (recommended) or `pip`

## Configuration

Environment variables:

- `YNAB_TOKEN` (required): your YNAB API token
- `TRANSPORT` (optional): `http` (default) or `stdio`

## Run Locally

Using `uv`:

```bash
uv sync
export YNAB_TOKEN="your_token_here"
export TRANSPORT="http"   # optional, defaults to http
uv run python main.py
```

HTTP mode starts the server on `0.0.0.0:8080`.

## Docker

Use the prebuilt image from GHCR:

```bash
docker pull ghcr.io/alexfu/mcp-ynab:latest
```

Run prebuilt image in HTTP mode:

```bash
docker run --rm -p 8080:8080 \
  -e YNAB_TOKEN="your_token_here" \
  -e TRANSPORT="http" \
  ghcr.io/alexfu/mcp-ynab:latest
```

Run prebuilt image in stdio mode:

```bash
docker run --rm \
  -e YNAB_TOKEN="your_token_here" \
  -e TRANSPORT="stdio" \
  ghcr.io/alexfu/mcp-ynab:latest
```

## Notes

- The server fetches YNAB's OpenAPI spec at startup from `https://api.ynab.com/papi/open_api_spec.yaml`.
- Startup will fail if `YNAB_TOKEN` is missing, `TRANSPORT` is invalid, or the spec request fails.
