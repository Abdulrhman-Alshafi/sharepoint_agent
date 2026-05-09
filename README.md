# SharePoint AI Agent

**Domain-Driven Design + Clean Architecture FastAPI Application**

A production-ready AI-powered agent that translates natural language prompts into SharePoint provisioning blueprints and automatically manages SharePoint resources via Microsoft Graph API. Supports sites, lists, libraries, pages, permissions, hub sites, enterprise scenarios, file operations, document intelligence, and conversational state.

---

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Architecture Overview](#architecture-overview)
- [Project Structure](#project-structure)
- [API Endpoints](#api-endpoints)
- [DDD / Clean Architecture Principles](#ddd--clean-architecture-principles)
- [Design Patterns](#design-patterns)
- [Docker](#docker)
- [Adding New Features](#adding-new-features)
- [Troubleshooting](#troubleshooting)

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- pip or conda
- Azure AD credentials (Tenant ID, Client ID, Client Secret)
- An AI provider: **Gemini API key**, **Vertex AI** service account, or an **OpenAI-compatible** endpoint (Groq, Ollama, etc.)
- (Optional) Redis — used for persistent conversation state, distributed rate limiting, and security controls
- (Optional) Docker + Docker Compose

### Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Copy the environment template and fill in your credentials
cp .env.example .env
```

### Environment Variables

```env
# AI provider (gemini | vertexai | openai)
AI_PROVIDER=gemini

# ── Gemini ──
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-2.0-flash

# ── Vertex AI (Google Cloud) ──
# VERTEXAI_PROJECT_ID=your_gcp_project_id
# VERTEXAI_LOCATION=us-central1
# VERTEXAI_MODEL=gemini-2.5-flash
# VERTEXAI_CLIENT_EMAIL=your-sa@project.iam.gserviceaccount.com
# VERTEXAI_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"

# ── OpenAI-Compatible (Groq, Ollama, etc.) ──
# OPENAI_API_KEY=your_key
# OPENAI_BASE_URL=https://api.groq.com/openai/v1
# OPENAI_MODEL=llama3-8b-8192

# Azure AD / Microsoft Graph
TENANT_ID=your_azure_tenant_id
CLIENT_ID=your_azure_client_id
CLIENT_SECRET=your_azure_client_secret
SITE_ID=your_sharepoint_site_id

# CORS — tenant allowlist (recommended for production)
ALLOWED_SHAREPOINT_TENANTS=yourtenant
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:4321

# Optional: Redis for distributed state
REDIS_URL=redis://redis:6379/0

# OBO token cache TTL (seconds, default: 900)
OBO_CACHE_TTL_SECONDS=900
```

> **Note:** API Key authentication has been removed. All requests require Azure AD JWT tokens via the On-Behalf-Of (OBO) flow.

### Running the Application

```bash
# Development server with auto-reload (run from sharepoint_ai/ directory)
uvicorn src.main:app --reload

# Production server
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Access the API:

| URL | Description |
|-----|-------------|
| http://localhost:8000/docs | Swagger / OpenAPI UI |
| http://localhost:8000/redoc | ReDoc UI |
| http://localhost:8000/ | API root |
| http://localhost:8000/health | Health check |

---

## 🏗️ Architecture Overview

### 5-Layer Clean Architecture

```
┌─────────────────────────────────────────┐
│   PRESENTATION LAYER                    │
│   Controllers, Orchestrators, Services  │
└────────────────────┬────────────────────┘
                     │ depends on
┌────────────────────▼────────────────────┐
│   DETECTION LAYER                       │
│   Intent, Classification, Routing       │
└────────────────────┬────────────────────┘
                     │ depends on
┌────────────────────▼────────────────────┐
│   APPLICATION LAYER                     │
│   Use Cases, Services, Commands, DTOs   │
└────────────────────┬────────────────────┘
                     │ depends on
┌────────────────────▼────────────────────┐
│   DOMAIN LAYER                          │
│   Entities, Value Objects, Interfaces   │
└────────────────────▲────────────────────┘
                     │ implements
┌────────────────────┴────────────────────┐
│   INFRASTRUCTURE LAYER                  │
│   Graph API, AI Clients, Repositories   │
└─────────────────────────────────────────┘
```

### Layer Responsibilities

| Layer | Purpose | Key Modules | Allowed Dependencies |
|-------|---------|-------------|---------------------|
| **Domain** | Pure business logic | Entities, Value Objects, Repository interfaces, Domain Services | None |
| **Application** | Orchestrate use cases | Use Cases, Application Services, Commands, DTOs | Domain |
| **Detection** | Cross-cutting NL pattern detection | Intent detectors, Classifiers, Routers, Semantic analysers | Domain |
| **Infrastructure** | External integrations | Graph API client, AI services, Repositories, Schemas | Domain, Application |
| **Presentation** | HTTP API (Controller → Orchestrator → Service) | Controllers, Orchestrators, Intent routing, API services | Application, Detection, Domain |

---

## 📁 Project Structure

```
sharepoint_ai/
├── src/
│   ├── main.py                            # FastAPI app factory + middleware
│   │
│   ├── domain/                            # Pure business logic (no framework deps)
│   │   ├── entities/
│   │   │   ├── core.py                    # SPList, SPPage, ProvisioningBlueprint
│   │   │   ├── conversation.py            # Conversation / message entities
│   │   │   ├── document.py                # Document entities
│   │   │   ├── enterprise.py              # Enterprise site/hub entities
│   │   │   ├── page_content_templates.py  # Page content template definitions
│   │   │   ├── preview.py                 # Blueprint preview entities
│   │   │   ├── query.py                   # Query result entities
│   │   │   ├── security.py                # Permission / security entities
│   │   │   └── templates.py               # Provisioning template entities
│   │   ├── value_objects/
│   │   │   ├── page_purpose.py            # Page purpose value object
│   │   │   └── resource_candidate.py      # Smart resource discovery candidates
│   │   ├── repositories/                  # Abstract repository interfaces
│   │   │   ├── enterprise_repository.py
│   │   │   ├── library_repository.py
│   │   │   ├── list_repository.py
│   │   │   ├── page_repository.py
│   │   │   ├── permission_repository.py
│   │   │   └── site_repository.py
│   │   ├── services/                      # Domain service interfaces
│   │   │   ├── intent_classification.py
│   │   │   ├── page_purpose_detector.py   # Page purpose detection logic
│   │   │   └── smart_resource_discovery.py
│   │   └── exceptions/                    # Domain exception hierarchy
│   │
│   ├── detection/                         # Cross-cutting NL pattern detection
│   │   ├── base.py                        # DetectionResult, scoring utilities
│   │   ├── intent/                        # Intent detectors
│   │   │   ├── analyze_detector.py
│   │   │   ├── delete_detector.py
│   │   │   ├── item_detector.py
│   │   │   ├── page_detector.py
│   │   │   ├── router.py                  # Intent routing coordinator
│   │   │   └── update_detector.py
│   │   ├── classification/                # NL classifiers
│   │   │   ├── page_purpose_classifier.py
│   │   │   └── template_classifier.py
│   │   ├── matching/                      # Pattern matching utilities
│   │   │   ├── library_matcher.py
│   │   │   ├── location_hint_detector.py
│   │   │   └── query_classifier.py
│   │   ├── operations/                    # Operation-type detectors
│   │   │   ├── enterprise_operation_detector.py
│   │   │   ├── file_operation_detector.py
│   │   │   ├── library_operation_detector.py
│   │   │   ├── list_item_operation_detector.py
│   │   │   ├── page_operation_detector.py
│   │   │   ├── permission_operation_detector.py
│   │   │   └── site_operation_detector.py
│   │   ├── routing/                       # Content routing
│   │   │   ├── page_content_router.py
│   │   │   ├── resource_type_router.py
│   │   │   └── webpart_router.py
│   │   ├── semantic/                      # Semantic analysis
│   │   │   ├── concept_mapper.py
│   │   │   └── synonym_expander.py
│   │   └── validation/                    # Validation detectors
│   │       └── confirmation_detector.py
│   │
│   ├── application/                       # Use cases & orchestration
│   │   ├── use_cases/
│   │   │   ├── provision_resources_use_case.py
│   │   │   ├── generate_preview_use_case.py
│   │   │   ├── delete_resource_use_case.py
│   │   │   ├── update_resource_use_case.py
│   │   │   ├── query_data_use_case.py
│   │   │   ├── analyze_content_use_case.py
│   │   │   ├── file_operations_use_case.py
│   │   │   ├── library_analysis_use_case.py
│   │   │   ├── list_item_crud_use_case.py
│   │   │   ├── list_item_batch_use_case.py
│   │   │   ├── list_item_operations_use_case.py
│   │   │   ├── list_item_views_use_case.py
│   │   │   └── provisioners/              # Dedicated provisioners per resource
│   │   │       ├── site_provisioner.py
│   │   │       ├── list_provisioner.py
│   │   │       ├── page_provisioner.py
│   │   │       ├── library_provisioner.py
│   │   │       ├── group_provisioner.py
│   │   │       └── enterprise_provisioner.py
│   │   ├── services/
│   │   │   ├── audit_service.py
│   │   │   ├── governance_service.py
│   │   │   ├── requirement_gathering_service.py
│   │   │   ├── smart_question_service.py
│   │   │   ├── smart_suggestions.py       # AI-powered smart suggestions
│   │   │   ├── question_templates.py
│   │   │   └── template_registry.py
│   │   ├── commands/                      # Command objects (user intentions)
│   │   ├── converters/                    # Domain <-> DTO converters
│   │   └── dtos/                          # Data transfer objects
│   │
│   ├── infrastructure/                    # External integrations
│   │   ├── config.py                      # Settings (pydantic BaseSettings)
│   │   ├── graph_service.py               # Low-level Graph API entry point
│   │   ├── rate_limiter.py                # Request rate limiting
│   │   ├── logging.py                     # Structured logging setup
│   │   ├── correlation.py                 # X-Request-ID correlation tracking
│   │   ├── resilience.py                  # Retry / circuit-breaker logic
│   │   ├── external_services/             # AI parsers & intelligence
│   │   │   ├── ai_blueprint_generator.py
│   │   │   ├── ai_client_factory.py       # AI provider factory (Gemini/VertexAI/OpenAI)
│   │   │   ├── ai_data_query_service.py
│   │   │   ├── ai_intent_classification.py
│   │   │   ├── document_intelligence.py
│   │   │   ├── library_intelligence.py
│   │   │   ├── query_intelligence.py
│   │   │   ├── site_resolver.py           # Fuzzy site name resolution
│   │   │   ├── enterprise_operation_parser.py
│   │   │   ├── file_operation_parser.py
│   │   │   ├── library_operation_parser.py
│   │   │   ├── list_item_parser.py
│   │   │   ├── page_operation_parser.py
│   │   │   ├── permission_operation_parser.py
│   │   │   ├── site_operation_parser.py
│   │   │   └── query/                     # Query intelligence sub-package
│   │   │       ├── service.py
│   │   │       ├── prompts.py
│   │   │       ├── helpers.py
│   │   │       ├── data_mixin.py
│   │   │       ├── library_mixin.py
│   │   │       ├── metadata_mixin.py
│   │   │       └── page_mixin.py
│   │   ├── repositories/
│   │   │   ├── graph_sharepoint_repository.py
│   │   │   ├── conversation_state_repository.py
│   │   │   ├── redis_conversation_state_repository.py
│   │   │   └── utils/
│   │   │       ├── canvas_builder.py
│   │   │       ├── canvas_editor.py
│   │   │       ├── payload_builders.py
│   │   │       ├── url_helpers.py
│   │   │       ├── error_handlers.py
│   │   │       ├── constants.py
│   │   │       └── webpart_composer.py
│   │   ├── services/
│   │   │   ├── authentication_service.py  # MSAL OBO token acquisition
│   │   │   ├── base_api_client.py
│   │   │   ├── graph_api_client.py        # Microsoft Graph API client
│   │   │   ├── rest_api_client.py         # SharePoint REST API client
│   │   │   ├── batch_operations_service.py
│   │   │   ├── cache_service.py
│   │   │   ├── clarification_engine.py
│   │   │   ├── concept_mapper.py
│   │   │   ├── concept_memory.py
│   │   │   ├── content_analyzer.py
│   │   │   ├── content_template_manager.py
│   │   │   ├── context_normalizer.py
│   │   │   ├── cross_resource_synthesizer.py
│   │   │   ├── document_index.py
│   │   │   ├── document_parser.py
│   │   │   ├── duplicate_name_resolver.py
│   │   │   ├── embedding_service.py
│   │   │   ├── field_validator.py
│   │   │   ├── input_sanitizer.py
│   │   │   ├── list_item_index.py
│   │   │   ├── multi_hop_retriever.py
│   │   │   ├── ontology_expander.py
│   │   │   ├── page_content_generator.py
│   │   │   ├── person_field_resolver.py
│   │   │   ├── query_resilience.py
│   │   │   ├── query_telemetry.py
│   │   │   ├── redis_security_store.py
│   │   │   ├── section_index.py
│   │   │   ├── smart_resource_discovery.py
│   │   │   ├── tenant_users_service.py
│   │   │   ├── token_validation_service.py
│   │   │   ├── user_status_service.py
│   │   │   ├── web_part_decision_engine.py
│   │   │   ├── webpart_index.py
│   │   │   ├── heft_compiler_service.py
│   │   │   └── sharepoint/               # Operation-specific service modules
│   │   │       ├── site_service.py
│   │   │       ├── list_service.py
│   │   │       ├── library_service.py
│   │   │       ├── page_service.py
│   │   │       ├── drive_service.py
│   │   │       ├── data_service.py
│   │   │       ├── enterprise_service.py
│   │   │       ├── permission_service.py
│   │   │       ├── search_service.py
│   │   │       └── webpart_reader_service.py
│   │   └── schemas/
│   │       ├── blueprint_schemas.py
│   │       ├── query_schemas.py
│   │       └── validation_schemas.py
│   │
│   └── presentation/                      # HTTP API layer
│       ├── api/
│       │   ├── router.py                  # Route aggregation
│       │   ├── dependencies.py            # FastAPI dependency providers
│       │   ├── routes/                    # Thin HTTP controllers
│       │   │   ├── chat_controller.py     # POST /chat/, POST /chat/upload
│       │   │   ├── file_controller.py     # POST /files/query
│       │   │   ├── library_controller.py  # POST /libraries/analyze
│       │   │   ├── provision_controller.py # POST /provision/
│       │   │   └── query_controller.py    # POST /query/
│       │   ├── orchestrators/             # Business logic orchestration
│       │   │   ├── chat_orchestrator.py
│       │   │   ├── site_orchestrator.py
│       │   │   ├── page_orchestrator.py
│       │   │   ├── item_orchestrator.py
│       │   │   ├── file_orchestrator.py
│       │   │   ├── library_orchestrator.py
│       │   │   ├── delete_orchestrator.py
│       │   │   ├── update_orchestrator.py
│       │   │   ├── permission_orchestrator.py
│       │   │   ├── enterprise_orchestrator.py
│       │   │   ├── analysis_orchestrator.py
│       │   │   └── orchestrator_utils.py
│       │   ├── intent/                    # Intent routing for presentation
│       │   │   ├── intent_router.py
│       │   │   ├── delete_intent.py
│       │   │   ├── item_intent.py
│       │   │   ├── page_intent.py
│       │   │   └── update_intent.py
│       │   ├── handlers/                  # Legacy intent-based handlers
│       │   ├── services/                  # Presentation-layer services
│       │   │   ├── clarification_service.py
│       │   │   ├── conversation_state.py
│       │   │   ├── library_matcher.py
│       │   │   ├── upload_service.py
│       │   │   └── validation_service.py
│       │   ├── utils/
│       │   │   ├── message_resolver.py
│       │   │   ├── prompt_builder.py
│       │   │   └── response_formatter.py
│       │   └── schemas/
│       │       └── chat_schemas.py
│       └── schemas/                       # Shared HTTP Pydantic models
│
├── data/
│   └── document_index/                    # Persisted document vector index
│
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## 🌐 API Endpoints

All endpoints require **Azure AD JWT** tokens via the `Authorization: Bearer <token>` header. Authentication uses the On-Behalf-Of (OBO) flow.

### Chat (Conversational AI Agent)

**POST** `/api/v1/chat/`

Send a natural language message. The agent classifies intent and routes to the appropriate orchestrator automatically.

```bash
curl -X POST http://localhost:8000/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <azure_ad_token>" \
  -d '{"message": "Create a project tasks list with status and due date columns", "site_id": "your-site-id"}'
```

**Response**:
```json
{
  "reply": "I have created the 'Project Tasks' list with Status and DueDate columns.",
  "session_id": "conv-abc123",
  "intent": "create_list"
}
```

### Chat File Upload

**POST** `/api/v1/chat/upload`

Upload files to SharePoint libraries via natural language.

```bash
curl -X POST http://localhost:8000/api/v1/chat/upload \
  -H "Authorization: Bearer <azure_ad_token>" \
  -F "file=@document.pdf" \
  -F "message=add to Documents library"
```

### Provision Resources

**POST** `/api/v1/provision/`

Directly provision SharePoint resources from a structured prompt.

```bash
curl -X POST http://localhost:8000/api/v1/provision/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <azure_ad_token>" \
  -d '{"prompt": "Create an HR document library with department and retention columns", "site_id": "your-site-id"}'
```

### Query Data

**POST** `/api/v1/query/`

Query SharePoint data with natural language.

```bash
curl -X POST http://localhost:8000/api/v1/query/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <azure_ad_token>" \
  -d '{"question": "Show me all tasks due this week with status Pending", "site_id": "your-site-id"}'
```

### File Operations

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/files/query` | Query and filter files via natural language |

### Library Analysis

**POST** `/api/v1/libraries/analyze` — Analyse a document library's metadata structure.

### Health Check

**GET** `/health` or `/api/v1/health`

Returns service health including Graph API, AI provider, and SharePoint site connectivity status.

```json
{
  "status": "healthy",
  "services": {
    "graph_api": "healthy",
    "ai_provider": "healthy",
    "sharepoint_site": "healthy"
  }
}
```

---

## 🎯 DDD / Clean Architecture Principles

### Separation of Concerns
- Each layer has a single, well-defined responsibility
- Layers communicate through well-defined interfaces
- Dependencies point **inward** — domain has zero external dependencies

### Dependency Inversion
- Domain defines repository/service **interfaces**
- Infrastructure **implements** those interfaces
- Application depends on abstractions, never concretions

### Controller → Orchestrator → Service (Presentation Layer)
- **Controllers** (`routes/`) are thin HTTP endpoints that handle request/response only
- **Orchestrators** contain the business logic coordination for each resource domain
- **Services** provide shared utilities (conversation state, validation, file upload)

### SOLID Principles
- **S** — Single Responsibility: one reason to change per class
- **O** — Open/Closed: extend via new implementations, not modification
- **L** — Liskov Substitution: all repository implementations are interchangeable
- **I** — Interface Segregation: small, focused repository interfaces per resource type
- **D** — Dependency Inversion: all cross-layer dependencies point toward abstractions

---

## 🔧 Design Patterns

| Pattern | Where Used |
|---------|------------|
| **Repository** | `domain/repositories/` → `infrastructure/repositories/` |
| **Use Case** | `application/use_cases/` — one class per operation |
| **Command** | `application/commands/` — encapsulate user intent |
| **DTO** | `application/dtos/` — decouple domain from HTTP |
| **Factory** | `ai_client_factory.py` — Gemini / VertexAI / OpenAI provider selection |
| **Strategy** | Provisioner classes per resource type |
| **Mixin** | Query intelligence sub-package (data, library, metadata, page) |
| **Detector** | `detection/` — pure-function NL pattern detectors with confidence scores |
| **Orchestrator** | `presentation/api/orchestrators/` — per-domain business logic coordination |
| **Registry** | `template_registry.py` |
| **Dependency Injection** | FastAPI `Depends()` + `dependencies.py` |
| **Middleware** | Correlation ID, User Identification, CORS |

---

## 🐳 Docker

### Docker Compose (recommended)

```bash
# Standard startup (includes Redis)
docker-compose up --build
```

The `docker-compose.yml` includes:
- `sharepoint-ai` — FastAPI application (Python 3.11)
- `redis` — Distributed state persistence (conversation state, security controls, rate limiting)

### Manual Docker

```bash
docker build -t sharepoint-ai .
docker run -p 8000:8000 --env-file .env sharepoint-ai
```

---

## ➕ Adding New Features

Follow these steps to add a new resource operation whilst preserving clean architecture:

### Example: Add "Archive List" Operation

**1. Domain** — add method to the list repository interface:
```python
# src/domain/repositories/list_repository.py
@abstractmethod
async def archive_list(self, list_id: str) -> bool: ...
```

**2. Detection** — add an operation detector if needed:
```python
# src/detection/operations/list_archive_detector.py
class ListArchiveDetector:
    def detect(self, text: str) -> DetectionResult: ...
```

**3. Infrastructure** — implement in `GraphAPISharePointRepository`:
```python
async def archive_list(self, list_id: str) -> bool:
    # Call Graph API
    ...
```

**4. Application** — create a use case:
```python
# src/application/use_cases/archive_list_use_case.py
class ArchiveListUseCase:
    def __init__(self, repo: ListRepository):
        self._repo = repo

    async def execute(self, command: ArchiveListCommand) -> ArchiveListResponseDTO:
        success = await self._repo.archive_list(command.list_id)
        return ArchiveListResponseDTO(success=success)
```

**5. Presentation** — add an orchestrator and wire to the controller or intent router.

---

## 🆘 Troubleshooting

### ModuleNotFoundError: No module named 'src'

Run from the `sharepoint_ai/` directory (where `src/` lives):
```bash
cd /path/to/sharepoint_ai
uvicorn src.main:app --reload
```

### ImportError or stale `.pyc` files

```bash
find . -type d -name __pycache__ -exec rm -r {} +
find . -type f -name "*.pyc" -delete
pip install -r requirements.txt --force-reinstall
```

### Authentication failures (Graph API)

This application uses **Azure AD On-Behalf-Of (OBO)** flow exclusively. Ensure:
- The Azure App Registration has the correct **delegated** permissions
- `TENANT_ID`, `CLIENT_ID`, and `CLIENT_SECRET` are set correctly
- The user token passed in the `Authorization` header is valid

Required Azure AD permissions:
- `Sites.FullControl.All`
- `Files.ReadWrite.All`
- `User.Read.All`

### AI provider not responding

- **Gemini**: verify `GEMINI_API_KEY` and model name (e.g. `gemini-2.0-flash`).
- **Vertex AI**: verify `VERTEXAI_PROJECT_ID`, `VERTEXAI_CLIENT_EMAIL`, and `VERTEXAI_PRIVATE_KEY`.
- **OpenAI-compatible** (Groq/Ollama): verify `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_MODEL`.

### Redis connection refused

If Redis is unavailable, the application falls back to in-memory storage automatically. Rate limits, auth state, and conversation history will not persist across restarts in this mode. A warning is logged at startup.

---

## 📚 Learn More

- **Domain-Driven Design** — Eric Evans
- **Clean Architecture** — Robert C. Martin
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Microsoft Graph API](https://learn.microsoft.com/en-us/graph/overview)
- [MSAL Python](https://github.com/AzureAD/microsoft-authentication-library-for-python)

---

**Last Updated**: May 2026
**Architecture**: Domain-Driven Design + Clean Architecture (5-Layer)
**Framework**: FastAPI + Pydantic
**Python Version**: 3.11+
**AI Providers**: Google Gemini, Vertex AI, OpenAI-compatible (Groq, Ollama)
