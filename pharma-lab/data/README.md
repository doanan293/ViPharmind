# Data layout

```text
data/
├── sources/      original inputs: the formulary PDF, leaflets/ (manifest.json, urls/,
│                 html/<category>/<slug>.html), curation/, colloquial_mappings.json,
│                 term_glossary.json, vietnamese_valid_syllables.json
├── corpus/       rag-final/ (output of `pharma-lab build`) and formulary/ (the knowledge bundle
│                 that `pharma-agent corpus import` loads)
├── evaluation/   gold/ (evaluation set) and runs/<run>/ (run.json, candidates/,
│                 rerank/<model>/, reports/)
├── cache/        text_embeddings/<model>.jsonl, query_embeddings/<model>.jsonl,
│                 rerank_scores/<model>.jsonl, kaggle_profiles/<workload>/<model>.json
│                 local_profiles/<workload>/<model>.json
└── work/         scratch space: build workspace, locks, bundle-embed input, archive staging,
                  logs/rerank/<model>.log (appended by every `pharma-lab rerank`)
```

`<model>` is the model slug from the catalog, for example `qwen3_embedding_4b_q8_0`. File and folder names never contain hashes; digests and identities live inside `manifest.json` files and cache records.

## Archive versions

Kaggle numbers dataset versions 1, 2, 3… with no branches or tags, so each major version
of the code has its own private dataset, and each push is one dataset version whose
message names the git tag. `pharma-lab data push` writes to `<owner>/vipharmind-data-v2`;
`pharma-lab data pull --dataset SLUG --version N` restores any of them (the latest version
of `vipharmind-data-v2` without options).

| Dataset | Kaggle version | Git tag | Content |
| --- | ---: | --- | --- |
| `vipharmind-data-v1` | 1 | `v1.0.0` | SoICT 2026 submission: corpus, 10,000-question benchmark, golden set, all retrieval and end-to-end runs (archived 2026-09-23 at `bc6df6f`) |
| `vipharmind-data-v1` | 2 | `v1.1.0` | Camera-ready: version 1 plus the camera-ready runs, citation re-judgments, dev/test split and slices (packed at `camera-ready` `611ed08`: tag `v1.1.0` plus the dataset rename and the symbolic-link fix, which do not touch the report; 2,629 files) |
| `vipharmind-data-v2` | 1… | `v2.x` | v2 work, one version per tag |

### Closed datasets

The v1 line ended with the camera-ready paper, which cites its code at tag `v1.1.0` and
its data on Kaggle without a version number. `data push` refuses these datasets:

| Dataset | Visibility | State |
| --- | --- | --- |
| `vipharma-rag` | public, cited by the paper | frozen at version 3 (`v1.1.0`); a public v2 release gets a new dataset |
| `vipharmind-data-v1` | private | frozen at version 2 |
| `vipharmind-data` | private | legacy name of `vipharmind-data-v1` version 1 |

## What Git tracks

Git keeps only small files that are maintained by hand or quoted in the thesis report:

- everything in `sources/` except the PDF and the leaflet HTML;
- `manifest.json` and `validation_report.json` of the corpus artifacts;
- `run.json`, `manifest.json` and `report.md` of evaluation runs.

Everything else under `data/`, except `work/`, lives in a private Kaggle dataset and is stored and restored with `pharma-lab data push` and `pharma-lab data pull`, which check the sha256 of every part and every file:

```bash
uv run pharma-lab data push --kaggle-account acc1 --message "v2.1.0: rebuild evaluation runs"
uv run pharma-lab data pull --kaggle-account acc1
```

The first push after a fresh setup needs the owner's confirmation; pull refuses to overwrite files that differ from the archive unless `--force` is given. A push replaces the whole archive, so it refuses to run while files listed in the current archive are missing from `data/`; pull them first, or pass `--allow-removal` to drop them on purpose.

The working copy may keep only the final results: `run.json`, `metrics.jsonl` and `report.md` of each evaluation run, the end-to-end answers, judgments and reports, `evaluation/gold/`, the corpus and the sources. The intermediates (`cache/`, `candidates/candidates.jsonl` and `rerank/<model>/rerank_scores.jsonl` of each run) stay in the archive, and `pharma-lab data pull` restores them before any rescoring or rerun.

`work/` is never archived. `work/logs/rerank/<model>.log` records, with timestamps, the account and GPU quota of every Kaggle session, the kernel, progress and errors of each `pharma-lab rerank` run; it stays on the machine that ran the command and survives restarts.

## Leaflet source

`sources/leaflets/manifest.json` (schema `leaflet-source-v1`) is the only record of where the leaflet pages came from: the sitemap URL, the crawl date, the sha256 of the URL list, and the path, size, sha256 and source URL of every HTML file. It stays inside pharma-lab; the knowledge bundle names leaflets only by `leaflet:<category>:<slug>`. `pharma-lab build` refuses to run when a file no longer matches the manifest.
