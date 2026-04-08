"""
api_server.py — minimal HTTP API for ACORN extension imports.

Routes:
  POST /api/acorn/import
  GET  /api/acorn/latest
  GET  /api/acorn/status

The server stores ACORN imports in Supabase Postgres.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from supabase import Client, create_client

from integrations.acorn_store import AcornStoreError, validate_payload


class ApiStorageError(RuntimeError):
    """Raised when the backend storage layer fails."""


def _get_supabase() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise ApiStorageError("SUPABASE_URL and SUPABASE_KEY must be configured")
    return create_client(url, key)


def _insert_acorn_import(payload: dict) -> dict:
    validated = validate_payload(payload)
    row = {
        "import_code": validated["importCode"],
        "user_id": None,
        "data": validated,
        "imported_at": validated["importedAt"],
    }
    try:
        response = (
            _get_supabase()
            .table("acorn_imports")
            .insert(row)
            .execute()
        )
    except Exception as exc:
        raise ApiStorageError("Failed to store ACORN import") from exc

    data = getattr(response, "data", None) or []
    if not data:
        raise ApiStorageError("Supabase returned no inserted ACORN import row")
    return validated


def _read_latest(import_code: str) -> dict | None:
    try:
        response = (
            _get_supabase()
            .table("acorn_imports")
            .select("data")
            .eq("import_code", import_code)
            .order("imported_at", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise ApiStorageError("Failed to load latest ACORN import") from exc

    rows = getattr(response, "data", None) or []
    if not rows:
        return None
    return rows[0].get("data")


def _get_status(import_code: str) -> dict:
    try:
        response = (
            _get_supabase()
            .table("acorn_imports")
            .select("data")
            .eq("import_code", import_code)
            .order("imported_at", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise ApiStorageError("Failed to load ACORN import status") from exc

    rows = getattr(response, "data", None) or []
    if not rows:
        return {"exists": False, "importedAt": None, "importCode": import_code}

    latest = rows[0].get("data") or {}
    return {
        "exists": True,
        "importedAt": latest.get("importedAt"),
        "importCode": latest.get("importCode", import_code),
        "courseCount": len(latest.get("courses", [])),
    }


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "uoft-agent-api/0.1"

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_common_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        import_code = self._get_import_code(parsed.query)

        if parsed.path == "/api/acorn/latest":
            if not import_code:
                self._send_json(400, {"ok": False, "error": "Missing import_code query parameter"})
                return

            try:
                latest = _read_latest(import_code)
            except ApiStorageError as exc:
                self._send_json(500, {"ok": False, "error": str(exc)})
                return

            if latest is None:
                self._send_json(200, {
                    "ok": True,
                    "exists": False,
                    "message": "No ACORN data has been imported yet.",
                    "data": None,
                })
                return

            self._send_json(200, {"ok": True, "exists": True, "data": latest})
            return

        if parsed.path == "/api/acorn/status":
            if not import_code:
                self._send_json(400, {"ok": False, "error": "Missing import_code query parameter"})
                return
            try:
                status = _get_status(import_code)
            except ApiStorageError as exc:
                self._send_json(500, {"ok": False, "error": str(exc)})
                return
            self._send_json(200, {"ok": True, **status})
            return

        self._send_json(404, {"ok": False, "error": "Not found"})

    def do_POST(self):
        if self.path != "/api/acorn/import":
            self._send_json(404, {"ok": False, "error": "Not found"})
            return

        try:
            body = self._read_json_body()
            stored = _insert_acorn_import(body)
        except AcornStoreError as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})
            return
        except json.JSONDecodeError:
            self._send_json(400, {"ok": False, "error": "Request body must be valid JSON"})
            return
        except ApiStorageError as exc:
            self._send_json(500, {"ok": False, "error": str(exc)})
            return
        except Exception as exc:
            self._send_json(500, {"ok": False, "error": str(exc)})
            return

        self._send_json(200, {
            "ok": True,
            "message": "ACORN data imported successfully",
            "importedAt": stored["importedAt"],
            "courseCount": len(stored["courses"]),
        })

    def log_message(self, format, *args):
        # Keep the local API quiet unless an actual HTTP request is being debugged.
        return

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self._send_common_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_common_headers(self):
        # Allow the local extension to talk to the local API during development.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    @staticmethod
    def _get_import_code(query: str) -> str | None:
        params = parse_qs(query)
        value = params.get("import_code", [None])[0]
        return value.strip() if isinstance(value, str) and value.strip() else None


def main(host: str | None = None, port: int | None = None):
    host = host or os.getenv("HOST", "0.0.0.0")
    port = port or int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), ApiHandler)
    print(f"UofT Agent API listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
