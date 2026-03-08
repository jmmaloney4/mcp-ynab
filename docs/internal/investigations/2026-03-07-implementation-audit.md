# Implementation Audit

Date: 2026-03-07
Project: `mcp-ynab`

## Question

Is this OpenAPI-generated MCP server built properly? Is there a better way to structure it, and are there community libraries worth considering?

## Short Answer

Yes. The current implementation is fundamentally sound and uses a reasonable approach for this kind of project. The server is small, clear, and correctly leans on FastMCP's OpenAPI support instead of hand-writing a large MCP wrapper around the YNAB API.

That said, there are a handful of correctness, dependency, security, and maintainability issues that should be cleaned up. There are also alternative approaches in the ecosystem, but for a Python implementation, the current FastMCP-based design is already close to the best fit.

## What the Project Does

`mcp-ynab` is a Python MCP server that exposes the YNAB REST API as MCP tools.

At startup it:

1. Fetches YNAB's OpenAPI spec from `https://api.ynab.com/papi/open_api_spec.yaml`
2. Sanitizes nullable `date` / `date-time` fields in the schema
3. Creates an authenticated `httpx.AsyncClient` for the YNAB API
4. Uses `FastMCP.from_openapi()` to generate MCP tools from the spec
5. Runs either over HTTP or stdio transport

This is runtime OpenAPI-driven generation, not a static code generation workflow.

## What Is Good

### 1. The core approach is good

Using `FastMCP.from_openapi()` is a sensible choice for a small Python MCP server backed by a third-party REST API.

Benefits:

- Very little boilerplate
- Easy to track upstream API changes
- Avoids hand-maintaining a large tool surface
- Uses an established MCP library instead of custom protocol code

### 2. The nullable datetime workaround is thoughtful

The `sanitize_openapi_spec()` logic addresses a real integration problem: YNAB publishes nullable datetime fields that can cause validation trouble when mapped into generated schemas.

The sanitizer is narrow and understandable:

- It only removes `format` when the schema is nullable
- It preserves `format` for non-nullable fields
- It is backed by tests

### 3. The project stays intentionally small

The implementation is roughly one main file plus tests. That is appropriate here. There is no clear benefit to introducing a larger architecture unless the project starts needing custom tools, richer auth flows, caching, or filtered tool registration.

### 4. Tests exist for the risky part

The tests focus on the most failure-prone area: the contract mismatch between published schema and live API behavior. That is the right place to invest test effort.

## Problems Found

### 1. Startup errors use `ToolError` in the wrong place

File: `main.py:64`
File: `main.py:90`

`ToolError` is meant for failures inside MCP tool execution. It is not the right error type for process startup or configuration validation.

Current uses:

- missing `YNAB_TOKEN` / `YNAB_API_KEY`
- invalid `TRANSPORT`

Better choices:

- `ValueError`
- `RuntimeError`
- `SystemExit` with a clear message

### 2. The async HTTP client is never explicitly closed

File: `main.py:73`

`httpx.AsyncClient` should be closed cleanly on shutdown. The current code constructs it and passes it into FastMCP, but there is no explicit lifecycle management visible in this repository.

Risk:

- leaked connections during shutdown
- unclear resource ownership

Recommendation:

- verify whether FastMCP takes ownership and closes the client
- if not, wrap lifecycle explicitly or use FastMCP hooks if available

### 3. No timeout on proxied YNAB API requests

File: `main.py:73`

The startup spec fetch uses a timeout, but the main `AsyncClient` does not. That means MCP tool calls may hang indefinitely if YNAB stalls.

Recommendation:

- set a client timeout explicitly
- consider separate connect/read timeouts if needed

### 4. Direct dependencies are incomplete

File: `pyproject.toml:7`

The project directly imports `httpx` and `yaml`, but only declares `fastmcp` as a dependency.

This works only because those packages currently arrive transitively.

Risk:

- a FastMCP dependency change can break this project unexpectedly

Recommendation:

- add direct dependencies for `httpx` and `pyyaml`

### 5. HTTP mode is exposed broadly and unauthenticated

File: `main.py:86`

The HTTP transport binds to `0.0.0.0:8080`. That is convenient for containers, but it also means any reachable client can trigger requests against the user's YNAB account through this server.

Risk depends on deployment context, but for a finance API wrapper this matters.

Recommendation:

- document the trust model clearly
- prefer stdio by default for local use
- consider binding to localhost by default outside Docker
- add auth or network restrictions if HTTP mode is intended for shared environments

### 6. Output validation is disabled

File: `main.py:83`

`validate_output=False` is understandable as a workaround, but it weakens confidence in generated tool results.

Given that the sanitizer now exists, this should be revisited.

Recommendation:

- test whether the sanitizer is sufficient to safely enable output validation
- if validation must stay off, document exactly why

### 7. All endpoints are exposed as tools

File: `main.py:79`

Automatically exposing the full OpenAPI surface is efficient, but not always ideal for MCP usability.

Problems with a very large tool surface:

- harder tool selection for the model
- more noise in capability discovery
- more accidental invocation risk
- less room for tailored descriptions or grouped workflows

Recommendation:

- consider filtering tool exposure to the highest-value endpoints
- or keep full coverage but add custom high-level tools for common flows

### 8. The server depends on a live upstream spec at startup

File: `main.py:66`

Fetching the spec at runtime is convenient, but it introduces startup fragility.

