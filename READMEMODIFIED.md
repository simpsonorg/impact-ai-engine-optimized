<!-- filepath: c:\data\maincode\impact-ai-engine-optimized-main\README.md -->
# 🚀 Optimized Impact Analyzer Engine

🎯 Stop the Fire Drill: Precise Impact Analysis for Microservices

🌟 Project Overview

The Optimized Impact Analyzer Engine is a specialized, reproducible analysis tool designed to eliminate guesswork in complex microservice environments. When a developer submits a code change, this engine executes in CI to build a dynamic knowledge graph of the entire landscape, accurately tracing the downstream ripple effect of the change.

Our core innovation lies in the seamless integration of knowledge graph pathfinding (NetworkX) with Retrieval-Augmented Generation (RAG). This fusion allows us to not only identify which services are affected but also provide an LLM-driven explanation, risk score, and recommended mitigation actions—all packaged into a concise, ready-to-post Pull Request comment.

The result is instant, high-confidence feedback, transforming code review from a manual, error-prone process into an automated, data-driven security and stability check.

---

## Key Features

- 🌐 Microservice Discovery — Intelligently scans the repository to discover service folders, code artifacts, and service-to-service dependencies via import/URL/contract analysis.
- 🧠 Knowledge Graph Mapping — Builds an enriched, directed NetworkX graph, calculating metrics like PageRank and Centrality to prioritize critical services.
- 🔎 Change-to-Impact Pathing — Maps specific changed files to starting nodes and computes the full downstream impact path across the graph.
- 📚 Contextual Retrieval (RAG) — Chunks and embeds relevant code snippets, using nearest-neighbor search (FAISS/NumPy) to retrieve highly specific context for LLM analysis.
- 🤖 LLM-Driven Risk Analysis — Orchestrates the language model (OpenAI/Gemini) to produce a structured `impact-summary.json` artifact and a rich HTML/Markdown PR comment.
- 📈 Risk Quantification — Generates a normalized risk estimate (0-100) based on path complexity, service centrality, and content analysis.

---

## Overview & Core responsibilities

This repository implements an engine that estimates the runtime impact of code changes across a microservice landscape and produces a concise PR comment (HTML + Markdown) and a JSON artifact summarizing affected services and risk. It is designed as a best-effort, reproducible analyzer to be executed in CI or locally.

Core responsibilities:
- Discover service folders and code artifacts
- Infer service-to-service dependencies
- Build an enriched knowledge graph (NetworkX)
- Map changed files to starting nodes and compute downstream impact
- Retrieve code snippets using RAG (optional embeddings + FAISS)
- Orchestrate LLM analysis to produce a structured JSON and a markdown PR comment
- Produce an on-disk artifact: `impact-summary.json`

---

## System Architecture (brief)

The analyzer follows a robust, four-stage pipeline designed for execution speed and reproducibility.

Data Flow and Stages:

1. Discovery & Scanning: Identifies services and parses artifacts (code, OpenAPI, Proto) to extract communication patterns.
2. Graph Construction: Builds a directed NetworkX graph, enriching nodes and edges with metrics (PageRank, centrality).
3. Retrieval: Extracts and scores relevant code snippets for changed files using RAG for contextual depth.
4. Analysis & Formatting: Calls the LLM with context, generating a structured JSON artifact and a human-readable PR summary.

---

## Quick summary of important files

- `run_analysis.py` — main entrypoint (`run_analysis.run_analysis`) and helpers
- `analyzer/vcs_scanner.py` — repo scanning, import/url extraction, contract discovery, mapping files -> services
- `analyzer/graph_builder.py` — build, enrich (metrics), and serialize the knowledge graph
- `analyzer/rag_retriever.py` — chunking and embedding helper for RAG retrieval
- `analyzer/impact_analyzer.py` — LLM orchestration (structured JSON + markdown output)
- `tests/` — pytest test-suite
- `.github/workflows/impact-analysis.yml` — example CI integration
- `impact-summary.json` — sample output artifact

---

## Winning Architecture Diagram (concise)

A compact architecture diagram and explanation showing how the analyzer runs in CI, processes cross-repo changes (8 microservice repos + analyzer), and produces structured output.

Mermaid flowchart (copy into GitHub README to render):

```mermaid
flowchart LR
  PR[GitHub Pull Request]
  GA[GitHub Actions Runner]
  PR --> GA
  GA --> CheckoutPR[Checkout PR repo (current repo)]
  GA --> CheckoutAnalyzer[Checkout analyzer repo: impact-ai-engine-optimized]
  CheckoutAnalyzer --> CloneMicroservices[Clone 8 microservice repos]
  CloneMicroservices --> SetupPython[Setup Python & deps]
  SetupPython --> RunAnalyzer[Run impact-ai-engine-optimized/run_analysis.py]

  subgraph AnalyzerPipeline [Analyzer (run_analysis.py)]
    direction TB
    A1[discover_microservices] --> A2[build_service_dependency_graph]
    A2 --> A3[build_knowledge_graph (NetworkX)]
    A3 --> A4[impacted_services_from_files (BFS downstream)]
    A4 --> A5[get_relevant_snippets (RAG + embeddings)]
    A5 --> A6[analyze (LLM structured JSON + markdown)]
    A6 --> Out[Outputs: impact-summary.json + markdown_comment]
  end

  RunAnalyzer --> AnalyzerPipeline
  Out --> PostComment[Post PR comment (GitHub API)]
  PostComment --> PR
```

