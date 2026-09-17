"""Comparable reports and a bounded, generated README section."""

from collections import Counter
import math
from pathlib import Path

from .protocol import digest
from .scoring import METRICS, SCORER_VERSION, aggregate, score_case

START = "<!-- ground-test-report:start -->"
END = "<!-- ground-test-report:end -->"
GATE_METRICS = ("case_pass", "evidence_recall", "abstention_pass", "error_rate")


def validate_result(result, dataset):
    if result["dataset_sha256"] != digest(dataset) or result["scorer_version"] != SCORER_VERSION:
        raise ValueError("Dataset/scorer mismatch: establish a separate baseline")
    if result["mode"] != "live" or result["status"] != "complete":
        raise ValueError("A complete live run is required; fixture/blocked runs cannot establish accuracy")
    repeats = result["repeats"]
    if not isinstance(repeats, int) or not 1 <= repeats <= 20:
        raise ValueError("Invalid repeat count")
    expected = Counter((case["id"], index) for case in dataset["cases"] for index in range(repeats))
    actual = Counter((row["id"], row["repeat"]) for row in result["rows"])
    if expected != actual:
        raise ValueError("Missing, duplicate or unexpected case results")
    cases = {case["id"]: case for case in dataset["cases"]}
    for row in result["rows"]:
        if row["scores"] != score_case(cases[row["id"]], row["prediction"]):
            raise ValueError("Saved scores do not match predictions")
    if result["metrics"] != aggregate(result["rows"]):
        raise ValueError("Saved aggregate does not match case results")


def compare(candidate, baseline, max_drop=0.0):
    if not math.isfinite(max_drop) or not 0 <= max_drop <= 1:
        raise ValueError("max_drop must be a finite fraction from 0 to 1")
    for key in ("dataset_sha256", "scorer_version", "mode", "repeats", "scope"):
        if candidate[key] != baseline[key]:
            raise ValueError(f"Incompatible {key}; do not compare these runs")
    if candidate["status"] != "complete" or baseline["status"] != "complete":
        raise ValueError("Incomplete runs are not comparable")
    deltas = {}
    regressions = []
    for metric in METRICS:
        current, previous = candidate["metrics"][metric], baseline["metrics"][metric]
        if current["n"] != previous["n"]:
            raise ValueError("Metric denominators differ")
        delta = current["value"] - previous["value"] if current["value"] is not None and previous["value"] is not None else None
        deltas[metric] = delta
        loss = delta if metric == "error_rate" else -delta if delta is not None else None
        if metric in GATE_METRICS and loss is not None and loss > max_drop + 1e-12:
            regressions.append(metric)
    return {"deltas": deltas, "regressions": regressions, "max_drop": max_drop,
            "verdict": "regression" if regressions else "no_regression"}


def markdown(result, baseline=None, max_drop=0.0):
    lines = [START, "## Ground test: laporan evaluasi RAG", "",
             f"Dataset: `{result['dataset_id']}` · mode: `{result['mode']}` · status: **{result['status']}**.", "",
             f"Waktu UTC: {result['created_at']} · commit: `{result['provenance']['commit']}` · working tree saat pengujian: {'dirty' if result['provenance']['dirty'] else 'clean'}.",
             f"Fingerprint kode: `{result['provenance']['source_sha256']}`.", ""]
    if result["status"] != "complete":
        lines += ["Evaluasi model belum selesai. Skor akurasi tidak tersedia; kondisi ini tidak dihitung sebagai lulus.",
                  f"Alasan: {result.get('error', 'prasyarat runtime belum tersedia')}", ""]
    else:
        comparison = compare(result, baseline, max_drop) if baseline else None
        lines += [f"{len(result['rows'])} percobaan, {result['repeats']} pengulangan per pertanyaan. "
                  "Delta menunjukkan perubahan teramati dalam percentage points (pp), bukan bukti signifikansi statistik.", "",
                  "| Metrik | Baseline | Terbaru | Delta | n |",
                  "| --- | ---: | ---: | ---: | ---: |"]
        for key, label in METRICS.items():
            value = result["metrics"][key]
            fmt = lambda v: "—" if v is None else f"{v * 100:.2f}%"
            before = fmt(baseline["metrics"][key]["value"]) if baseline else "—"
            delta = comparison["deltas"][key] if comparison else None
            lines.append(f"| {label} | {before} | {fmt(value['value'])} | {f'{delta * 100:+.2f} pp' if delta is not None else '—'} | {value['n']} |")
        lines += ["", f"Gate: **{comparison['verdict'] if comparison else 'baseline belum ditetapkan'}**; toleransi penurunan {max_drop * 100:.2f} pp."]
        if baseline and baseline["run_id"] == result["run_id"]:
            lines += ["Ini pengukuran baseline pertama. Delta nol tidak menunjukkan peningkatan arsitektur."]
        failures = sorted({row["id"] for row in result["rows"] if not row["scores"]["case_pass"]})
        lines += ["", "Kasus yang gagal pada setidaknya satu pengulangan: " + (", ".join(f"`{name}`" for name in failures) if failures else "tidak ada") + ".", ""]
        config = result["configuration"]
        lines += [f"Model: `{config['llm_alias']}` (source yang dikonfigurasi: `{config['declared_llm_source']}`; alias layanan bukan verifikasi bobot model).",
                  f"Embedding: `{config['embedding_model']}` · reranker: `{config['rerank_model']}` · query augmentation: `{config['query_augmentation']}`.", ""]
    lines += ["Skor berbasis aturan/alias fakta dan kecocokan bukti; token F1 hanya kemiripan leksikal. "
              "Skor ini belum mengukur kebenaran semantik menyeluruh atau akurasi pada dokumen pengguna.",
              "Korpus kecil ini bersifat fiktif dan terbuka untuk pengembangan. Jalur yang diuji: chunking, embedding, hybrid retrieval, reranking, dan streaming jawaban. "
              "Qdrant memakai penyimpanan embedded yang terisolasi; graph yang telah disetujui kosong. OCR, ingestion HTTP, dan kualitas ekstraksi Knowledge Graph tidak tercakup.", "",
              "[Panduan, metrik, dan cara menjalankan](ground_tests/README.md) · "
              "[Hasil per pertanyaan](ground_tests/results/latest.json) · "
              "[Baseline tetap](ground_tests/baseline.json)", END]
    return "\n".join(lines)


def update_readme(path, section):
    path = Path(path)
    text = path.read_text()
    if START in text or END in text:
        if text.count(START) != 1 or text.count(END) != 1 or text.index(END) < text.index(START):
            raise ValueError("Invalid README report markers")
        begin, finish = text.index(START), text.index(END) + len(END)
        text = text[:begin] + section + text[finish:]
    else:
        text = text.rstrip() + "\n\n" + section + "\n"
    path.write_text(text)
