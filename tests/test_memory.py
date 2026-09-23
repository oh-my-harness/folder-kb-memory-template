import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from demo import program as p, prepare, record, samples
from package import build


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "base"
        self.source.mkdir()
        (self.source / "auxiliary.txt").write_text("preserve")
        self.n = 0
        self.job([], "initialize")

    def job(self, records, operation="update", planner=None, req_edit=None):
        self.n += 1
        job = self.root / str(self.n)
        prepare(job, self.source, operation, records, "structured")
        if req_edit:
            req = p.read_json(job / "input/request.json")
            req_edit(req)
            p.write_json(job / "input/request.json", req)
        self.last_job = job
        before = p.workspace_digest(job / "input/workspace")
        result = p.run(operation, job / "input", job / "work", job / "output", planner)
        self.assertEqual(before, p.workspace_digest(job / "input/workspace"))
        self.source = job / "output/workspace"
        return result

    def notes(self):
        return p.read_json(self.source / p.META / "state.json")["notes"]

    def test_initialize_and_preserve(self):
        self.assertTrue((self.source / "knowledge/INDEX.md").exists())
        self.assertEqual((self.source / "auxiliary.txt").read_text(), "preserve")

    def test_memory_observation_and_replay(self):
        result = self.job(samples())
        self.assertEqual(len(self.notes()), 2)
        self.assertEqual(result["materials"][2]["outcome"], "partially_accepted")
        self.assertNotIn("导入", (self.source / "knowledge/INDEX.md").read_text(encoding="utf-8"))
        before = p.workspace_digest(self.source)
        self.job(samples(), planner=lambda *a: self.fail("Replay must not call model"))
        self.assertEqual(before, p.workspace_digest(self.source))

    def test_changed_payload_same_id_rejected(self):
        self.job(samples()[:1])
        changed = samples()[0]
        changed["material"]["content"]["text"] = "different"
        with self.assertRaisesRegex(p.Invalid, "reused"):
            self.job([changed])
        self.assertFalse((self.last_job / "output/result.json").exists())

    def test_same_fact_different_record_merges_sources(self):
        self.job(samples()[:1])
        rec = samples()[0]
        rec["id"] = "another"
        rec["material"]["submission_id"] = "another"
        self.job([rec])
        self.assertEqual(len(self.notes()), 1)
        self.assertEqual(len(next(iter(self.notes().values()))["sources"]), 2)

    def test_correction_keeps_audit(self):
        self.job(samples()[:1])
        target = next(iter(self.notes()))
        old = self.notes()[target]["body"]
        self.job([record("fix", "技术汇报先给详细依据，再给结论。", kind="correction", memory_action="revise", memory_target=target,
                         memory_title="汇报顺序", memory_summary="依据在先")])
        self.assertNotEqual(self.notes()[target]["body"], old)
        ledger = (self.source / p.META / "processed.jsonl").read_text(encoding="utf-8")
        self.assertIn(old, ledger)
        self.assertEqual(len(self.notes()[target]["sources"]), 2)

    def test_new_content_cannot_replace(self):
        self.job(samples()[:1])
        target = next(iter(self.notes()))
        with self.assertRaisesRegex(p.Invalid, "Only corrections"):
            self.job([record("fix", "new", memory_action="revise", memory_target=target, memory_title="title", memory_summary="summary")])

    def test_cross_scope_rejected(self):
        self.job(samples()[:1])
        target = next(iter(self.notes()))
        with self.assertRaisesRegex(p.Invalid, "another scope"):
            self.job([record("fix", "new", scope="someone-else", memory_action="duplicate", memory_target=target)])

    def test_duplicate_does_not_replace_body(self):
        self.job(samples()[:1])
        target = next(iter(self.notes()))
        old = self.notes()[target]["body"]
        self.job([record("dup", "same meaning", memory_action="duplicate", memory_target=target)])
        self.assertEqual(self.notes()[target]["body"], old)

    def test_merge_preserves_old_content(self):
        self.job(samples()[:1])
        target = next(iter(self.notes()))
        old = self.notes()[target]["body"]
        self.job([record("addition", "Use bullet points when useful.", memory_action="merge", memory_target=target)])
        self.assertTrue(self.notes()[target]["body"].startswith(old))

    def test_false_evidence_rejected(self):
        bad = lambda *a: [{"action": "defer", "reason": "uncertain", "evidence": ["not in source"]}]
        with self.assertRaisesRegex(p.Invalid, "not in source"):
            self.job(samples()[:1], planner=bad)

    def test_path_from_model_rejected(self):
        bad = lambda *a: [{"action": "defer", "reason": "uncertain", "evidence": ["技术汇报"], "path": "../escape"}]
        with self.assertRaisesRegex(p.Invalid, "fields"):
            self.job(samples()[:1], planner=bad)

    def test_external_edit_refused(self):
        (self.source / "knowledge/INDEX.md").write_text("human edited")
        with self.assertRaisesRegex(p.Invalid, "changed externally"):
            self.job([])

    def test_subpath_and_base_version_rejected(self):
        for sub in (".", "../outside", "metadata", "knowledge/../../oops"):
            with self.subTest(sub=sub), self.assertRaises(p.Invalid):
                self.job([], req_edit=lambda r: r.update(knowledge_subpath=sub))
        with self.assertRaisesRegex(p.Invalid, "base version"):
            self.job([], req_edit=lambda r: r.update(base_version="wrong"))

    def test_limits_no_silent_truncation(self):
        with self.assertRaisesRegex(p.Invalid, "count limit"):
            self.job(samples()[:2], req_edit=lambda r: r.update(config={"mode": "structured", "max_memories": 1}))
        self.assertFalse((self.last_job / "output/result.json").exists())

    def test_repeated_input_id_rejected(self):
        with self.assertRaisesRegex(p.Invalid, "Duplicate record"):
            self.job([samples()[0], samples()[0]])

    def test_wrong_library_rejected(self):
        rec = samples()[0]
        rec["material"]["library_id"] = "other"
        with self.assertRaisesRegex(p.Invalid, "library"):
            self.job([rec])

    def test_observation_never_calls_llm(self):
        self.job(samples()[2:], planner=lambda *a: self.fail("Observation must await review"))
        self.assertEqual(self.notes(), {})

    def test_excluded_paths_rejected(self):
        (self.source / ".env").write_text("SECRET=placeholder")
        with self.assertRaisesRegex(p.Invalid, "Excluded"):
            self.job([])

    def test_link_rejected(self):
        target = self.root / "external"
        target.write_text("outside")
        try:
            (self.source / "link").symlink_to(target)
        except OSError:
            self.skipTest("Host does not permit symlinks")
        with self.assertRaisesRegex(p.Invalid, "Links"):
            p.scan(self.source)


