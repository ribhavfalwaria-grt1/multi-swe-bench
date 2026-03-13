# collect

Data collection pipeline for Multi-SWE-bench. Scrapes merged PRs from GitHub repositories, extracts patches, resolves linked issues, and produces JSONL datasets. Two modes are supported: **SWE** (single-PR tasks from the original Multi-SWE-bench workflow) and **LHT** (Long Horizon Tasks that bundle multiple PRs between version tags into composite tasks).

The LHT pipeline uses a **multi-layered version diff strategy** to correctly handle semver parsing, parallel release branches, pre-release filtering, git ancestry verification, and multi-tier PR attribution — producing accurate "which PRs belong to version X → Y?" answers across diverse repo structures.

## Prerequisites

- Python >= 3.10
- Install from project root:
  ```bash
  cd multi-swe-bench && pip install -e .
  ```
  Or simply `make install`. Dependencies (PyGithub, unidiff, tqdm, requests, **packaging**) are pulled in automatically.
- Git must be on `PATH`. Used for ancestry verification, merge-log PR extraction, and clone-based diff fallback when GitHub's compare API can't return a full diff.
- One or more GitHub Personal Access Tokens (PATs). Classic tokens with `repo` scope work fine.

## Token Setup

Tokens can be provided three ways (auto-detected in order):

1. **CLI argument.** Pass them directly:
   ```bash
   --tokens ghp_xxx ghp_yyy ghp_zzz
   ```

2. **`.env` file.** Place a `.env` file in (or above) the working directory with:
   ```
   GITHUB_TOKEN=ghp_xxx
   ```
   The pipeline's `util.get_tokens()` walks up from `cwd` to find `.env` files automatically.

3. **Token file.** A file called `tokens`, `tokens.txt`, `token`, or `token.txt` in the working directory, one token per line.

Multiple tokens enable round-robin rotation, which significantly increases API throughput before you hit rate limits.

## Pipeline Modes

### SWE Mode (default)

Five-step pipeline:

1. **`get_all_prs`** — Fetch all PRs via PyGithub.
2. **`filter_prs`** — Keep closed PRs that resolve at least one issue.
3. **`get_related_issues`** — Fetch issue details for resolved issues.
4. **`merge_prs_with_issues`** — Join PRs with their resolved issue data.
5. **`build_dataset`** — Download diffs via the compare API, split into `fix_patch` / `test_patch`.

Output: `{org}__{repo}_raw_dataset.jsonl`

### LHT Mode — Multi-Layered Version Diff Strategy

Six-step pipeline with a 4-layer strategy for accurate version-range PR attribution:

1. **`get_all_prs`** — Fetch all PRs via PyGithub.
2. **`filter_prs --mode lht`** — Keep all merged PRs. No issue requirement, skips commit message fetching.
3. **`get_version_tags`** — Smart tag parsing & classification (Layer 1).
4. **`group_prs_by_tags`** — Ancestry verification, release-line grouping, and tiered PR attribution (Layers 2–4).
5. **`get_related_issues`** — Fetch issue details referenced by grouped PRs.
6. **`build_lht_dataset`** — Unified diff between tag SHAs (GitHub API with clone-based fallback for large diffs), split into `fix_patch` / `test_patch`, aggregate resolved issues.

Output: `{org}__{repo}_lht_dataset.jsonl`

#### Layer 1 — Smart Tag Parsing & Classification (`get_version_tags.py`)

Tags are parsed into three schemes with full metadata:

| Scheme | Examples | What's Extracted |
|--------|----------|-----------------|
| **semver** | `v1.2.3`, `v2.0.0-rc.1` | major, minor, patch, pre-release label |
| **calver** | `2024.01`, `2024.01.15`, `24.1` | year, month, day, micro |
| **unknown** | anything else | best-effort pre-release detection |

Each tag gets:
- `scheme` — detected versioning scheme
- `release_line` — grouping key (e.g., `1.2` for semver, `2024.01` for calver)
- `is_pre_release` — flag (alpha, beta, rc, dev, etc.)
- `sort_key` — tuple for correct cross-scheme comparison: `(0, major, minor, patch, pre)` for semver, `(1, year, month, ...)` for calver, `(2, ...)` for unknown

Tags are sorted by **version order** (not date), preventing misorderings from backport releases.

#### Layer 2 — Git Ancestry Verification (`group_prs_by_tags.py`)

Before pairing consecutive tags, the pipeline verifies that the base tag is a git ancestor of the head tag using `git merge-base --is-ancestor`. This catches:
- Parallel branches being incorrectly paired
- Imported sub-project tags (e.g., `dask-expr` tags in the `dask` repo)
- Rebased or force-pushed tags

