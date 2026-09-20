# DiLLeMa

DiLLeMa is a distributed Large Language Model (LLM) serving system that provides an easy-to-use interface for deploying and using LLMs in distributed settings. Built on top of Ray Framework and VLLM, it enables efficient multi-GPU and multi-node deployments.

![Architecture](https://raw.githubusercontent.com/robbypambudi/DiLLeMa/refs/heads/main/docs/assets/architecture.png)

## Features

An opt-in Knowledge Graph pilot for DiLLeMa v2 is available in `apps/`. See the
[implementation plan and agent handoff](docs/DILLEMA_V2_PLAN.md),
[setup/runbook](docs/DILLEMA_V2_RUNBOOK.md),
[validation findings](docs/DILLEMA_V2_VALIDATION.md), and
[target architecture](docs/DILLEMA_V2_DESIGN.md).

- **Distributed LLM Serving**: Deploy LLMs across multiple GPUs and nodes using Ray and VLLM
- **Simple CLI Interface**: Easy-to-use command-line interface for managing Ray clusters and deploying models
- **OpenAI-Compatible API**: Standard OpenAI-compatible API endpoints for seamless integration
- **Tensor and Pipeline Parallelism**: Support for both tensor and pipeline parallelism for large models
- **Auto-scaling**: Automatic scaling of model replicas based on demand

## Installation

Requires [uv](https://docs.astral.sh/uv/).

### From PyPI

```bash
uv pip install dillema
```

### From Source

```bash
git clone https://github.com/robbypambudi/DiLLeMa.git
cd DiLLeMa
uv sync
```

Or run `./install.sh` to install uv (if missing), pin Python 3.12.9, and sync the environment.

After that, run commands with `uv run` (for example `uv run dillema --help`) or activate `.venv`:

```bash
source .venv/bin/activate
```

### With Docker

Build the GPU serving image (based on `rayproject/ray:2.55.0-py312-cu128`):

```bash
docker build -t dillema:2.55.0 .
docker run --gpus all --rm -it dillema:2.55.0 bash -lc \
  'ray start --head && dillema serve --model-id qwen-3.5-0.8b \
     --model-source Qwen/Qwen3.5-0.8B'
```

Requires the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html). See the header comment in the `Dockerfile` and `deploy/auth-proxy/` for securing the endpoint.

### Prerequisites

- Python 3.12.9
- CUDA-capable GPU(s) (for GPU acceleration)
- Ray 2.55.0
- VLLM 0.18.0

> **Note**: `uv sync` creates `.venv` with Python 3.12.9 (see `.python-version`). You do not need conda.

## Project Structure

```
DiLLeMa/
│
├── dillema/                    # Main package
│   ├── cli.py                  # CLI interface (head, worker, serve, stop commands)
│   └── serve/                  # LLM serving module
│       └── llm.py              # Ray Serve LLM wrapper
│
├── deploy/                     # Deployment helpers (e.g. auth-proxy for the endpoint)
├── evaluation/                 # Evaluation scripts and tools
├── analysis/                  # Analysis notebooks and scripts
├── docs/                      # Documentation and assets
├── test/                      # Unit tests
├── pyproject.toml             # Project configuration
└── uv.lock                    # Locked dependency versions
```

## Flow Diagram

```
  +------------------------+
  |      User/Client        |
  +------------------------+
            |
            v
  +------------------------+     +------------------------+
  |   API Server (Ray Serve)|<--->|   Ray Head Node        |
  |   OpenAI-Compatible API |     |   (Ray Management)     |
  +------------------------+     +------------------------+
            |                         ^
            v                         |
    +--------------------+    +--------------------+
    |  Ray Cluster       |----|  Ray Worker Nodes  |
    |  (Distributed)     |    |  (GPU Workers)     |
    +--------------------+    +--------------------+
            |
            v
  +------------------------+
  |  VLLM Engine           |
  |  (Model Inference)     |
  +------------------------+
            |
            v
  +------------------------+
  |  LLM Model             |
  |  (HuggingFace)         |
  +------------------------+
```

## Usage

If `.venv` is not activated, prefix commands with `uv run` (for example `uv run dillema serve ...`).

### Single Device Deployment

`dillema serve` reads `LLM_MODEL` and `LLM_MODEL_SOURCE` from the repository `.env` (copy `.env.example`; it is the single config file for the CLI, the dashboard API and the web app) and starts a local Ray head if needed. The web dashboard is a separate command (`dillema dashboard`).

```bash
uv run dillema serve
```

Add `-d` (or `--detach`) to return to the terminal immediately and keep running
in the background, including after the terminal closes:

```bash
uv run dillema serve -d
uv run dillema dashboard -d
# Equivalent dashboard command:
uv run dillema start dashboard -d
```

Each command prints its background PID and a `tail -f` command for its log in
`$XDG_STATE_HOME/dillema` (default: `~/.local/state/dillema`). Startup continues
asynchronously; check the log for readiness or errors. Stop the dashboard with
`dillema dashboard down` (it also stops the API/web processes it started; add
`--docker` to stop Postgres/Qdrant too, keeping their data). Use `kill <PID>` for
other background processes, and `dillema stop` to stop the Ray cluster and
deployed model.
Without `-d`, commands continue running in the foreground.

Or pass the model explicitly:

```bash
dillema serve \
  --model-id qwen-0.5b \
  --model-source Qwen/Qwen2.5-1.5B-Instruct
```

### Multi-Node Cluster Deployment

#### 1. Start Head Node

On the head node machine:

```bash
dillema head
# Output: Connect workers with: dillema worker --address='192.168.1.100:6379'
# Dashboard: http://192.168.1.100:8265
```

#### 2. Start Worker Nodes

On each worker machine:

```bash
dillema worker --address 192.168.1.100:6379
```

#### 3. Deploy Model

On any machine connected to the cluster:

```bash
dillema serve \
  --model-id qwen-0.5b \
  --model-source Qwen/Qwen2.5-0.5B-Instruct \
  --ray-address ray://192.168.1.100:10001 \
  --tensor-parallel 2 \
  --pipeline-parallel 2
```

#### 4. Stop Ray Cluster

```bash
dillema stop
```

### Command Options

#### `dillema head`
- `--port`: Ray port (default: 6379)
- `--dashboard-host`: Dashboard host (default: 0.0.0.0)

#### `dillema worker`
- `--address`: Head node address in format `ip:port` (required)

#### `dillema serve`
- `-d`, `--detach`: Run in the background with output saved to a log
- `--model-id`: Model identifier (default: `LLM_MODEL` in `.env`)
- `--model-source`: HuggingFace model path (default: `LLM_MODEL_SOURCE` or `TEXT_GENERATION_MODEL`)
- `--min-replicas`: Minimum replicas (default: 1)
- `--max-replicas`: Maximum replicas (default: 1)
- `--tensor-parallel`: Tensor parallel size (default: 1)
- `--pipeline-parallel`: Pipeline parallel size (default: 1)
- `--hf-token`: HuggingFace token for gated models
- `--ray-address`: Ray cluster address (default: auto)
- `--network-interface`: Network interface for distributed communication (e.g., eth0, enp132s0)
- `--app-host`: Application host address (default: 0.0.0.0)
- `--app-port`: Application port number (default: 8000)

#### `dillema dashboard [up|down]` / `dillema start dashboard`
- `up` (default): start the API and web UI; `down`: stop a running dashboard, foreground or `-d`
- `--docker`: With `down`, also stop the Postgres/Qdrant containers (data is kept)
- `-d`, `--detach`: Run the API and web UI in the background with output saved to a log
- `--api-host`: API host (default: 0.0.0.0)
- `--api-port`: API port (default: 8080)
- `--web-port`: Web UI port (default: 3000)
- `--no-docker`: Skip starting Postgres/Qdrant with Docker Compose

### Python API Usage

You can also use DiLLeMa programmatically:

```python
import ray
from ray import serve
from dillema.serve import LLMServe

ray.init()

wrapper = LLMServe(
    model_id="qwen-0.5b",
    model_source="Qwen/Qwen2.5-0.5B-Instruct",
    tensor_parallel_size=2,
    pipeline_parallel_size=1,
)

app = wrapper.build_app(
    min_replicas=1,
    max_replicas=2
)

serve.run(app, blocking=True)
```

## Architecture

DiLLeMa leverages Ray as the distributed orchestration framework and VLLM as the inference engine:

- **Ray**: Manages distributed resources, task scheduling, autoscaling, and fault tolerance
- **VLLM**: Optimizes LLM inference through dynamic batching, kernel fusion, and advanced memory management
- **Ray Serve**: Provides the serving layer with OpenAI-compatible API endpoints

The system supports three deployment configurations:
- **Single GPU**: Deploy models on a single GPU
- **Multi-GPU**: Deploy models across multiple GPUs using tensor parallelism
- **Multi-node Multi-GPU**: Deploy models across multiple nodes and GPUs using pipeline parallelism

## Evaluasi RAG: chunking, indeks, dan model kecil

Eksperimen lokal **18 September 2026** menguji tujuan DiLLeMa: memberikan bukti
yang tepat kepada LLM kecil. Hasilnya: pipeline saat ini menyediakan jawaban dari
sumber acuan pada **156/160 pertanyaan (97,5%)**, tetapi Qwen 0.5B hanya mencapai
**29/80 exact match (36,25%)**. Kualitas retrieval yang tinggi membantu model,
namun belum menjamin jawaban yang benar. Ini hasil pilot terukur, bukan klaim
kesiapan produksi.

### Data dan protokol

- Dataset publik: [TyDi QA](https://huggingface.co/datasets/google-research-datasets/tydiqa),
  `secondary_task/validation`, bahasa Indonesia, revisi
  `da78f23f9119363459acbaf46bf89426ff26c259`. Seluruh **565 pertanyaan / 514 konteks
  unik** dipakai untuk membentuk corpus. Dataset card mencantumkan Apache-2.0.
- Pertanyaan dibagi berdasarkan **judul artikel**, dengan seed `20260918`:
  **40 dev**, **160 test**, dan **80 pertanyaan pertama dari test** untuk generasi.
  Tidak ada konteks sumber bersama antara pertanyaan dev dan test. Corpus tetap
  mencakup semua 514 konteks; pertanyaan dan label jawaban tidak masuk indeks.
- Ini adaptasi retrieval atas kumpulan paragraf TyDi QA: satu konteks menjadi satu
  dokumen dengan satu halaman virtual. Bukan skor resmi TyDi QA, pencarian seluruh
  Wikipedia, atau evaluasi parsing PDF. Teks jawaban diverifikasi ada di sumber;
  offset anotasi tidak dipakai karena sebagian tidak cocok dengan slicing Unicode.
- Komponen aplikasi yang benar-benar dijalankan: `DocumentChunker`,
  `DefaultEmbedding`, encoder sparse, `QdrantHttpClient`, `ReRanking`, dan
  `RetrievalService`. Qdrant memakai **mode in-memory / pencarian exact**, tanpa
  database aplikasi. Kualitas HNSW, payload index server, serta latency jaringan
  tidak diuji.
- Embedding: [multilingual-e5-base](https://huggingface.co/intfloat/multilingual-e5-base),
  768 dimensi, prefix `query:` / `passage:` dan normalisasi L2. Reranker:
  [bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3).
  Pool 40 kandidat, 8 hasil rerank, skor minimum 0,05, ambang relatif 0,5,
  maksimal 4 sumber. Query augmentation dan Knowledge Graph dinonaktifkan agar
  kontribusi chunking/indexing dapat diperiksa.
- Generator: [Qwen2.5-0.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct),
  BF16, greedy decoding, maksimal 64 token, batch 8. Generasi memakai Transformers
  lokal dengan prompt jawaban ekstraktif yang sama antarkondisi; **bukan** prompt
  Markdown/sitasi dashboard atau uji serving Ray/vLLM. Tidak ada pemotongan input
  generator. Mesin: RTX 5090 32 GB, i7-12700, WSL2; PyTorch 2.8.0,
  Transformers 4.50.0, sentence-transformers 3.4.1, qdrant-client 1.15.1.

**Definisi metrik:** *answer hit* berarti setidaknya satu blok yang diberikan ke
generator berasal dari konteks acuan **dan** masih mengandung salah satu jawaban
anotasi. *Source precision* adalah proporsi blok keluaran dari konteks acuan,
dirata-ratakan per pertanyaan; ini proksi relevansi, bukan penilaian kebenaran
setiap klaim. Exact match dan token F1 memakai lowercase, normalisasi tanda baca
serta whitespace, dan jawaban anotasi terbaik. Tidak ada LLM-as-judge.

### Pengaruh chunking pada indeks

Ukuran/overlap berikut dalam **karakter**, bukan token. Baseline fixed memakai
recursive splitter tanpa enrichment judul; structured memakai chunker produksi
beserta judul dan aturan struktur. Semua baris memakai corpus dan model yang sama.

| Chunking | Jumlah chunk | Dense: answer hit@4 | Pipeline lengkap: answer hit | Source precision pipeline | Rata-rata karakter konteks pipeline |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fixed 800 / 120 | 634 | 96,88% | 95,00% | 88,59% | 625 |
| Structured 400 / 60 | 976 | 97,50% | 97,50% | 92,81% | 647 |
| **Structured 800 / 120 — konfigurasi saat ini** | **629** | **98,75%** | **97,50%** | **91,61%** | **638** |
| Structured 1600 / 240 | 527 | 98,75% | 97,50% | 91,93% | 631 |

Structured 400 menghasilkan sekitar **55% lebih banyak vector** dibanding 800,
tanpa kenaikan answer hit pipeline pada test. Structured 1600 menghasilkan
sekitar **16% lebih sedikit vector**, dengan answer hit pipeline yang sama;
hasil corpus paragraf pendek ini belum membuktikan 1600 lebih baik untuk dokumen
panjang. Tidak ada chunk pada eksperimen ini yang terpotong oleh batas embedding.
Pemilihan hanya dari dev, berdasarkan answer hit, reciprocal rank, lalu konteks
terpendek, memilih **structured 800/120 + parent packing**. Jadi eksperimen ini
tidak memberikan dasar kuat untuk mengganti default ukuran chunk.

### Pengaruh jenis indeks dan penyaringan

Ablasi berikut mempertahankan structured 800/120, dengan 160 pertanyaan test:

| Jalur | Answer hit di pool@40 | Answer hit keluaran | Source precision keluaran | Rata-rata karakter konteks |
| --- | ---: | ---: | ---: | ---: |
| Dense, top-4 leaf | 100,00% | 98,75% | 28,91% | 2.039 |
| Sparse saat ini, top-4 leaf | 96,88% | 93,13% | 26,25% | 2.300 |
| Dense + sparse RRF, top-4 leaf | 99,38% | 98,75% | 28,91% | 2.139 |
| Hybrid + reranker + ambang, top-4 leaf | 99,38% | 97,50% | 91,67% | 605 |
| **Pipeline saat ini: hybrid + reranker + parent packing** | **99,38%** | **97,50%** | **91,61%** | **638** |

Reranking/penyaringan menghasilkan konteks jauh lebih terfokus, dengan konsekuensi
kehilangan sebagian bukti: 159 pertanyaan memiliki jawaban di pool hybrid,
tetapi hanya 156 yang tetap memilikinya setelah pipeline. Hybrid RRF belum
meningkatkan answer hit@4 dibanding dense pada corpus ini. Simpan keduanya sebagai
baseline evaluasi, jangan menganggap hybrid selalu unggul.

### Apakah model sangat kecil terbantu?

Empat kondisi berikut memakai **80 pertanyaan yang sama**. Oracle memberikan
konteks acuan lengkap dan menjadi kontrol diagnostik; bukan sistem yang bisa
dipakai tanpa mengetahui sumber jawaban terlebih dahulu.

| Bukti untuk Qwen 0.5B | Answer hit konteks | Exact match | Token F1 | Rata-rata token input, termasuk prompt |
| --- | ---: | ---: | ---: | ---: |
| Tanpa RAG | — | 1,25% | 7,45% | 129 |
| Baseline fixed 800/120 + dense top-4 | 96,25% | 38,75% | 47,15% | 769 |
| **RAG saat ini / konfigurasi terpilih dari dev** | **97,50%** | **36,25%** | **47,29%** | **347** |
| Oracle: konteks acuan lengkap | 100,00% | 36,25% | 49,60% | 319 |

RAG saat ini meningkatkan exact match **35 poin persentase** dibanding tanpa
RAG; interval bootstrap berpasangan 95% adalah **+25 sampai +45 poin**.
Dibanding baseline dense, selisihnya **−2,5 poin**, dengan interval **−10 sampai
+3,75 poin**: belum ada bukti peningkatan akurasi. Kelebihan yang terlihat adalah
**54,8% lebih sedikit token input** dengan token F1 hampir sama. Interval bersifat
eksploratif: 10.000 resampling pertanyaan, bukan cluster artikel.

Dari 78 pertanyaan yang sudah menerima jawaban dalam konteks, **49 belum dijawab
dengan exact match**. Ini mencakup kesalahan isi maupun perbedaan bentuk jawaban,
bukan otomatis 49 halusinasi. Contoh kesalahan isi: pertanyaan presiden pertama
Nauru memiliki jawaban acuan `Hammer DeRoburt`, tetapi model memilih
`Bernard Dowiyogo` meskipun bukti acuan tersedia. Skor oracle memperkuat bahwa
kemampuan membaca bukti/prompt/model juga menjadi kendala. Model generator kecil
tidak berarti seluruh sistem kecil: embedding dan reranker tetap model terpisah.

Kontrol tambahan pada 20 pertanyaan memberikan konteks pengganggu dari hasil
dense setelah sumber acuan dan teks jawaban anotasi dikeluarkan, serta konteks
kosong. Dengan instruksi yang secara eksplisit melarang pengetahuan di luar bukti,
model menulis penolakan tepat `TIDAK DITEMUKAN` pada **3/20** dan **2/20** kasus.
Ini metrik kepatuhan format penolakan, **bukan tingkat halusinasi**: beberapa
penolakan memakai ejaan lain, dan ketiadaan string jawaban tidak membuktikan
ketiadaan semua kemungkinan jawaban semantik. Kontrol ini menguji generator,
bukan gate bukti kosong aplikasi. Lihat [respons kontrol mentah](evaluation/results/rag-tydiqa-id-20260918/missing-evidence.jsonl).

### Temuan integritas dan prioritas perbaikan

[Probe sintetis terpisah](evaluation/results/rag-tydiqa-id-20260918/integrity-probes.json)
menghasilkan temuan yang tidak bergantung pada skor TyDi QA:

1. **Bukti dari bagian berbeda dapat hilang.** Dua bagian dokumen tanpa nomor
   halaman menghasilkan dua retrieved chunks, tetapi `pack_parent_pages`
   menyisakan satu karena kuncinya sama-sama `(file_id, None, claim_id)`.
   Gunakan identitas parent/section yang stabil untuk Markdown, DOCX, dan teks.
2. **Parent yang dipotong dapat menghapus jawaban leaf.** Pada halaman sintetis
   6.678 karakter, jawaban di offset 6.646 ada di retrieved leaf, tetapi hilang
   setelah packing: parent dibatasi 5.000 karakter dan quote 350 karakter.
   Pertahankan seluruh span leaf yang cocok; perluas konteks di sekitarnya dalam
   anggaran token, bukan selalu mengambil awal halaman.
3. **Indeks bernama BM25 belum menerapkan BM25 lengkap.** `encode_sparse`
   menyimpan raw term frequency; Qdrant menambahkan IDF. Pengulangan satu istilah
   10 kali menghasilkan bobot 10 kali, tanpa saturasi TF dan normalisasi panjang
   dokumen. Bandingkan implementasi BM25 sebenarnya secara terkontrol sebelum
   menyimpulkan manfaat sparse/hybrid. [Referensi IDF Qdrant](https://qdrant.tech/documentation/concepts/indexing/#idf-modifier).
4. **Identitas konfigurasi indeks perlu eksplisit.** Simpan versi parser/chunker,
   revisi model embedding, dimensi, prefix, dan aturan sparse/stemming pada manifest
   collection. Pemeriksaan collection yang ada saat ini belum memvalidasi semua
   parameter tersebut. Reindex lewat staging lalu alihkan publikasi setelah siap;
   jalur retry saat ini menghapus points lama sebelum pengindeksan ulang selesai.
5. **Prioritaskan validasi bukti sebelum memperbesar model.** Pertahankan source ID,
   lokasi span, angka/satuan/negasi, dan provenance sampai prompt akhir. Tambahkan
   gate aplikasi untuk bukti kosong, validasi kutipan/angka, dan abstention terukur;
   prompt saja belum merupakan jaminan. Uji dokumen Indonesia nyata, tabel, OCR,
   pengecualian aturan, dan pertanyaan tanpa jawaban sebelum mengubah default.

Perbaikan di atas adalah **rekomendasi hasil evaluasi 18 September**; eksperimen
awal tidak mengubah pipeline produksi. Implementasi tahap pertama dicatat di
bawah. Batas lain: corpus kecil berisi paragraf yang sudah
memiliki anotasi jawaban; tidak mengukur validitas fakta dunia nyata, konflik
antardokumen, freshness, multi-hop, OCR/tabel, kualitas sitasi UI, atau skala indeks.
Skor ini tidak menjamin kualitas pada dokumen pengguna.

### Perbaikan integritas bukti — 20 September 2026

Tahap pertama sudah diimplementasikan di kode aplikasi:

- Parent packing mempertahankan **semua leaf hasil retrieval dari parent yang
  terpilih**, termasuk leaf yang ditemukan setelah batas empat parent tercapai.
  Konteks tambahan diambil di sekitar bukti, dengan anggaran lunak 5.000 karakter
  per parent; bukti tidak dipotong agar muat. Ini belum anggaran berbasis token.
- Identitas sumber memakai file ID, versi dokumen, dan parent/claim; bagian
  Markdown/DOCX tanpa halaman serta dua file bernama sama tidak lagi disatukan.
  Indeks lama tetap bisa dibaca dengan fallback identitas dan teks leaf.
- Chunk baru menyimpan `chunk_schema_version=evidence-v2`, `document_version`,
  `parent_id`, `section_id`, `chunk_id`, teks bukti lengkap, konteks header tabel,
  serta window parent. Versi adalah SHA-256 unit hasil parsing, bukan hash file
  asli. Offset `source_start`/`source_end` mengacu pada karakter Unicode unit
  setelah pembersihan (`cleaned_unit_unicode`), bukan koordinat PDF. Offset yang
  tidak dapat dicocokkan secara kontigu dibiarkan `null`.
- Jawaban tanpa penanda sumber valid tidak lagi diberi sumber pertama secara
  otomatis. Penomoran prompt dan sitasi memakai identitas yang sama; kutipan
  dipilih dari window terpisah agar tidak menggabungkan potongan berjauhan
  menjadi satu kutipan. Penanda `[Sn]` **belum membuktikan dukungan semantik**.
- Log `RAG evidence trace` mencatat ID pertanyaan/collection, jumlah kandidat,
  ID dan skor hasil rerank, serta versi/ID chunk yang masuk konteks. Trace ini
  tidak memuat teks pertanyaan atau dokumen dan membantu melacak bukti yang hilang.

Benchmark dijalankan ulang dengan dataset, split, model, dan konfigurasi yang
sama seperti eksperimen awal; file pemilihan pertanyaan identik.

| Pemeriksaan | Sebelum | Sesudah |
| --- | ---: | ---: |
| Dua bagian tanpa halaman tetap tersedia setelah packing | 1/2 | **2/2** |
| Jawaban pada offset 6.646 bertahan setelah packing | Tidak | **Ya** |
| TyDi QA: answer hit pipeline, 160 pertanyaan | 97,50% | 97,50% |
| Qwen 0.5B: exact match, 80 pertanyaan | 36,25% | 36,25% |
| Qwen 0.5B: token F1 | 47,29% | 47,29% |
| Rata-rata token input Qwen | 347,475 | 347,475 |

Hasil ini menunjukkan perbaikan pada kasus kehilangan bukti tanpa penurunan
metrik benchmark, **belum peningkatan akurasi umum**. Paragraf pendek TyDi QA
jarang memicu dua bug tersebut. Benchmark generasi tetap memakai prompt
ekstraktif, bukan alur sitasi dashboard. Suite aplikasi menjalankan 176 tes:
**144 lulus, 32 dilewati**, termasuk regresi provenance, tabel, packing, dan
sitasi. Sebanyak 32 tes integrasi PostgreSQL dilewati karena database uji khusus
belum dikonfigurasi; bagian tersebut belum diverifikasi pada putaran ini.

[Ringkasan benchmark ulang](evaluation/results/rag-evidence-fix-20260920/summary.json),
[hasil retrieval](evaluation/results/rag-evidence-fix-20260920/retrieval.jsonl),
[jawaban mentah](evaluation/results/rag-evidence-fix-20260920/generation.jsonl),
[probe integritas](evaluation/results/rag-evidence-fix-20260920/integrity-probes.json),
[analisis](evaluation/results/rag-evidence-fix-20260920/analysis.json), dan
[fingerprint kode akhir](evaluation/results/rag-evidence-fix-20260920/source-manifest.json)
tersedia untuk diperiksa. Fingerprint mencakup penyempurnaan metadata kutipan
setelah benchmark; penyempurnaan itu tidak mengubah teks konteks benchmark.

**Penerapan:** restart aplikasi dengan kode baru untuk memakai packing/sitasi
baru. Dokumen lama perlu **diindeks ulang** untuk mendapatkan metadata v2,
window, dan offset lengkap. Uji dahulu pada collection terpisah dengan dokumen
produksi yang diketahui bermasalah; bandingkan bukti, sitasi, dan jawaban sebelum
memindahkan pemakaian. Tidak ada deployment atau reindex produksi yang dilakukan
dalam eksperimen ini. Normalisasi BM25, manifest konfigurasi indeks lengkap,
parsing layout/OCR, serta verifikasi semantik/abstention tetap pekerjaan berikutnya.

### Evaluasi template prompt — 20 September 2026

Prompt jawaban kini memakai versi `grounded-answer-2` dan perluasan query memakai
`query-rewrite-2`. Prompt lama memaksa daftar, meminta sitasi hanya di butir,
dan belum secara eksplisit menjaga negasi, pengecualian, atau lingkup waktu.
Template baru meminta jawaban langsung, sitasi pada setiap kalimat faktual,
pemeliharaan syarat/angka/negasi, penjelasan konflik, dan penolakan ketika jawaban
tidak ada. Tiga contoh fiktif menunjukkan format jawaban dan penolakan; contoh
terpisah dari pesan bukti terakhir.

Bukti dibungkus dalam elemen sumber berlabel dengan delimiter yang di-escape.
Nama file dan nomor halaman tetap tersedia untuk sitasi aplikasi, tetapi tidak
lagi menambah teks input generator; bagian dokumen tetap disertakan sebagai
konteks. Sumber tanpa nama juga mendapat label tersendiri agar tidak berbenturan
dengan sumber lain. Ini pemisahan data, bukan jaminan keamanan terhadap instruksi
dalam dokumen. Prompt query meminta nama, kode, tahun, negasi, dan batasan tetap
dipertahankan; query asli tetap menjadi pencarian pertama. Prompt ekstraksi
Knowledge Graph ditinjau dan dipertahankan beserta kewajiban review klaimnya.

Perbandingan memakai Qwen2.5-0.5B-Instruct lokal, BF16, greedy decoding:
**10 kasus pengembangan jawaban, 6 kasus tambahan yang tidak dipakai untuk
penyempurnaan, dan 4 kasus rewrite**, masing-masing dijalankan sebelum/sesudah.
Input, keluaran, serta parameter disimpan. Dua rancangan JSON dan satu iterasi
awal delimiter dipertahankan sebagai artefak; versi panjang sempat membuat model
menyalin struktur input. Hasil berikut menggabungkan kasus pengembangan dan
tambahan, sehingga **bukan estimasi akurasi pada data independen**.

| Pemeriksaan | Prompt lama | Prompt akhir |
| --- | ---: | ---: |
| Himpunan label sitasi sesuai harapan, 16 kasus | 4/16 | 11/16 |
| Menolak empat kasus tanpa jawaban, dari pemeriksaan keluaran mentah | 0/4 | 4/4 |
| Rewrite mempertahankan kode/tahun yang diperiksa | 4/4 | 4/4 |
| Rata-rata token input jawaban pada fixture | 356 | 660 |

**Batas yang ditemukan:** label benar bukan bukti jawaban benar. Model masih
membalik larangan peserta nonaktif, tidak menjelaskan konflik dua biaya, dan
meniru label palsu `[S999]`/`[S88]` dari teks dokumen. Pada kasus larangan tambahan,
model malah mengulang pertanyaan. Rewrite juga masih salah menerjemahkan
pengecualian biaya menjadi *penalty* serta kehilangan syarat `belum lulus`.
Prompt baru belum menyelesaikan kegagalan tersebut. Aplikasi tidak menambahkan
referensi untuk label yang tidak valid, tetapi itu belum memverifikasi isi
jawaban atau menghapus penanda palsu dari teks generasi.

Percobaan ini menguji penyusunan pesan aplikasi, tanpa retrieval; pengaturan
sampling/streaming server produksi tidak diuji. Kontrol bukti kosong menguji
model langsung; aplikasi tetap memiliki jalur penolakan tanpa generasi untuk
retrieval kosong. Suite aplikasi: **147 tes lulus, 32 tes PostgreSQL dilewati**
karena database uji khusus belum dikonfigurasi. Tidak dilakukan deployment.
Perubahan prompt cukup diaktifkan dengan restart aplikasi, tanpa reindex.

[Template sebelum](evaluation/results/prompt-review-20260920/templates-before.json),
[template akhir](evaluation/results/prompt-review-20260920/templates-after.json),
[respons lengkap](evaluation/results/prompt-review-20260920/responses.jsonl), dan
[ringkasan pemeriksaan](evaluation/results/prompt-review-20260920/summary.json)
dapat diperiksa. Untuk mengulang dengan cache model eksperimen sebelumnya:

```bash
mkdir -p evaluation/results/prompt-review-rerun
cp evaluation/results/prompt-review-20260920/templates-before.json evaluation/results/prompt-review-rerun/
apps/.venv/bin/python -u apps/evaluation/prompt_eval.py --out evaluation/results/prompt-review-rerun
```

### Artefak dan pengulangan eksperimen

[Ringkasan lengkap](evaluation/results/rag-tydiqa-id-20260918/summary.json),
[hasil retrieval per pertanyaan](evaluation/results/rag-tydiqa-id-20260918/retrieval.jsonl),
[jawaban model mentah](evaluation/results/rag-tydiqa-id-20260918/generation.jsonl),
[pembagian dev/test](evaluation/results/rag-tydiqa-id-20260918/selection.json),
[interval/perbandingan](evaluation/results/rag-tydiqa-id-20260918/analysis.json), dan
[fingerprint kode](evaluation/results/rag-tydiqa-id-20260918/source-manifest.json)
disimpan di repo. Kondisi `dev_selected` pada artefak generasi sama dengan
`current_production`, sehingga bukan replikasi independen. Ada satu variasi
ejaan penolakan antarbatches BF16; skor EM/F1 kedua kondisi sama.
Artefak `missing-evidence-conditional-prompt*` menyimpan percobaan awal dengan
prompt yang mengizinkan pengetahuan internal bila bukti tidak diberikan;
angka kontrol di atas memakai percobaan berikutnya dengan larangan eksplisit.

Dari root repo, setelah `uv sync --directory apps` dan GPU CUDA tersedia:

```bash
mkdir -p /tmp/dillema-rag-eval
curl -fL 'https://huggingface.co/datasets/google-research-datasets/tydiqa/resolve/da78f23f9119363459acbaf46bf89426ff26c259/secondary_task/validation-00000-of-00001.parquet' \
  -o /tmp/dillema-rag-eval/validation.parquet

uv run --directory apps huggingface-cli download intfloat/multilingual-e5-base --revision d128750597153bb5987e10b1c3493a34e5a4502a
uv run --directory apps huggingface-cli download BAAI/bge-reranker-v2-m3 --revision 953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e
uv run --directory apps huggingface-cli download Qwen/Qwen2.5-0.5B-Instruct --revision 7ae557604adf67be50417f59c2c2f167def9a775

uv run --directory apps python evaluation/public_rag_eval.py \
  --dataset /tmp/dillema-rag-eval/validation.parquet \
  --out ../evaluation/results/rag-tydiqa-id-rerun
uv run --directory apps python evaluation/rag_integrity_probes.py \
  --out ../evaluation/results/rag-tydiqa-id-rerun/integrity-probes.json
uv run --directory apps python evaluation/public_rag_controls.py \
  --dataset /tmp/dillema-rag-eval/validation.parquet \
  --results ../evaluation/results/rag-tydiqa-id-rerun
uv run --directory apps python evaluation/summarize_public_rag.py \
  --results ../evaluation/results/rag-tydiqa-id-rerun
```

Model dibaca dari cache lokal pada revisi di atas; dataset SHA-256, versi library,
dan parameter disimpan dalam hasil. Waktu indexing mentah pada JSON **tidak layak
dibandingkan sebagai benchmark**: konfigurasi pertama membayar inisialisasi/cache
stemming, konfigurasi berikutnya memakai cache yang sudah hangat. Revisi benchmark
berikutnya perlu isolasi cold/warm run dan ulangan terpisah untuk mengukur performa.

## Documentation

For detailed documentation, see [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md)

For CLI usage examples, see [CLI_USAGE.md](CLI_USAGE.md)

## License

MIT License - see [LICENSE](LICENSE) file for details

## Authors

- Robby Ulung Pambudi (robby.pambudi10@gmail.com)
