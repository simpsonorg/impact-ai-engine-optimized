# 📦 Full SBOM – Impact Delphyne (AI Optimized Impact Analyzer Engine)

Generated: 2025-11-26T10:34:58.230834Z

## 1. High-Level System Summary
Impact Delphyne is a multi-stage automated impact analyzer using:
- Static dependency scanning
- Knowledge Graphs (NetworkX)
- RAG retrieval (FAISS/NumPy/pgvector)
- LLM-driven risk scoring
- PR-based CI automation

Repository: https://github.com/simpsonorg/impact-ai-engine-optimized

## 2. Repository Component Listing
Core modules:
- run_analysis.py
- analyzer/vcs_scanner.py
- analyzer/graph_builder.py
- analyzer/rag_retriever.py
- analyzer/impact_analyzer.py
- fastapi-listener (optional)
- tests/

## 3. External Systems & Microservices
- GitHub Actions CI
- FastAPI Listener Microservice
- NeonDB with pgvector
- Railway/Render/Fly deployment
- OpenAI API
- FAISS vector index (optional)

## 4. Dependencies
| Package | License | Purpose |
|--------|---------|---------|
| networkx | BSD-3 | Knowledge Graphs |
| numpy | BSD | Vector math |
| openai | MIT | LLM integration |
| faiss-cpu | MIT | Vector similarity |
| pyyaml | MIT | OpenAPI parsing |
| esprima | BSD | JS parsing |
| GitPython | BSD-3 | Git operations |
| fastapi | MIT | Listener service |
| uvicorn | BSD | ASGI server |
| psycopg2 | LGPL | Postgres driver |
| requests | Apache-2 | HTTP client |
| pytest | MIT | Tests |

## 5. LLM Model SBOM
| Model | Provider | Purpose |
|-------|----------|---------|
| gpt-4o-mini | OpenAI | PR analysis |
| text-embedding-3-small | OpenAI | Embeddings |
| Gemini (optional) | Google | Alternative analysis |

## 6. Knowledge Graph Structure
Nodes = services, APIs, files  
Edges = imports, URL callouts  
Metrics = PageRank, centrality, SCC

## 7. RAG Components
- Chunker → splitter
- Embeddings → OpenAI
- Vector Store → FAISS or pgvector
- Retriever → KNN top-k search

## 8. CI Workflow SBOM
Files:
- .github/workflows/impact-analysis.yml
- impact-summary.json

## 9. Security Considerations
- External LLM usage
- GitHub token scopes
- DB sslmode=require
- Repo cloning sanitation
- Embeddings storage

## 10. CycloneDX & SPDX Files Included
sbom.json  
sbom.spdx

