# 📌 Model Card – Impact AI Engine

This document provides a detailed, transparent description of the Large Language Models (LLMs) and Embedding Models used by the **Impact AI Engine** for automated Pull Request (PR) impact analysis.

---

## 🔍 1️⃣ Models Used

| Model Name | Type | Purpose |
|----------|------|---------|
| **gpt-4o-mini** | LLM (Chat/Completions) | Generate PR impact assessments, structured Markdown reports |
| **text-embedding-3-large** | Embedding Model | Convert code into vector format for RAG, find most relevant impacted snippets |

These models are used together to enable **Context-aware impact intelligence** during code reviews.

---

## 🤖 2️⃣ Model: `gpt-4o-mini`

### 📌 Why this model?

- Designed for **highly structured output** – ideal for PR comments & tables
- Handles dependency graphs + code snippets efficiently
- **Low latency** → suitable for fast CI/CD pipelines
- **Cost-effective** while still semantically strong
- Large enough context window for:
  - 10–20 changed files
  - Graph metadata
  - Snippets from multiple services

### 💡 Responsibilities in System

- Converts technical details into **reviewer-friendly** insights
- Generates:
  - PR impact summaries
  - Risk levels
  - Recommended tests
  - Reviewer guidance
- Used in → `analyzer/impact_analyzer.py`

### ⭐ Advantages

- Understands **multi-service architecture impacts**
- Excellent at table and bullet formatting (GitHub-friendly)
- Interprets code + metadata + graphs together
- Faster + cheaper than full GPT-4 models

### ⚠️ Limitations / Biases

- Can **hallucinate** reviewers/tests not present in context
- **Non-deterministic** output (varies slightly run-to-run)
- **Context boundaries** → huge PRs may truncate inputs
- Training data bias:
  - May assume industry-standard or OSS patterns over internal ones
- Compliance concern if sending **sensitive code** to cloud LLMs

💡 Mitigation:
- Deterministic fallback if API disabled
- RAG constraints reduce hallucination
- Use Enterprise/OpenAI private routing where applicable

---

## 🧬 3️⃣ Model: `text-embedding-3-large`

### 📌 Why this model?

- High-quality **semantic embeddings**
- Accurate similarity scoring across:
  - Python, JS/TS, configs, comments
- Better for **code vectorization** than general language embeddings
- API-simple → seamless FAISS integration

### 💡 Responsibilities in System

- Used in → `analyzer/rag_retriever.py`
- Enables **code-aware Retrieval-Augmented Generation (RAG)**:
  - Code chunk embedding
  - Vector index building
  - Relevant snippet search
- Supplies snippet context to `gpt-4o-mini` for reasoning

### ⭐ Advantages

- Detects related code even if **not directly referenced**
- Handles **loosely coupled microservice** architectures
- Identifies:
  - Schema dependencies  
  - API shifts  
  - Logic disruptions  

### ⚠️ Limitations / Biases

- **Semantic**, not syntactic:
  - Minor breaking code changes may seem irrelevant
- **Embedding cost** grows with repository size
- More common tech stacks may map better than niche internal frameworks
- Latency increases with:
  - Large repo chunking
  - Big PRs

💡 Mitigation:
- Chunk limiting and top-K retrieval
- Graceful degradation if embeddings fail

---

## 🛡️ 4️⃣ Fallback Behavior (No API Keys)

| Condition | System Behavior |
|----------|----------------|
| `OPENAI_API_KEY` missing | Skip LLM → Deterministic Markdown impact summary |
| Embeddings fail | Fall back to basic snippet extraction |
| Network/API issues | CI still posts a baseline report |

Benefits:
- **Zero downtime** during compliance lockdowns or cost control
- **Predictable output** in internal environments

---

## 🏁 Summary

| Capability | Status |
|-----------|--------|
| Multi-repo impact awareness | ✅ |
| Code-aware retrieval & reasoning | ✅ |
| Human-friendly PR insights | ✅ |
| Deterministic CI fallback | ✅ |
| Security controls | ⚠️ Dependent on API policies |

The chosen model stack enables:
- Faster reviews  
- Reduced SME dependency  
- Production-grade automation for code impact analysis 🚀  

---

📌 **This Model Card should be updated whenever:**
- Models change or are augmented (e.g., GPT-4 series)
- Prompting logic is updated
- RAG pipeline evolves

---

> 👤 Maintainer: Impact AI Engine Team  
> 🔄 Last Updated: *Auto-sync with latest deployment*

