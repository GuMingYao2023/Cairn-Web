from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Literal


def test_worker_connection(
    worker_type: Literal["claudecode", "codex", "pi", "mock"],
    env: dict[str, str],
) -> tuple[bool, str]:
    """Test a worker endpoint by making a minimal API call.

    Returns (success, message) — never raises.
    """
    if worker_type == "mock":
        return True, "Mock worker is always available"

    try:
        url, headers, body = _build_test_request(worker_type, env)
    except KeyError as exc:
        return False, f"Missing environment variable: {exc}"
    except ValueError as exc:
        return False, str(exc)

    return _do_http_test(url, headers, body)


def _build_test_request(
    worker_type: str, env: dict[str, str]
) -> tuple[str, dict[str, str], str]:
    """Build the HTTP request parameters for a given worker type."""
    if worker_type == "claudecode":
        base_url = env["ANTHROPIC_BASE_URL"].rstrip("/")
        return (
            f"{base_url}/v1/messages",
            {
                "Authorization": f"Bearer {env['ANTHROPIC_AUTH_TOKEN']}",
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json.dumps({
                "model": env["ANTHROPIC_MODEL"],
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "ping"}],
            }),
        )
    elif worker_type == "codex":
        base_url = env["CODEX_BASE_URL"].rstrip("/")
        return (
            f"{base_url}/responses",
            {
                "Authorization": f"Bearer {env['OPENAI_API_KEY']}",
                "content-type": "application/json",
            },
            json.dumps({
                "input": [{"content": "ping", "role": "user"}],
                "model": env["CODEX_MODEL"],
                "stream": False,
            }),
        )
    elif worker_type == "pi":
        base_url = env["PI_BASE_URL"].rstrip("/")
        return (
            f"{base_url}/chat/completions",
            {
                "Authorization": f"Bearer {env['PI_API_KEY']}",
                "content-type": "application/json",
            },
            json.dumps({
                "model": env["PI_MODEL"],
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 10,
            }),
        )
    else:
        raise ValueError(f"Unknown worker type: {worker_type}")


def _do_http_test(url: str, headers: dict[str, str], body: str) -> tuple[bool, str]:
    """Execute the HTTP request and return a (success, message) tuple."""
    try:
        req = urllib.request.Request(url, data=body.encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as response:
            status = response.status
            return True, f"Connected successfully (HTTP {status})"
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")[:300]
        return False, f"HTTP {exc.code}: {body_text}"
    except urllib.error.URLError as exc:
        return False, f"Connection failed: {exc.reason}"
    except TimeoutError:
        return False, "Connection timed out after 10 seconds"
    except Exception as exc:
        return False, f"Unexpected error: {exc}"
