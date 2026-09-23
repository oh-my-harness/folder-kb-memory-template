"""Run a disposable memory workflow; never changes an existing knowledge base."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("memory_program", ROOT / "template/program.py")
program = importlib.util.module_from_spec(spec)
spec.loader.exec_module(program)


def model_env(provider):
    env = {k: os.environ[k] for k in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH") if k in os.environ}
    env["PYTHONIOENCODING"] = "utf-8"
    mappings = {
        "memory": ("MEMORY_LLM_BASE_URL", "MEMORY_LLM_MODEL", "MEMORY_LLM_API_KEY"),
        "glm": ("GLM_BASE_URL", "GLM_MODEL", "GLM_KEY"),
        "deepseek": ("DEEPSEEK_API_BASE", "DEEPSEEK_MODEL", "DEEPSEEK_API_KEY")}
    for dest, source in zip(mappings["memory"], mappings[provider]):
        value = os.environ.get(source, "")
        if value:
            env[dest] = value
    if provider == "deepseek" and not env.get("MEMORY_LLM_MODEL"):
        env["MEMORY_LLM_MODEL"] = "deepseek-chat"
    return env


def record(ident, text, *, kind="new_content", scope="demo:user", **context):
    return {"id": ident, "material": {"schema_version": "1.0", "submission_id": ident, "library_id": "memory-demo", "kind": kind,
        "title": context.get("memory_title", "演示材料"), "content": {"format": "text", "text": text},
        "source": {"reference": "synthetic:memory-demo", "description": "合成示例，非真实用户信息"},
        "context": {"scope": scope, **context}}}


def samples():
    return [record("demo-preference", "在技术汇报中，我希望先给出结论，再给出必要的技术依据。", memory_type="feedback", memory_title="技术汇报偏好", memory_summary="技术汇报先讲结论，再给技术依据"),
            record("demo-project", "演示项目 Orion 的管理员界面采用明亮主题。这个约定只适用于 Orion。", scope="project:orion", memory_type="project", memory_title="Orion 界面约定", memory_summary="Orion 管理界面采用明亮主题"),
            record("demo-observation", "这次导入比昨天慢，但还没有确认原因。", kind="observation")]


def prepare(job, source, operation, records, mode):
    for name in ("input", "work", "output"):
        (job / name).mkdir(parents=True)
    shutil.copytree(source, job / "input/workspace")
    sha = hashlib.sha256((ROOT / "template/program.py").read_bytes()).hexdigest()
    tree_sha = hashlib.sha256(json.dumps([("program.py", sha)], ensure_ascii=False).encode()).hexdigest()
    req = {"protocol_version": "1.1", "job_id": job.name, "operation": operation, "library_id": "memory-demo",
        "base_version": program.workspace_digest(source), "template": {"id": "memory-files", "version": "0.1.0", "package_sha256": tree_sha},
        "config": {"mode": mode}, "knowledge_subpath": "knowledge", "workspace_key": "demo:memory", "source_version": None, "exclude_paths": []}
    program.write_json(job / "input/request.json", req)
    (job / "input/materials.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")


def execute(job, operation, env):
    subprocess.run([sys.executable, "-I", "-B", str(ROOT / "template/program.py"), operation,
        "--input", str(job / "input"), "--work", str(job / "work"), "--output", str(job / "output")],
        env=env, check=True, timeout=900)


def run_demo(mode, provider, output):
    root = output.resolve() / ("run-" + uuid.uuid4().hex[:10])
    empty = root / "empty"
    empty.mkdir(parents=True)
    (empty / "auxiliary.txt").write_text("preserve me", encoding="utf-8")
    env = model_env(provider)
    materials = samples()
    if mode == "llm":
        for rec in materials:
            rec["material"]["context"] = {"scope": rec["material"]["context"]["scope"]}
    source = empty
    for name, operation, records in (("initialize", "initialize", []), ("update", "update", materials)):
        job = root / name
        prepare(job, source, operation, records, mode)
        execute(job, operation, env)
        source = job / "output/workspace"
    state = program.read_json(source / program.META / "state.json")
    if mode == "structured":
        target = next(k for k, v in state["notes"].items() if v["type"] == "project")
        correction = record("demo-correction", "Orion 项目的界面主题现在改为跟随系统设置，不再固定为明亮主题。", kind="correction", scope="project:orion",
                            memory_action="revise", memory_target=target, memory_title="Orion 界面约定", memory_summary="Orion 主题跟随系统设置")
        job = root / "correction"
        prepare(job, source, "update", [correction], mode)
        execute(job, "update", env)
        source = job / "output/workspace"
    before = program.workspace_digest(source)
    job = root / "replay"
    prepare(job, source, "update", materials, mode)
    execute(job, "update", env)
    assert program.workspace_digest(job / "output/workspace") == before
    assert (source / "auxiliary.txt").read_text() == "preserve me"
    summary = {"candidate": str(source), "index": str(source / "knowledge/INDEX.md"), "mode": mode,
               "idempotent_replay": True, "auxiliary_preserved": True, "published": False}
    program.write_json(root / "summary.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["structured", "llm"], default="structured")
    parser.add_argument("--provider", choices=["memory", "glm", "deepseek"], default="memory")
    parser.add_argument("--output", type=Path, default=ROOT / "data/demo")
    args = parser.parse_args()
    print(json.dumps(run_demo(args.mode, args.provider, args.output), ensure_ascii=False, indent=2))
