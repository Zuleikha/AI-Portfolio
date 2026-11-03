# Research Agent — Progress

## Project goal

Build a LangGraph agent that searches PubMed, summarises the findings, checks every claim against its citations, and writes an audit record for each run.

## Stages

- [x] 1. Check the repo and set up the folder structure
- [ ] 2. Set up the environment and install LangGraph
- [ ] 3. Build the PubMed search tool
- [ ] 4. Build the summarise step
- [ ] 5. Build the citation check step
- [ ] 6. Connect the steps into a graph, add the audit log, and run it
- [ ] 7. Add tracing with Langfuse or LangSmith

## Session log

| Date | What was done | Next step |
|------|---------------|-----------|
| 2026-11-03 | Inspected the AI-Portfolio repo and created the `research-agent/` scaffold: placeholder modules, `.env.example`, `requirements.txt`, `.gitignore` (ignores `.env` and `runs/`). No agent logic yet. | Stage 2: create a virtual environment, pin and install requirements, confirm LangGraph imports. |
