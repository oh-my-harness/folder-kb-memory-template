"""Build a reproducible, source-only template ZIP and platform registration."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build():
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    archive = output / "memory-files-0.1.0.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        info = zipfile.ZipInfo("program.py", (2026, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        z.writestr(info, (ROOT / "template/program.py").read_bytes())
    registration = {
        "protocol_version": "1.1", "id": "memory-files", "name": "通用文件记忆", "version": "0.1.0",
        "description": "索引＋独立记忆文件；增量整理、作用域、证据溯源和冲突待审。生成候选，不自动发布。",
        "maintainer": "oh-my-harness", "capabilities": ["initialize", "update"],
        "entrypoints": {op: ["python", "program.py", op] for op in ("initialize", "update")},
        "runtime": {"type": "trusted-python-demo", "timeout_seconds": 900, "memory_mb": 512, "cpus": 1},
        "required_secrets": [],
        "config_schema": {"type": "object", "additionalProperties": False, "properties": {
            "mode": {"type": "string", "enum": ["llm", "structured"], "default": "llm"},
            "default_scope": {"type": "string", "minLength": 1, "maxLength": 200, "default": "personal"},
            "max_memories": {"type": "integer", "minimum": 1, "maximum": 100, "default": 100},
            "max_context_chars": {"type": "integer", "minimum": 4000, "maximum": 160000, "default": 80000}}},
        "output": {"directory": "workspace", "required_files": ["INDEX.md"]},
        "source": {"type": "uploaded-zip", "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}}
    (output / "registration.json").write_text(json.dumps(registration, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return archive, registration


if __name__ == "__main__":
    archive, registration = build()
    print(json.dumps({"archive": str(archive), "sha256": registration["source"]["archive_sha256"]}, indent=2))