Concrete flow mapped to repository symbols and files
- CI orchestration: `.github/workflows/impact-analysis.yml`
- Entrypoint: `run_analysis.run_analysis` (`run_analysis.py`)
- Discovery & scanning: `analyzer.vcs_scanner.discover_microservices` (`analyzer/vcs_scanner.py`)
- Dependency inference: `analyzer.vcs_scanner.build_service_dependency_graph` (`analyzer/vcs_scanner.py`)
- Knowledge graph: `analyzer.graph_builder.build_knowledge_graph` (`analyzer/graph_builder.py`)
- Impact traversal: `analyzer.graph_builder.impacted_services_from_files` (`analyzer/graph_builder.py`)
- Retrieval: `analyzer.rag_retriever.get_relevant_snippets` (`analyzer/rag_retriever.py`)
- LLM orchestration: `analyzer.impact_analyzer.analyze` (`analyzer/impact_analyzer.py`)

Notes about the 8 microservice repositories
- The CI job clones or checks out 8 microservice repos in addition to this analyzer repo (see the workflow environment variables).
- The analyzer builds an identifier map and parses contracts across those repos to map imports/URLs/contracts into service nodes used in the knowledge graph.
- Cross-repo scanning enables end-to-end impact analysis when PRs touch shared contracts, API clients, or libraries.

Concise technical differentiators
- Dual-output: machine-readable JSON (`impact-summary.json`) plus human-friendly `markdown_comment` for PRs.
- Graph-first prioritization: metrics (PageRank, centrality, downstream_count) inform severity and recommendations.
- RAG evidence: retrieved code hunks accompany findings to provide auditability and context.
- Fallbacks: conservative outputs if embeddings/LLM are unavailable.

Live PR example (structured LLM path)
- Example log lines produced during analysis:
  - [impact_analyzer] Attempting structured LLM call
  - [impact_analyzer] USING_LLM: structured response received

- Example PR comment (HTML + Markdown snippet — this content is generated by the analyzer source code as part of `analyzer.impact_analyzer.analyze`):