Requires a bare clone (auto-cached in `.repo_cache/`).

#### Layer 3 — Branch-Aware Release-Line Grouping

- Pre-release tags are filtered out (unless only pre-releases exist for a line)
- Tags are grouped by release line (`major.minor`)
- Within each group, tags are sorted by semver (not chronologically)
- Only consecutive tags that pass the ancestry check form valid pairs
- Cross-line bridging pairs connect the last tag of one release line to the first of the next

#### Layer 4 — Tiered PR Attribution

PRs are attributed to version ranges using four methods in priority order:

| Priority | Method | Description |
|----------|--------|-------------|
| 1st | `git log --merges --first-parent` | Extracts PR numbers from merge commit messages between base..head. **No 250-commit cap.** Highest accuracy. |
| 2nd | GitHub Compare API | SHA matching — maps commit SHAs from the compare API to known PR merge SHAs. Subject to GitHub's 250-commit cap. |
| 3rd | Cherry-pick detection | `git cherry` identifies commits cherry-picked between branches (shares patch-id but different SHA). |
| 4th | Date-range fallback | Assigns PRs whose `merged_at` falls between tag dates. **Only used when compare API returned zero commits**, preventing wrong attribution on sub-project tags. |

Each bundle records which methods were used via the `attribution_methods` field.

## Quick Start

**SWE mode:**

```bash
python -m multi_swe_bench.collect.get_pipeline \
  --mode swe \
  --out_dir ./output \
  --org pallets \
  --repo flask \
  --tokens ghp_xxx ghp_yyy
```

**LHT mode:**

```bash
python -m multi_swe_bench.collect.get_pipeline \
  --mode lht \
  --out_dir ./output \
  --org pallets \
  --repo flask \
  --tokens ghp_xxx ghp_yyy \
  --max-tags 200
```

**LHT mode (skip PR fetch if already downloaded):**

```bash
python -m multi_swe_bench.collect.get_lht_pipeline \
  --out_dir ./output \
  --org pallets \
  --repo flask \
  --tokens ghp_xxx ghp_yyy \
  --skip-pr-fetch
```

**Using `.env` for tokens (no `--tokens` flag needed):**

```bash
# .env file contains GITHUB_TOKEN=ghp_xxx
python -m multi_swe_bench.collect.get_pipeline \
  --mode lht \
  --out_dir ../collect_lht_output \
  --org cli \
  --repo cli
```

## CLI Reference

All arguments for `get_pipeline`:

| Argument | Type | Default | Description |
|---|---|---|---|
| `--out_dir` | Path | required | Output directory |
| `--org` | str | required | GitHub organization |
| `--repo` | str | required | Repository name |
| `--tokens` | str[] | auto-detect | GitHub PAT(s) |
| `--mode` | swe\|lht | swe | Pipeline mode |
| `--delay-on-error` | int\|none | 300 | Retry delay in seconds |
| `--retry-attempts` | int | 3 | Max retry attempts |
| `--skip-commit-message` | bool | False | [SWE] Skip fetching commit messages |
| `--max-tags` | int | 200 | [LHT] Max version tags to fetch |
| `--window-days` | int | 30 | [LHT] Fallback time-window size |
| `--cache-dir` | str | .repo_cache | [LHT] Bare clone cache directory |
| `--lang` | str | python | [LHT] Programming language of the repo |
| `--skip-pr-fetch` | bool | False | [LHT] Skip step 1 if PRs already fetched (use `get_lht_pipeline` directly) |

## Batch Processing

`get_from_repos_pipeline.py` processes multiple repositories from a CSV file. The CSV must have a `Name` column with `org/repo` entries.

```bash
python -m multi_swe_bench.collect.get_from_repos_pipeline \
  --csv_file repos.csv \
  --out_dir ./output \
  --tokens ghp_xxx ghp_yyy \
  --distribute round
```

The `--distribute round` flag distributes repos across available tokens in round-robin fashion.

## Output Format

### SWE record

```json
{
  "instance_id": "pallets__flask-5001",
  "org": "pallets",
  "repo": "flask",
  "number": 5001,
  "title": "Fix session handling",
  "body": "...",
  "base": {"label": "main", "ref": "main", "sha": "abc123"},
  "resolved_issues": [{"number": 4999, "title": "Session bug", "body": "..."}],
  "fix_patch": "diff --git ...",
  "test_patch": "diff --git ..."
}
```

### LHT record

