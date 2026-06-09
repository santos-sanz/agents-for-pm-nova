from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from hyper_demo.config import Settings, get_settings

JSONRPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2025-06-18"

PERPLEXITY_MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "perplexity_search",
        "description": (
            "Search the web with Perplexity Search API and return ranked source results."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "perplexity_ask",
        "description": "Ask Sonar Pro for a concise, cited answer using current web context.",
        "inputSchema": {
            "type": "object",
            "required": ["question"],
            "properties": {
                "question": {"type": "string"},
                "model": {"type": "string", "enum": ["sonar", "sonar-pro"]},
                "max_tokens": {"type": "integer", "minimum": 64, "maximum": 8000},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "perplexity_research",
        "description": "Run deeper source-backed research with Sonar Deep Research.",
        "inputSchema": {
            "type": "object",
            "required": ["topic"],
            "properties": {
                "topic": {"type": "string"},
                "focus": {"type": "string"},
                "max_tokens": {"type": "integer", "minimum": 256, "maximum": 32000},
                "strip_thinking": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "perplexity_reason",
        "description": "Use Sonar Reasoning Pro for source-aware analysis and decision support.",
        "inputSchema": {
            "type": "object",
            "required": ["problem"],
            "properties": {
                "problem": {"type": "string"},
                "context": {"type": "string"},
                "max_tokens": {"type": "integer", "minimum": 256, "maximum": 16000},
                "strip_thinking": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
]


class McpError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class PerplexityMcpServer:
    """Small Streamable-HTTP-compatible MCP bridge for Claude Managed Agents.

    Claude supplies the Perplexity API key as an Authorization bearer through a
    Managed Agents Vault credential. The key is only used server-side for the
    upstream Perplexity request and is never returned in MCP content.
    """

    def __init__(self, settings: Settings | None = None, timeout: int = 45) -> None:
        self.settings = settings or get_settings()
        self.timeout = timeout

    def handle_http(
        self,
        payload: Any,
        authorization: str | None,
    ) -> tuple[Any | None, int]:
        token = _bearer_token(authorization)
        if isinstance(payload, list):
            responses = [
                response
                for item in payload
                if (response := self._handle_request(item, token)) is not None
            ]
            return (responses, 200) if responses else (None, 202)
        response = self._handle_request(payload, token)
        return (response, 200) if response is not None else (None, 202)

    def _handle_request(self, request: Any, token: str) -> dict[str, Any] | None:
        if not isinstance(request, dict):
            return _error(None, -32600, "Invalid JSON-RPC request.")
        request_id = request.get("id")
        method = request.get("method")
        if not method:
            return _error(request_id, -32600, "JSON-RPC method is required.")
        try:
            if method == "initialize":
                return _result(request_id, self._initialize(request.get("params")))
            if method == "notifications/initialized":
                return None
            if method == "ping":
                return _result(request_id, {})
            if method == "tools/list":
                return _result(request_id, {"tools": PERPLEXITY_MCP_TOOLS})
            if method == "tools/call":
                return _result(request_id, self._call_tool(request.get("params"), token))
            return _error(request_id, -32601, f"Unknown MCP method: {method}.")
        except McpError as exc:
            return _error(request_id, exc.code, exc.message)
        except Exception as exc:
            return _error(request_id, -32603, f"Perplexity MCP request failed: {exc}")

    def _initialize(self, params: Any) -> dict[str, Any]:
        requested_version = ""
        if isinstance(params, dict):
            requested_version = str(params.get("protocolVersion") or "")
        return {
            "protocolVersion": requested_version or MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "hyperclaude-perplexity-mcp", "version": "0.1.0"},
        }

    def _call_tool(self, params: Any, token: str) -> dict[str, Any]:
        if not token:
            raise McpError(-32001, "Missing Perplexity bearer token from Managed Agents Vault.")
        if not isinstance(params, dict):
            raise McpError(-32602, "tools/call params must be an object.")
        name = str(params.get("name") or "")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise McpError(-32602, "tools/call arguments must be an object.")

        if name == "perplexity_search":
            structured = self._search(token, arguments)
        elif name == "perplexity_ask":
            structured = self._sonar(
                token,
                arguments,
                prompt_key="question",
                default_model="sonar-pro",
            )
        elif name == "perplexity_research":
            structured = self._sonar(
                token,
                arguments,
                prompt_key="topic",
                default_model="sonar-deep-research",
                context_key="focus",
            )
        elif name == "perplexity_reason":
            structured = self._sonar(
                token,
                arguments,
                prompt_key="problem",
                default_model="sonar-reasoning-pro",
                context_key="context",
            )
        else:
            raise McpError(-32602, f"Unknown Perplexity MCP tool: {name}.")

        return {
            "content": [{"type": "text", "text": _format_tool_text(name, structured, arguments)}],
            "structuredContent": structured,
            "isError": False,
        }

    def _search(self, token: str, arguments: dict[str, Any]) -> dict[str, Any]:
        query = _required_string(arguments, "query")
        max_results = _bounded_int(arguments.get("max_results"), default=5, minimum=1, maximum=10)
        payload = {"query": query, "max_results": max_results}
        return _post_json(f"{_api_origin(self.settings)}/search", token, payload, self.timeout)

    def _sonar(
        self,
        token: str,
        arguments: dict[str, Any],
        *,
        prompt_key: str,
        default_model: str,
        context_key: str | None = None,
    ) -> dict[str, Any]:
        prompt = _required_string(arguments, prompt_key)
        context = str(arguments.get(context_key) or "").strip() if context_key else ""
        if context:
            prompt = f"{prompt}\n\nContext:\n{context}"
        payload = {
            "model": str(arguments.get("model") or default_model),
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": _bounded_int(
                arguments.get("max_tokens"),
                default=2000,
                minimum=64,
                maximum=32000,
            ),
            "stream": False,
        }
        response = _post_json(
            f"{self.settings.perplexity_base_url}/sonar",
            token,
            payload,
            self.timeout,
        )
        if arguments.get("strip_thinking"):
            response = _strip_thinking(response)
        return response


def _post_json(url: str, token: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = _read_error_detail(exc)
        raise McpError(-32002, f"Perplexity API returned HTTP {exc.code}: {detail}") from exc
    except (TimeoutError, urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
        raise McpError(-32003, f"Perplexity API request failed: {exc}") from exc


def _read_error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace")[:500]
    except Exception:
        return "No response body."


def _format_tool_text(name: str, structured: dict[str, Any], arguments: dict[str, Any]) -> str:
    if name == "perplexity_search":
        lines = [f"Perplexity search: {_required_string(arguments, 'query')}"]
        for result in structured.get("results", [])[:10]:
            if not isinstance(result, dict):
                continue
            title = str(result.get("title") or "Untitled")
            url = str(result.get("url") or "")
            snippet = str(result.get("snippet") or "")
            lines.append(f"- {title} | {url} | {snippet}".strip())
        return "\n".join(lines)

    content = ""
    choices = structured.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            content = str(message.get("content") or "")
    lines = [content or json.dumps(structured, ensure_ascii=False)[:3000]]
    citations = [str(item) for item in structured.get("citations", []) if item]
    if citations:
        lines.append("\nCitations:")
        lines.extend(f"- {citation}" for citation in citations[:12])
    return "\n".join(lines)


def _strip_thinking(value: dict[str, Any]) -> dict[str, Any]:
    text_pattern = re.compile(r"<think>.*?</think>", flags=re.DOTALL | re.IGNORECASE)
    cleaned = json.loads(json.dumps(value))
    for choice in cleaned.get("choices", []):
        if not isinstance(choice, dict):
            continue
        message = choice.get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            message["content"] = text_pattern.sub("", message["content"]).strip()
    return cleaned


def _api_origin(settings: Settings) -> str:
    parsed = urlparse(settings.perplexity_base_url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        return ""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return ""
    return token.strip()


def _required_string(arguments: dict[str, Any], key: str) -> str:
    value = str(arguments.get(key) or "").strip()
    if not value:
        raise McpError(-32602, f"Argument '{key}' is required.")
    return value


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": {"code": code, "message": message},
    }