class ModelTests(unittest.TestCase):
    def server(self, responses):
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                calls.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                status, payload = responses[min(len(calls) - 1, len(responses) - 1)]
                self.send_response(status)
                self.end_headers()
                self.wfile.write(payload)
            def log_message(self, *a):
                pass
        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return "http://127.0.0.1:" + str(server.server_port) + "/v1", calls

    def test_http_json_and_retry(self):
        plan = {"decisions": [{"action": "skip", "reason": "transient", "evidence": []}]}
        payload = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(plan)}}]}).encode()
        url, calls = self.server([(429, b"busy"), (200, payload)])
        with patch.dict(os.environ, {"MEMORY_LLM_BASE_URL": url, "MEMORY_LLM_MODEL": "test", "MEMORY_LLM_API_KEY": "test-secret"}), patch.object(p.time, "sleep"):
            result = p.llm_plan(samples()[0]["material"], {}, "demo", p.config({}))
        self.assertEqual(result, plan["decisions"])
        self.assertEqual(len(calls), 2)
        self.assertNotIn("test-secret", json.dumps(calls))

    def test_invalid_json_fails_without_fallback(self):
        url, calls = self.server([(200, b"not json")])
        with patch.dict(os.environ, {"MEMORY_LLM_BASE_URL": url, "MEMORY_LLM_MODEL": "test"}):
            with self.assertRaisesRegex(p.Invalid, "invalid JSON"):
                p.llm_plan(samples()[0]["material"], {}, "demo", p.config({}))
        self.assertEqual(len(calls), 1)

    def test_http_error_redacts_body(self):
        url, _ = self.server([(401, b"secret and user text")])
        with patch.dict(os.environ, {"MEMORY_LLM_BASE_URL": url, "MEMORY_LLM_MODEL": "test"}):
            with self.assertRaisesRegex(p.Invalid, "LLM HTTP failure: 401") as caught:
                p.llm_plan(samples()[0]["material"], {}, "demo", p.config({}))
        self.assertNotIn("secret", str(caught.exception))

    def test_missing_model_fails(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(p.Invalid, "Set MEMORY"):
            p.llm_plan(samples()[0]["material"], {}, "demo", p.config({}))

    def test_package_reproducible(self):
        a, first = build()
        data = a.read_bytes()
        _, second = build()
        self.assertEqual(data, a.read_bytes())
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
