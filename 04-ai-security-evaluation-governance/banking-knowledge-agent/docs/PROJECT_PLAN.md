# PROJECT PLAN — Banking Knowledge Agent

> Moved verbatim from the former `prompt.md` (§4–§8 and every stage section), archived in
> `docs/legacy/prompt.md`. Workflow and rules live in `CLAUDE.md`.
> **Read only the current stage's section**, not the whole file.

---

# 4. PROJECT DEFINITION

Build a production-style AI knowledge and support agent for a banking technology platform similar to CR2.

CR2 and BankWorld are used only as inspiration for the domain.

The system should support engineers and technical users working with complex banking software.

The domain should cover:

* ATM and self-service banking
* Digital banking
* Cards
* Payments
* APIs
* Integrations
* Configuration
* Operational procedures
* Troubleshooting
* Incidents
* Technical documentation

Do NOT copy:

* CR2 proprietary documentation
* CR2 source code
* CR2 branding
* Confidential information
* Copyrighted documentation

Use synthetic banking documentation created specifically for this project.

---

# 5. PRIMARY ARCHITECTURE

The final system should demonstrate:

User
|
v
Web Interface
|
v
API
|
v
Agent / LLM
|
+---- RAG Knowledge Retrieval
|
+---- MCP Tools
|
+---- Conversation Context
|
+---- Guardrails
|
v
Source-backed Answer

The architecture must allow additional:

* Knowledge sources
* Banking domains
* Tools
* LLM providers
* Vector stores

without requiring a complete redesign.

The objective is NOT simply to build a chatbot.

The objective is to demonstrate production-oriented AI engineering using:

* LLMs
* RAG
* Agents
* MCP
* Testing
* Observability
* Docker
* Clean architecture

---

# 6. ENGINEERING PRINCIPLES

Use:

* Python
* FastAPI
* LLM integration through a clean abstraction
* RAG
* Embeddings
* Vector search
* MCP
* Docker
* Automated testing
* Structured logging
* Observability
* Environment-based configuration
* Git/GitHub

Use established libraries where appropriate.

Do not introduce technologies merely because they are fashionable.

Every major technology must have a clear architectural purpose.

Prefer simple, maintainable implementations over unnecessary complexity.

Keep everything runnable locally.

---

# 7. REPOSITORY REQUIREMENTS

The repository root is the project root.

Do NOT create another `banking-knowledge-agent` directory inside it.

Do not create unnecessary nested directories.

The repository must eventually contain:

* Application source code
* Tests
* Synthetic knowledge documents
* Configuration
* Docker configuration
* Documentation
* Architecture documentation
* Diagrams
* API documentation
* Developer setup instructions
* `requirements.txt`
* `.gitignore`
* `.env.example`
* `README.md`
* `docs/HANDOVER.md`
* `docs/architecture-guide.html`

Never create a real `.env` containing secrets.

After every structural change, verify the expected files and directories exist.

---

# 8. PERSONAL KNOWLEDGE DOCUMENTATION

Create:

`docs/architecture-guide.html`

This is a personal technical knowledge/reference document.

It is NOT the application's user-facing interface.

It should help the developer understand and remember the system.

Include:

* Overall architecture
* Repository structure
* Technology stack
* What every major component does
* Why each technology is used
* Data flow
* RAG flow
* Agent flow
* MCP flow
* LLM interaction
* Vector database
* API layer
* Docker
* Testing
* Observability
* Security
* Deployment
* Future extension points

Include simple diagrams and examples.

Keep this document updated whenever the architecture changes.

A decision is not recorded until it is written into `docs/architecture-guide.html`. This
applies to every design decision made during any stage from Stage 3 onward — including a
decision presented to the user as multiple options with a recommendation, and whichever
option they choose. Record the decision at the time it is made, in the same what / why /
what was rejected form as previous entries, not only in the stage-end summary. Do not wait
to be reminded.

---
# 9. STAGE 1: PROJECT FOUNDATION