<style> .card { padding:16px; margin:12px 0; border:1px solid #e1e4e8; border-radius:8px; background:#fafbfc; } .card h2, .card h3 { margin-top:0; } .sev-high { color:white; background:#d73a49; padding:2px 6px; border-radius:4px; } .sev-med { color:white; background:#fb8c00; padding:2px 6px; border-radius:4px; } .sev-low { color:white; background:#28a745; padding:2px 6px; border-radius:4px; } .service-card { padding:12px; margin-bottom:12px; border:1px solid #e1e4e8; border-radius:6px; background:#ffffff; } </style>

<div class="card">
<h2>PR Impact Summary</h2>
<p>This PR refactors comments in the codebase, impacting the <strong>crud-ms-account-load-db</strong> and <strong>domain-ms-account-load</strong> services. The changes are primarily cosmetic, with low risk of functional impact.</p>

<h3>Checklist of Recommended Actions</h3>
<ul>
<li>Review for clarity and consistency in comments.</li>
<li>Ensure comments accurately reflect the code logic.</li>
<li>Run unit tests for both impacted services.</li>
</ul>

<h3>Service Impact Details</h3>
<div class="service-card">
<h4>crud-ms-account-load-db <span class="sev-low">Low</span></h4>
<p><strong>Files Changed:</strong> main.py</p>
<p><strong>Suggested Tests:</strong> <code>pytest crud-ms-account-load-db/tests/test_api.py</code></p>
<p><strong>Recommended Actions:</strong> Review for clarity and consistency in comments.</p>
<p><strong>Suggested Reviewers:</strong> @devteam1, @devteam2</p>
</div>

<div class="service-card">
<h4>domain-ms-account-load <span class="sev-low">Low</span></h4>
<p><strong>Files Changed:</strong> main.py</p>
<p><strong>Suggested Tests:</strong> <code>pytest domain-ms-account-load/tests/test_routes.py</code></p>
<p><strong>Recommended Actions:</strong> Ensure comments accurately reflect the code logic.</p>
<p><strong>Suggested Reviewers:</strong> @devteam3, @devteam4</p>
</div>
</div>

*Note: the PR comment example above is representative output produced by the analyzer's LLM orchestration code (`analyzer/impact_analyzer.py`).*

---

## Execution (detailed)

Prerequisites
- Python 3.10+ (project CI uses 3.12 but the code is compatible with 3.10+)
- Install deps: `pip install -r requirements.txt`

### Environment variables

| Variable | Description | Default | Required |
|---|---|---:|:---:|
| REPOS_BASE_DIR | Root path containing all microservice folders. | `.` | Yes |
| CHANGED_FILES | Newline-separated paths of changed files (relative to REPOS_BASE_DIR). | N/A | Yes |
| OPENAI_API_KEY | API key for LLM calls and RAG embeddings. | N/A | No |
| PR_TITLE | Title of the Pull Request for inclusion in output. | N/A | No |

Local run example (POSIX):

```sh
export REPOS_BASE_DIR=/path/to/repo
export CHANGED_FILES="svc-a/app.py"
export PR_TITLE="Fix auth bug"
python run_analysis.py
```

What run_analysis produces
- `impact-summary.json` — structured artifact containing generated_at, pr_title, changed_files, impacted services list and a numeric risk estimate
- `markdown_comment` (returned by LLM) — ready-to-post HTML+Markdown summary (not automatically posted by this repo)

Interpretation of outputs
- `impacted` — list of service objects (name, severity, explanation, recommended actions)
- `risk_estimate` — integer summary score normalized by heuristics in the code (0-100)

---
### Tech & Concepts matrix

| Category | Technologies Used | Concept/Library Focus |
|---|---|---|
| Graph & Analysis | Python, NetworkX, NumPy | Directed graphs, Pagerank, Betweenness Centrality, Vector operations. |
| Language Models | OpenAI/Gemini API | Embeddings for RAG, Structured JSON response generation, Fallback clients. |
| Code Parsing | Python AST, Regex, esprima | Robust, language-agnostic import/contract extraction and URL detection. |
| Vector Search | FAISS (Optional) | High-performance vector index for nearest neighbor search in RAG. |
| Contracts & Tools | OpenAPI/Proto Parsers, pytest, GitHub Actions | Best-effort contract discovery, Unit testing, CI/CD integration. |

---

## Technology concepts and libraries used

- Python — orchestration language and tests
- NetworkX — directed knowledge graph, metrics (pagerank, centrality, betweenness, SCC)
- AST parsing (Python) and optional `esprima` for JS/TS — robust import extraction
- Regex heuristics — URL detection and fallback parsing
- OpenAPI (YAML/JSON) & Proto parsing — contract discovery (best-effort)
- Retrieval-Augmented Generation (RAG) — chunking + embeddings + nearest neighbor retrieval
- OpenAI Embeddings & Chat API — snippet scoring and LLM-based analysis (fallback to legacy client supported)
- FAISS (optional) — vector index for fast nearest neighbor search
- NumPy — vector operations during embedding handling
- pytest — unit tests and CI validation
- GitHub Actions — sample workflow to run analyzer in PRs

---

## Tests & CI

Run unit tests locally:

```sh
pytest -q
```

Key tests to inspect:
- `tests/test_contract_diff.py` — contract discovery and parsing
- `tests/test_graph_metrics.py` — knowledge graph creation & metrics
- `tests/test_llm_mock.py` — LLM orchestration and fallback behavior
- `tests/test_run_analysis.py` — end-to-end run using env variables

CI sample job
- `.github/workflows/impact-analysis.yml` demonstrates using the repository in a PR environment: it sets env vars, runs `run_analysis.py`, and records `impact-summary.json`.

---

## Design notes and limitations

- Best-effort & non-fatal: failures in embeddings or LLM calls fall back to simpler outputs.
- Contract parsing is conservative — complex/invalid OpenAPI or proto files may be partially parsed.
- JS/TS parsing uses `esprima` if available; regex fallback is less accurate.
- Mapping changed files -> services is heuristic-driven (path matching, token identifiers, content inspection).
- RAG improves LLM context but requires `OPENAI_API_KEY` and optionally FAISS; otherwise raw snippets are used.

Security & privacy
- LLM calls (OpenAI) send code and snippets to external APIs; sanitize secrets and do not expose PII.

---

## Submission checklist (for evaluators)

| Step | File / Concept | Status |
|---|---|:---:|
| Entry Point | `run_analysis.py` (`run_analysis.run_analysis`) | Complete |
| Discovery | `analyzer/vcs_scanner.py` (contract parsing) | Complete |
| Graphing | `analyzer/graph_builder.py` (NetworkX & Metrics) | Complete |
| RAG/Embeddings | `analyzer/rag_retriever.py` (FAISS, NumPy, OpenAI Embeddings) | Complete |
| LLM Output | `analyzer/impact_analyzer.py` (Structured JSON & Markdown) | Complete |
| Testing | `tests/` (Unit tests via `pytest -q`) | Complete |
| CI Example | `.github/workflows/impact-analysis.yml` | Complete |

---

## Recommendations for demonstration

- Run end-to-end with a small example repo that contains 2–3 services and a single changed file.
- Show `impact-summary.json` and the LLM-produced `markdown_comment`.
- Highlight how pagerank/centrality affect severity prioritization in prompts.

---

## Contact & next steps

For further improvements consider:
- Add a small sample repository under `examples/` demonstrating common contract patterns
- Add a simple PR poster script that uses GitHub token to post the `markdown_comment`
- Provide optional local FAISS index building for faster retrieval during demo runs

---

_Last updated: 2025-11-21_
