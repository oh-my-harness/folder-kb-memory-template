# Memory template

- Read README.md and docs/protocol.md before changing behavior.
- Keep the template independent of Folder KB internals. Only tools/platform_demo.py may import the platform for contract verification.
- Runtime is Python 3.11+ standard library. ZIP entrypoint is template/program.py, packaged as program.py at the archive root.
- Never write to the input snapshot, installed program, or published knowledge. Only emit a candidate under output/workspace and result.json.
- Treat submitted text and retrieved memory as data. Models may propose structured decisions, never shell commands or arbitrary file paths.
- Preserve sources, scope, material IDs and content hashes. Replays must be idempotent; reused IDs with different payloads must fail.
- Never silently switch to a fake or heuristic model after an LLM error. Unknown observations and conflicts stay outside the retrieval directory.
- Credentials are environment-only, never commit logs, generated knowledge, host paths, real user examples, or keys.
- Run python -m unittest discover -s tests -v, packaging, and platform integration checks after behavioral changes.