Create the initial project structure.

Implement:

* Clean repository structure
* `requirements.txt`
* `.gitignore`
* `.env.example`
* `README.md`
* Basic application entry point
* Basic test structure
* Configuration management
* Health endpoint
* Basic logging
* `docs/HANDOVER.md`
* Initial `docs/architecture-guide.html`

Do not implement the AI agent yet.

Testing must cover:

* Virtual environment setup
* Dependency installation
* Application startup
* Health endpoint
* Test suite

STOP after Stage 1.

---

# 10. STAGE 2: DOMAIN KNOWLEDGE

Create synthetic banking technical documentation.

Include realistic documents covering:

* ATM transactions
* Card authentication
* Payment processing
* Digital banking
* API integration
* Configuration
* Common errors
* Incident troubleshooting
* System components

Create enough content to make retrieval meaningful.

Implement document loading.

Add metadata:

* Document
* Domain
* Component
* Version
* Document type

Do not use real CR2 documentation.

Add document-loading tests.

Update the handover file.

STOP after Stage 2.

---

# 11. STAGE 3: RAG PIPELINE

Implement:

* Document chunking
* Metadata handling
* Embedding generation
* Vector storage
* Retrieval
* Similarity search
* Source metadata

Create a clean vector-store abstraction so the implementation can be replaced later.

Demonstrate:

Question
|
v
Embedding
|
v
Vector Search
|
v
Relevant Documents
|
v
Sources

The retrieval layer must be independently testable.

Add retrieval tests.

Include representative retrieval examples.

Update the handover file.

STOP after Stage 3.

---

# 12. STAGE 4: LLM ABSTRACTION

Implement an LLM service abstraction.

Do not tightly couple the application to one provider.

The architecture must allow the LLM implementation to be replaced.

Implement:

* Prompt management
* System instructions
* User question handling
* Context injection
* Response generation
* Error handling
* Environment configuration

The LLM must receive retrieved context rather than the entire knowledge base.

Add mocked LLM tests.

Update the handover file.

STOP after Stage 4.

---

# 13. STAGE 5: KNOWLEDGE AGENT

Build the first complete knowledge agent.

The agent must:

1. Receive a technical question.
2. Determine whether knowledge retrieval is required.
3. Retrieve relevant information.
4. Pass context to the LLM.
5. Produce a source-backed answer.
6. Clearly indicate when information is insufficient.

Example questions:

* Why would an ATM transaction fail after card authentication?
* What component handles card authentication?
* Which API is used for payment authorisation?
* How would I troubleshoot a failed cash withdrawal?
* What configuration controls transaction limits?

The agent must avoid inventing technical facts.

If the knowledge base does not contain sufficient information, explicitly say so.

Add agent tests.

Update the handover file.

STOP after Stage 5.

---

# 14. STAGE 6: MCP TOOLS

Introduce MCP.

Create synthetic banking support tools such as:

* Get system configuration
* Check transaction status
* Get component status
* Look up error code
* Retrieve system version
* Check service health

Use synthetic data only.

Demonstrate:

Agent
|
v
MCP
|
+---- Tool
|
+---- Tool
|
+---- Tool
|
v
Result

Clearly separate knowledge retrieval from live/tool information.

Add MCP tests.

Update the handover file.

STOP after Stage 6.

---

# 15. STAGE 7: AGENT DECISION AND TOOL SELECTION

Improve the agent so it can decide between:

* Answer from knowledge
* Retrieve additional knowledge
* Call an MCP tool
* Use both knowledge and tools
* Refuse when evidence is insufficient

Implement clear tool-selection behaviour.

Do not expose hidden chain-of-thought.

Expose useful execution information instead:

* Retrieval performed
* Documents used
* Tool used
* Tool result
* Final answer

Add tests for each decision path.

Update the handover file.

STOP after Stage 7.

---

# STAGE 8: CONVERSATION CONTEXT

Add controlled conversation context.

The agent should be able to handle follow-up questions while maintaining relevant context.

