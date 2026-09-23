# AI Systems Portfolio

I design and build **AI systems**: retrieval and agent architectures, evaluation and
governance controls, ML pipelines and intelligent automation. The focus is on how a
system behaves: what it grounds its answers in, when it refuses, how its decisions can
be reproduced, and how it can be checked.

This repository collects that work in one place, grouped by the capability each
project demonstrates. Every project folder is self-contained and has its own README.

> **Evidence label:** everything here is **personal project work**, self-directed
> build and study. None of it is presented as professional pharmaceutical, clinical or
> banking experience. Domain data is synthetic or public unless stated. Apart from
> RentPulse, these projects are not deployed with real users.

---

## At a glance

| Category | Projects |
|---|---|
| [1 · AI Systems & Architecture](#1--ai-systems--architecture) | production-llm-platform · xml-content-retrieval-service · hybrid-retrieval-rag-service · menuforge |
| [2 · AI/ML & Data](#2--aiml--data) | realtime-transaction-scoring-api · candidate-ranking-service |
| [3 · Intelligent Automation](#3--intelligent-automation) | RentPulse *(documentation only)* |
| [4 · AI Security, Evaluation & Governance](#4--ai-security-evaluation--governance) | banking-knowledge-agent |
| [5 · Life Sciences / Healthcare AI](#5--life-sciences--healthcare-ai) | pharma-ai · ml-training-orchestration-pipeline |

Several projects demonstrate more than one category. Each is filed under its strongest one,
and its README lists the others.

---

## 1 · AI Systems & Architecture

| Project | What it does | What it demonstrates |
|---|---|---|
| [**production-llm-platform**](01-ai-systems-architecture/production-llm-platform) | LLM platform built in ten documented stages: LangGraph agent on the Anthropic API, cited RAG, observability, CI evaluation gate, Kubernetes | Platform architecture, staged delivery, architecture decision records |
| [**xml-content-retrieval-service**](01-ai-systems-architecture/xml-content-retrieval-service) | Search and grounded Q&A over structured XML (DITA and JATS research articles), chunked on the document's own markup | Structure-aware retrieval, plus an honest measurement against fixed-size windows |
| [**hybrid-retrieval-rag-service**](01-ai-systems-architecture/hybrid-retrieval-rag-service) | Document Q&A with dense + BM25 retrieval, rank fusion, cross-encoder reranking and cited answers | Retrieval pipeline design |
| [**menuforge**](01-ai-systems-architecture/menuforge) | Menu photo → validated database records via one forced-tool-use Claude call | Structured extraction, schema contracts, bounded retry |

## 2 · AI/ML & Data

| Project | What it does | What it demonstrates |
|---|---|---|
| [**realtime-transaction-scoring-api**](02-ai-ml-data/realtime-transaction-scoring-api) | Fraud-risk scoring API that returns probability, decision and the threshold used | Imbalanced classification, SHAP explainability, cost-aware threshold choice |
| [**candidate-ranking-service**](02-ai-ml-data/candidate-ranking-service) | Ranks resumes against a job description with a per-component score breakdown | Explainable ranking; "ranks, does not decide" as a design constraint |

## 3 · Intelligent Automation

| Project | What it does | What it demonstrates |
|---|---|---|
| [**RentPulse**](03-intelligent-automation/rentpulse) | Chrome extension that alerts renters in Ireland to matching new listings across six sites. **Live product**: [rentpulse.ie](https://www.rentpulse.ie) | End-to-end product delivery: billing, store review, versioned releases. *No AI/ML; source not published* |

## 4 · AI Security, Evaluation & Governance

| Project | What it does | What it demonstrates |
|---|---|---|
| [**banking-knowledge-agent**](04-ai-security-evaluation-governance/banking-knowledge-agent) | Support agent over synthetic banking docs and MCP tools. It cites every claim and refuses without evidence | Groundedness, prompt-injection defence, evaluation gates, privacy-safe logging |

## 5 · Life Sciences / Healthcare AI

| Project | What it does | What it demonstrates |
|---|---|---|
| [**pharma-ai**](05-life-sciences-healthcare-ai/pharma-ai) | Drug-discovery workflow for the DHFR target: structure prediction, pocket detection, docking, cheminformatics | Integrating scientific tools into one workflow and reading the results correctly. *Pre-clinical and computational only* |
| [**ml-training-orchestration-pipeline**](05-life-sciences-healthcare-ai/ml-training-orchestration-pipeline) | Fine-tunes BiomedBERT to detect adverse drug events in biomedical literature, with a Dagster pipeline and drift monitoring | Biomedical NLP and reproducible ML pipelines |

---

## About this repository

- **Each project folder is a static snapshot**, independently readable, with its own
  dependencies and, for all but pharma-ai, its own test suite. Projects don't depend on each other.
- **This repository holds the current version of each project.** Where an earlier public
  repository exists, its README links to it as *development history*.
- Secrets are never committed. Each project reads credentials from environment variables
  and ships a `.env.example` where one is needed.
- Some projects fetch public datasets at run time instead of redistributing them.
