"""Install a built template through the authenticated Folder KB admin API."""
import argparse
import json
import os
from pathlib import Path
from urllib import request, error, parse

from package import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--token-env", default="FKB_ADMIN_TOKEN")
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--library-id")
    parser.add_argument("--workspace-root", help="Root relative to the platform KB_ROOT; complete update workspace")
    parser.add_argument("--mode", choices=["structured", "llm"], default="llm")
    args = parser.parse_args()
    token = args.token_file.read_text(encoding="utf-8").strip() if args.token_file else os.environ.get(args.token_env, "")
    if not token:
        parser.error("Admin token missing")
    if bool(args.library_id) != bool(args.workspace_root):
        parser.error("Binding requires both --library-id and --workspace-root")
    parsed = parse.urlsplit(args.url)
    if parsed.scheme not in ("http", "https") or parsed.username or parsed.password or parsed.query or parsed.fragment:
        parser.error("Invalid platform URL")
    class NoRedirect(request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = request.build_opener(NoRedirect())
    def call(method, path, payload, kind="application/json"):
        data = json.dumps(payload).encode() if kind == "application/json" else payload
        req = request.Request(args.url.rstrip("/") + path, data=data, method=method,
            headers={"Authorization": "Bearer " + token, "Content-Type": kind})
        with opener.open(req, timeout=30) as response:
            return json.load(response)
    definition = json.loads((ROOT / "dist/registration.json").read_text(encoding="utf-8"))
    try:
        call("POST", "/admin/api/templates", definition)
        base = "/admin/api/templates/" + definition["id"] + "/versions/" + definition["version"]
        call("PUT", base + "/package", (ROOT / "dist/memory-files-0.1.0.zip").read_bytes(), "application/zip")
        if args.library_id:
            if not all(c.isalnum() or c in "_-" for c in args.library_id):
                parser.error("Invalid library ID")
            call("PUT", "/admin/api/libraries/" + args.library_id + "/template", {
                "template_id": definition["id"], "template_version": definition["version"], "config": {"mode": args.mode},
                "workspace": {"type": "local", "root_path": args.workspace_root, "knowledge_subpath": "knowledge"}})
        print(json.dumps({"installed": True, "bound_library": args.library_id}, ensure_ascii=False))
    except error.HTTPError as exc:
        print("Admin API failed: HTTP " + str(exc.code))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