Implement:

* Conversation/session handling
* Context management
* Context limits
* Appropriate separation between conversation context and retrieved knowledge
* Tests for follow-up questions

Avoid sending unnecessary historical context to the LLM.

Document the design in `architecture-guide.html`.

Update the handover file.

STOP after Stage 8.

---

# STAGE 9: WEB INTERFACE

Create a simple professional local web interface.

Provide:

* Question input
* Conversation display
* Answer
* Sources
* Tool activity
* Basic error states

The interface should make it obvious when:

* RAG was used
* MCP was used
* Sources were consulted
* Information was insufficient

Do not spend excessive time on visual design.

The purpose is to demonstrate the underlying engineering.

Update the handover file.

STOP after Stage 9.

---

# STAGE 10: OBSERVABILITY

Add production-style observability.

Implement structured logging.

Track:

* Request ID
* Question
* Retrieval latency
* Retrieved documents
* LLM latency
* Tool calls
* Tool latency
* Errors
* Overall response latency

Where practical, introduce metrics and tracing.

Do not log secrets or sensitive information.

Document observability in `architecture-guide.html`.

Add tests where appropriate.

Update the handover file.

STOP after Stage 10.

---

# STAGE 11: TESTING AND EVALUATION

Build a proper evaluation framework.

Test:

* Retrieval accuracy
* Answer grounding
* Hallucination resistance
* Tool selection
* Tool results
* Failure handling
* API behaviour
* Agent behaviour

Create a small evaluation dataset containing realistic banking questions and expected evidence.

Measure retrieval and answer quality where practical.

Document known limitations.

Update the handover file.

STOP after Stage 11.

---

# STAGE 12: CONTAINERISATION

Create Docker support.

Implement:

* Dockerfile
* Docker Compose where appropriate
* Environment configuration
* Health checks
* Local startup instructions

The application must run locally without requiring cloud infrastructure.

Synthetic data must remain available locally.

Test the complete system through Docker.

Update the handover file.

STOP after Stage 12.

---

# STAGE 13: SECURITY AND PRODUCTION READINESS

Review the system for production considerations.

Identify and document:

* Authentication
* Authorisation
* Secrets management
* Input validation
* Prompt injection risks
* MCP security
* Data privacy
* Rate limiting
* LLM failure handling
* Tool failure handling
* Logging risks
* Dependency security

Implement appropriate lightweight protections where practical.

Do not introduce unnecessary enterprise infrastructure.

Update `architecture-guide.html`.

Update the handover file.

STOP after Stage 13.

---

# STAGE 14: PRODUCTION ARCHITECTURE

Review the complete system as a production architecture.

Document:

* Scaling considerations
* Vector database scaling
* LLM provider abstraction
* MCP architecture
* Service boundaries
* Deployment strategy
* Observability
* Failure modes
* Data privacy
* High availability considerations

Create an architecture diagram showing:

Client
|
API
|
Agent
|
+---- RAG
|
+---- MCP
|
+---- LLM
|
Knowledge / Tools / External Systems

Clearly distinguish:

LOCAL DEVELOPMENT

from

PRODUCTION ARCHITECTURE

Do not implement infrastructure that is not required for the portfolio project.

Update the handover file.

STOP after Stage 14.

---

# STAGE 15: FINAL ENGINEERING REVIEW

Perform a complete engineering review.

Check:

* Architecture
* Separation of concerns
* Type hints
* Error handling
* Logging
* Testing
* Configuration
* Security
* Dependency management
* Documentation
* Docker
* Code quality
* Naming
* Dead code
* Duplicate code
* Repository structure
* Accidental secrets
* Accidental nested project directories

Fix issues found.

Run the complete test suite.

Verify that all documented commands actually work.

Verify:

* Repository structure
* Git status
* Tests
* Docker
* Application startup
* Documentation
* Handover file

Update `docs/HANDOVER.md` with the final project state.

STOP and provide the final engineering summary.