```json
{
  "instance_id": "pallets__flask-501-502-503",
  "org": "pallets",
  "repo": "flask",
  "number": "501-502-503",
  "base": {"label": "2.3.0..2.3.1", "ref": "main", "sha": "abc123"},
  "resolved_issues": [
    {"number": 499, "title": "Fix cookie handling", "body": "..."},
    {"number": 500, "title": "Update session docs", "body": "..."}
  ],
  "fix_patch": "diff --git ...",
  "test_patch": "diff --git ...",
  "prs_in_bundle": [501, 502, 503],
  "release_line": "2.3",
  "attribution_methods": {"git_log_merge": 2, "compare_api": 1}
}
```

The `release_line` and `attribution_methods` fields are added by the new multi-layered strategy and can be used for downstream quality analysis.

## Intermediate Files

Every pipeline step writes its output to disk so you can resume or inspect partial runs.

| File | Produced By | Description |
|---|---|---|
| `{org}__{repo}_prs.jsonl` | get_all_prs | All PRs (raw) |
| `{org}__{repo}_filtered_prs.jsonl` | filter_prs (swe) | PRs with resolved issues |
| `{org}__{repo}_lht_filtered_prs.jsonl` | filter_prs (lht) | All merged PRs |
| `{org}__{repo}_related_issues.jsonl` | get_related_issues | Issue details |
| `{org}__{repo}_filtered_prs_with_issues.jsonl` | merge_prs_with_issues | [SWE] PRs + issue data |
| `{org}__{repo}_tags.jsonl` | get_version_tags | [LHT] Version tags with scheme, release_line, sort_key |
| `{org}__{repo}_tag_groups.jsonl` | group_prs_by_tags | [LHT] PR groupings with attribution_methods |
| `{org}__{repo}_raw_dataset.jsonl` | build_dataset | [SWE] Final dataset |
| `{org}__{repo}_lht_dataset.jsonl` | build_lht_dataset | [LHT] Final dataset |

## Module Reference

| Module | Description |
|---|---|
| `get_pipeline.py` | Main entry point, dispatches to SWE or LHT pipeline |
| `get_lht_pipeline.py` | LHT pipeline orchestrator (6 steps) |
| `get_all_prs.py` | Fetches all PRs from a repo via PyGithub |
| `filter_prs.py` | Filters PRs by mode (SWE: needs resolved issues, LHT: all merged) |
| `get_version_tags.py` | **Layer 1**: Smart tag parsing — semver/calver/unknown detection, release-line classification, pre-release flagging, version-order sorting |
| `group_prs_by_tags.py` | **Layers 2–4**: Git ancestry verification, branch-aware release-line grouping, 4-tier PR attribution (git log merges → compare API → cherry-pick → date fallback) |
| `get_related_issues.py` | Fetches issue details by number |
| `merge_prs_with_issues.py` | Joins filtered PRs with issue data (SWE only) |
| `build_dataset.py` | Builds SWE dataset with per-PR diffs |
| `build_lht_dataset.py` | Builds LHT dataset with unified tag-range diffs, clone-based fallback for large diffs, `release_line` and `attribution_methods` fields |
| `get_from_repos_pipeline.py` | Batch processor for multiple repos from CSV |
| `crawl_repos.py` | GitHub repo discovery by language/stars |
| `util.py` | Token parsing (auto-detects `.env`, token files), shared utilities |

## Test Results

Tested on `pallets/flask`:
- **46 LHT bundles** produced
- **1,517 / 1,627 PRs attributed** (93% attribution rate)
- **84% via git log merges** (Tier 1 — highest accuracy method)
- Remaining 9% via compare API, <1% via date fallback

## Key Design Decisions

1. **Sort by version, not date.** Backport releases (e.g., `v1.2.4` released after `v2.0.0`) would break date-sorted ordering. Version-sort ensures correct consecutive pairing.

2. **Ancestry verification before pairing.** Prevents pairing tags from parallel release lines or imported sub-projects (e.g., `dask-expr` tags appearing in the `dask` repo).

3. **Git log merges as Tier 1.** `git log --merges --first-parent base..head` has no commit cap (unlike GitHub's 250-commit compare API limit) and directly reads merge commit messages for PR numbers.

4. **Date fallback only when compare returns zero commits.** If compare returned commits but none matched a PR, the tag range likely belongs to a different lineage. Assigning temporally-coincident PRs would be incorrect.

5. **All sort keys use a scheme-discriminator prefix.** `(0, ...)` for semver, `(1, ...)` for calver, `(2, ...)` for unknown — prevents Python `TypeError` when comparing mixed-scheme tuples.

6. **Minimum 2 PRs per bundle.** Single-PR version ranges are excluded from LHT bundles (`_MIN_PRS_PER_BUNDLE = 2` in `group_prs_by_tags.py`). A single PR between two tags doesn't constitute a meaningful "long horizon" task — it's better served by the standard SWE pipeline.
