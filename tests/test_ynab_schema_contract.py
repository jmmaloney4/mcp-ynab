import importlib.util
import json
import os
import re
import unittest
import urllib.request
from datetime import datetime
from pathlib import Path


API_BASE_URL = "https://api.ynab.com/v1"
OPENAPI_SPEC_URL = "https://api.ynab.com/papi/open_api_spec.yaml"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = PROJECT_ROOT / "main.py"
GOAL_SNOOZED_AT = "goal_snoozed_at"


def load_main_module():
    spec = importlib.util.spec_from_file_location("mcp_ynab_main", MAIN_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_api_key():
    return os.getenv("YNAB_API_KEY") or os.getenv("YNAB_TOKEN")


def fetch_text(url, token=None):
    request = urllib.request.Request(url)
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def fetch_json(url, token):
    return json.loads(fetch_text(url, token=token))


def iter_key_paths(value, target_key, path="$"):
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key == target_key:
                yield child_path, child
            yield from iter_key_paths(child, target_key, path=child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_key_paths(child, target_key, path=f"{path}[{index}]")


def is_rfc3339_datetime(value):
    if not isinstance(value, str):
        return False

    normalized_value = value.replace("Z", "+00:00")
    try:
        datetime.fromisoformat(normalized_value)
    except ValueError:
        return False
    return True


class SanitizeOpenApiSpecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.main = load_main_module()
        except Exception as exc:  # pragma: no cover - environment-specific skip
            cls.main = None
            cls.import_error = exc
        else:
            cls.import_error = None

    def setUp(self):
        if self.main is None:
            self.skipTest(f"Unable to import main.py: {self.import_error}")
        self.assertIsNotNone(self.main)

    def test_sanitizer_removes_nullable_datetime_format(self):
        openapi_spec = {
            "components": {
                "schemas": {
                    "Example": {
                        "type": "object",
                        "properties": {
                            GOAL_SNOOZED_AT: {
                                "type": ["string", "null"],
                                "format": "date-time",
                            }
                        },
                    }
                }
            }
        }

        assert self.main is not None
        self.main.sanitize_openapi_spec(openapi_spec)

        field_schema = openapi_spec["components"]["schemas"]["Example"]["properties"][
            GOAL_SNOOZED_AT
        ]
        self.assertNotIn("format", field_schema)

    def test_sanitizer_keeps_non_nullable_datetime_format(self):
        openapi_spec = {
            "components": {
                "schemas": {
                    "Example": {
                        "type": "object",
                        "properties": {
                            "last_modified_on": {
                                "type": "string",
                                "format": "date-time",
                            }
                        },
                    }
                }
            }
        }

        assert self.main is not None
        self.main.sanitize_openapi_spec(openapi_spec)

        field_schema = openapi_spec["components"]["schemas"]["Example"]["properties"][
            "last_modified_on"
        ]
        self.assertEqual(field_schema["format"], "date-time")


class YnabSchemaContractIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api_key = get_api_key()
        if not cls.api_key:
            raise unittest.SkipTest("Set YNAB_API_KEY or YNAB_TOKEN to run YNAB tests")

    def test_openapi_declares_goal_snoozed_at_as_datetime(self):
        spec_text = fetch_text(OPENAPI_SPEC_URL)

        match = re.search(
            r"goal_snoozed_at:\s*\n(?:[ \t]+.*\n){0,12}",
            spec_text,
            re.MULTILINE,
        )
        self.assertIsNotNone(match, "goal_snoozed_at not found in published OpenAPI spec")

        assert match is not None
        field_block = match.group(0)
        self.assertIn("format: date-time", field_block)

    def test_last_used_budget_goal_snoozed_at_values_match_contract(self):
        response = fetch_json(f"{API_BASE_URL}/budgets/last-used", token=self.api_key)

        goal_snoozed_at_values = list(iter_key_paths(response, GOAL_SNOOZED_AT))
        self.assertGreater(
            len(goal_snoozed_at_values),
            0,
            "No goal_snoozed_at fields found in /budgets/last-used response",
        )

        invalid_values = [
            (path, value)
            for path, value in goal_snoozed_at_values
            if value is not None and not is_rfc3339_datetime(value)
        ]

        self.assertFalse(
            invalid_values,
            "Found goal_snoozed_at values that do not match the published "
            f"date-time contract: {invalid_values[:5]}",
        )

    def test_last_used_plan_matches_fastmcp_output_schema(self):
        try:
            import httpx
            import yaml
            from pydantic import TypeAdapter
            from fastmcp.utilities.json_schema_type import json_schema_to_type
            from fastmcp.utilities.openapi.parser import parse_openapi_to_http_routes
            from fastmcp.utilities.openapi.schemas import extract_output_schema_from_responses
        except Exception as exc:  # pragma: no cover - environment-specific skip
            self.skipTest(f"FastMCP validation dependencies unavailable: {exc}")

        spec_text = httpx.get(OPENAPI_SPEC_URL, timeout=30).text
        openapi_spec = yaml.safe_load(spec_text)
        routes = parse_openapi_to_http_routes(openapi_spec)
        route = next(route for route in routes if route.operation_id == "getPlanById")
        output_schema = extract_output_schema_from_responses(
            route.responses,
            route.response_schemas,
        )
        self.assertIsNotNone(output_schema)

        response = fetch_json(f"{API_BASE_URL}/plans/last-used", token=self.api_key)

        assert output_schema is not None
        TypeAdapter(json_schema_to_type(output_schema)).validate_python(response)


if __name__ == "__main__":
    unittest.main()
