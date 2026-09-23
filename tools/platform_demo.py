"""Verify the installed ZIP against a disposable Folder KB instance."""
import argparse
import json
from pathlib import Path
import sys
import uuid

from demo import samples
from package import ROOT, build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform-source", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.platform_source.resolve()))
    from folder_kb.management import Registry
    from folder_kb.templates import TemplateCatalog, TemplateRegistration, TemplateBinding
    from folder_kb.workspaces import WorkspaceSpec, workspace_digest
    from folder_kb.template_protocol import JobRequest, Record, TemplateRef, prepare_job, run_reference
    from folder_kb.inbox import Inbox, Material

    root = ROOT / "data/platform-demo" / ("run-" + uuid.uuid4().hex[:10])
    workspace = root / "libraries/memory-demo"
    (workspace / "knowledge").mkdir(parents=True)
    (workspace / "auxiliary.txt").write_text("keep this", encoding="utf-8")
    registry = Registry(str(root / "libraries"), str(root / "state"))
    registry.save_library("memory-demo", "合成记忆演示", "memory-demo/knowledge", True, create=True)
    archive, definition = build()
    catalog = TemplateCatalog(registry)
    catalog.register(TemplateRegistration.model_validate(definition))
    installed = catalog.install(definition["id"], definition["version"], archive.read_bytes())
    template = TemplateRef(id=definition["id"], version=definition["version"], package_sha256=installed["package_sha256"])
    catalog.bind("memory-demo", TemplateBinding(template_id=template.id, template_version=template.version, config={"mode": "structured"},
        workspace=WorkspaceSpec(type="local", root_path="memory-demo", knowledge_subpath="knowledge")))
    scope = catalog.snapshot_source("memory-demo")
    package = root / "state/templates" / template.id / template.version / "package"
    req = JobRequest(job_id="initialize", operation="initialize", library_id="memory-demo", template=template,
        base_version=workspace_digest(workspace), knowledge_subpath="knowledge", workspace_key=scope["workspace_key"], config={"mode": "structured"})
    job = root / "initialize"
    prepare_job(job, req, [], workspace)
    run_reference(job, req, [], package)
    source = job / "output/workspace"
    inbox = Inbox(registry)
    key = registry.create_key("synthetic-test", ["memory-demo"], None)
    inbox.grants(key["key"]["id"], ["memory-demo"])
    records = []
    for sample in samples():
        mat = Material.model_validate(sample["material"])
        receipt = inbox.submit(key["token"], mat)
        records.append(Record(id=receipt["id"], material=mat))
    req = req.model_copy(update={"job_id": "update", "operation": "update", "base_version": workspace_digest(source)})
    job = root / "update"
    before = workspace_digest(source)
    prepare_job(job, req, records, source)
    result = run_reference(job, req, records, package)
    assert before == workspace_digest(source)
    assert (job / "output/workspace/auxiliary.txt").read_text() == "keep this"
    print(json.dumps({"template_installed_and_bound": True, "inbox_records": len(records), "validated": True,
        "input_unchanged": True, "published": False, "candidate": str(job / "output/workspace"),
        "outcomes": [m.outcome for m in result.materials]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