Failure cases:

- YNAB spec URL changes
- temporary upstream outage
- network unavailability in local or container environments
- schema changes that silently alter generated tools

Recommendation:

- consider pinning or caching the spec
- or store a vendored fallback copy in the repo
- or log the fetched spec version / hash for easier debugging

### 9. The stale build artifact should not be in the repo

Path: `build/lib/main.py`

The repository contains an older built copy of `main.py` that does not match the main implementation.

Risk:

- confusion during audits
- mistaken edits to generated or stale output
- misleading packaging state

Recommendation:

- delete it from the repo
- ensure `build/` is ignored

### 10. Metadata still points at the upstream fork source

File: `Dockerfile:3`
File: `README.md:36`
File: `README.md:45`
File: `README.md:54`

The Docker label and image references still point at `alexfu/mcp-ynab`.

Recommendation:

- update image metadata and README examples to point at the maintained repository/image location

## Is It Built Properly?

Overall: yes, with caveats.

The server is not badly designed. In fact, the design is refreshingly direct:

- fetch spec
- patch spec
- generate tools
- run server

That is a legitimate and maintainable architecture for this scale.

The main problems are not architectural failures. They are operational details:

- dependency declarations
- client lifecycle
- transport exposure
- validation posture
- startup resilience

So the right conclusion is: built properly in principle, but not yet polished enough for a high-confidence production-quality package.

## Better Ways To Do It

### Best option for this repo: keep the current pattern, improve the edges

For a Python codebase, the best immediate path is not a rewrite. It is to keep the FastMCP OpenAPI-driven design and tighten the implementation.

Suggested improvements:

1. Add explicit dependencies for `httpx` and `pyyaml`
2. Replace startup `ToolError` usage with normal startup/configuration exceptions
3. Add explicit request timeout configuration to the YNAB client
4. Revisit `validate_output=False`
5. Decide whether full endpoint exposure is actually desirable
6. Add a strategy for spec pinning, caching, or fallback
7. Remove stale build output and fix docs / metadata

### A stronger hybrid model may be better than pure OpenAPI passthrough

If this server is intended for real LLM usage rather than raw API completeness, a hybrid model is probably better over time:

- keep generated low-level tools for full coverage
- add a smaller set of hand-authored high-level tools for common user intents

Examples:

- get budget summary
- list overspent categories
- show recent transactions
- summarize account balances

That gives better model ergonomics than forcing the model to navigate only raw CRUD-style endpoints.

### Full manual MCP server implementation is only worth it if customization becomes the main goal

Hand-registering tools with the official SDK would give:

- better tool names
- more tailored descriptions
- curated schemas
- better auth, caching, and error mapping
- workflow-oriented tools instead of API-shaped tools

But it also means much more maintenance. For this repository's current scope, that tradeoff does not look worthwhile yet.

## MCP Libraries And Community Options

### Official building blocks

The official MCP ecosystem includes SDKs for TypeScript, Python, Go, and Java.

For TypeScript, the main packages are under `@modelcontextprotocol/*`, especially:

- `@modelcontextprotocol/server`
- `@modelcontextprotocol/node`
- `@modelcontextprotocol/express`

Core capabilities in MCP are:

- tools
- resources
- prompts

For this project, tools are the primary concern.

### Python library choice

For Python, FastMCP is currently a strong choice because it offers a high-level framework and direct OpenAPI support. For this project, that is a meaningful advantage.

### Community libraries worth knowing

Several community projects are working in the OpenAPI-to-MCP space.

Most relevant examples found during the audit:

- `automation-ai-labs/mcp-link`: converts OpenAPI APIs to MCP servers
- `harsha-iiiv/openapi-mcp-generator`: generates MCP server code from OpenAPI
- `getdatanaut/openmcp`: turns OpenAPI files into MCP servers with selective exposure
- `twilio-labs/mcp`: OpenAPI-driven MCP tooling in TypeScript
- `janwilmake/openapi-mcp-server`: related OpenAPI + MCP tooling

These are useful references, especially if the project ever moves toward:

- static code generation
- TypeScript-based distribution
- selective tool publishing
- stronger customization on top of generated scaffolding

## Recommended Direction

### Recommendation 1: keep FastMCP

Do not replace the current approach just because there are other libraries. For a Python implementation, FastMCP remains a reasonable default.

### Recommendation 2: harden the current implementation

Highest priority fixes:

1. declare direct dependencies
2. add client timeouts
3. fix startup exception types
4. address HTTP exposure defaults and documentation
5. remove stale artifacts and fork leftovers

### Recommendation 3: improve MCP ergonomics, not just API coverage

If the package is intended for day-to-day assistant use, the next meaningful improvement is likely not infrastructure. It is tool design.

That means:

- curating exposed operations
- improving descriptions
- adding a few opinionated composite tools

### Recommendation 4: consider spec pinning or fallback

This is the biggest reliability improvement available without changing the overall architecture.

## Bottom Line

This package is built on a good foundation.

It is not a bad OpenAPI-generated MCP server. It is actually a fairly clean one. The main issues are around polish and operational safety, not around the central architectural choice.

If the goal is a lightweight Python MCP wrapper around YNAB, staying with FastMCP and improving the current implementation is the best path.

If the goal evolves toward a highly polished end-user MCP product, the likely next step is a hybrid design: keep generated coverage where useful, but layer curated, hand-authored MCP tools on top.
