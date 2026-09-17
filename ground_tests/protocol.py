"""Dataset validation, provenance and reproducible comparison boundaries."""

import hashlib
import json
from pathlib import Path
import subprocess

from .scoring import contains

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "ground_tests/dataset.json"
SOURCE_DIRS = ("apps/app", "apps/rag", "apps/agents", "apps/knowledge", "ground_tests")


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def load_dataset(path=DEFAULT_DATASET):
    dataset = json.loads(Path(path).read_text())
    documents = dataset["documents"]
    cases = dataset["cases"]
    if not documents or not cases or not dataset.get("id"):
        raise ValueError("Dataset needs an ID, documents and cases")
    docs = {item["id"]: item["text"] for item in documents}
    if len(docs) != len(documents) or len({case["id"] for case in cases}) != len(cases):
        raise ValueError("Duplicate document/case IDs")
    for case in cases:
        if not case["question"].strip() or not case["reference"].strip():
            raise ValueError("Empty question/reference")
        if not case.get("unanswerable") and (not case["facts"] or not case["evidence"]):
            raise ValueError("Answerable cases need facts and source evidence")
        if case.get("unanswerable") and (case["facts"] or case["evidence"]):
            raise ValueError("Unanswerable cases cannot claim answer evidence")
        if any(not aliases or any(not alias.strip() for alias in aliases) for aliases in case["facts"]):
            raise ValueError("Empty fact aliases")
        for evidence in case["evidence"]:
            if not contains(docs[evidence["document_id"]], evidence["quote"]):
                raise ValueError(f"Evidence absent from source for {case['id']}")
    return dataset


def source_fingerprint():
    files = {}
    for directory in SOURCE_DIRS:
        for path in sorted((ROOT / directory).rglob("*.py")):
            files[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest(files)


def provenance():
    def git(*args):
        result = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None

    return {
        "commit": git("rev-parse", "HEAD"),
        "dirty": bool(git("status", "--porcelain")),
        "source_sha256": source_fingerprint(),
    }


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)
