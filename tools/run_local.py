"""Prepare and run one reviewed local job; output remains a candidate."""
import argparse
import json
from pathlib import Path

from demo import prepare, execute, model_env, program


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["initialize", "update"])
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--job", type=Path, required=True, help="New job directory outside the input workspace")
    parser.add_argument("--library-id", required=True)
    parser.add_argument("--materials", type=Path)
    parser.add_argument("--knowledge-subpath", default="knowledge")
    parser.add_argument("--mode", choices=["llm", "structured"], default="llm")
    parser.add_argument("--provider", choices=["memory", "glm", "deepseek"], default="memory")
    args = parser.parse_args()
    source, job = args.workspace.absolute(), args.job.absolute()
    for path in (source, job):
        for parent in (path, *path.parents):
            if parent.exists():
                program.regular(parent)
    source, job = source.resolve(), job.resolve()
    if job.exists() or job.is_relative_to(source) or source.is_relative_to(job):
        parser.error("Use a fresh job directory outside the workspace")
    program.scan(source)
    if args.operation == "update" and not args.materials:
        parser.error("Update requires --materials")
    if args.operation == "initialize" and args.materials:
        parser.error("Initialize does not consume materials")
    records = []
    if args.materials:
        if args.materials.stat().st_size > 8 * 1024 * 1024:
            parser.error("Materials exceed limit")
        records = [json.loads(line) for line in args.materials.read_text(encoding="utf-8").splitlines() if line.strip()]
    prepare(job, source, args.operation, records, args.mode)
    req = program.read_json(job / "input/request.json")
    req.update(library_id=args.library_id, knowledge_subpath=args.knowledge_subpath, workspace_key="local:" + args.library_id)
    program.write_json(job / "input/request.json", req)
    execute(job, args.operation, model_env(args.provider))
    print(json.dumps({"candidate": str(job / "output/workspace"), "result": str(job / "output/result.json"), "published": False}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
