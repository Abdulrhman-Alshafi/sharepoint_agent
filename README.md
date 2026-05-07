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
- [Testing](#testing)
- [Docker](#docker)
- [Adding New Features](#adding-new-features)
- [Troubleshooting](#troubleshooting)

---

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- pip or conda
- Azure AD credentials (Tenant ID, Client ID, Client Secret)
- A Gemini API key **or** an Ollama instance running locally
- (Optional) Redis — used for persistent conversation state
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
# AI provider (gemini | ollama)
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-1.5-flash

# API security
API_KEY=your_api_key

# Azure AD / Microsoft Graph
TENANT_ID=your_azure_tenant_id
CLIENT_ID=your_azure_client_id
CLIENT_SECRET=your_azure_client_secret

# SharePoint
SITE_ID=your_sharepoint_site_id
SHAREPOINT_BASE_URL=https://yourtenant.sharepoint.com

# Optional: Redis conversation state
REDIS_URL=redis://localhost:6379
```

### Running the Application

```bash
# Development server with auto-reload (run from sharepoint_ai/ directory)
uvicorn src.main:app --reload

# Production server
uvicorn src.main:app --host 0.0.0.0 --port 8000

# Or use the helper script
bash run_local.sh
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

### 4-Layer Clean Architecture

```
┌─────────────────────────────────────────┐
│   PRESENTATION LAYER                    │
│   HTTP Endpoints, Schemas, Handlers     │
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
| **Infrastructure** | External integrations | Graph API client, AI services, Repositories, Schemas | Domain, Application |
| **Presentation** | HTTP API | FastAPI routers, Request handlers, Response schemas | Application, Domain |

---

## 📁 Project Structure

```
sharepoint_ai/
├── src/
│   ├── main.py                            # FastAPI app factory + startup
│   │
│   ├── domain/                            # Pure business logic (no framework deps)
│   │   ├── entities/
│   │   │   ├── core.py                    # SPList, SPPage, ProvisioningBlueprint
│   │   │   ├── conversation.py            # Conversation / message entities
│   │   │   ├── document.py                # Document entities
│   │   │   ├── enterprise.py              # Enterprise site/hub entities
│   │   │   ├── preview.py                 # Blueprint preview entities
│   │   │   ├── query.py                   # Query result entities
│   │   │   ├── security.py                # Permission / security entities
│   │   │   └── templates.py               # Provisioning template entities
│   │   ├── value_objects/
│   │   │   └── resource_candidate.py      # Smart resource discovery candidates
│   │   ├── repositories/                  # Abstract repository interfaces
│   │   │   ├── list_repository.py
│   │   │   ├── page_repository.py
│   │   │   ├── library_repository.py
│   │   │   ├── site_repository.py
│   │   │   ├── permission_repository.py
│   │   │   ├── enterprise_repository.py
│   │   │   └── hub_site_registry.py
│   │   ├── services/                      # Domain service interfaces
│   │   │   ├── intent_classification.py
│   │   │   └── smart_resource_discovery.py
│   │   └── exceptions/                    # Domain exception hierarchy
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
│   │   │   └── provisioners/              # Dedicated provisioners per resource type
│   │   │       ├── site_provisioner.py
│   │   │       ├── list_provisioner.py
│   │   │       ├── page_provisioner.py
│   │   │       ├── library_provisioner.py
│   │   │       ├── group_provisioner.py
│   │   │       └── enterprise_provisioner.py
│   │   ├── services/
│   │   │   ├── audit_service.py           # Audit logging service
│   │   │   ├── governance_service.py      # Governance / policy enforcement
│   │   │   ├── requirement_gathering_service.py  # Multi-turn requirement gathering
│   │   │   ├── smart_question_service.py  # Dynamic clarifying questions
│   │   │   ├── question_templates.py      # Reusable question templates
│   │   │   └── template_registry.py       # Provisioning template registry
│   │   ├── commands/                      # Command objects (user intentions)
│   │   ├── converters/                    # Domain <-> DTO converters
│   │   └── dtos/                          # Data transfer objects
│   │
│   ├── infrastructure/                    # External integrations
│   │   ├── config.py                      # Settings (pydantic BaseSettings)
│   │   ├── graph_service.py               # Low-level Graph API entry point
│   │   ├── rate_limiter.py                # Request rate limiting
│   │   ├── logging.py                     # Structured logging setup
│   │   ├── external_services/             # AI parsers & intelligence services
│   │   │   ├── ai_blueprint_generator.py  # Gemini/Ollama blueprint generation
│   │   │   ├── ai_client_factory.py       # AI provider factory (Gemini / Ollama)
│   │   │   ├── ai_data_query_service.py   # AI-powered data querying
│   │   │   ├── ai_intent_classification.py # NL intent -> operation type
│   │   │   ├── document_intelligence.py   # Document understanding
│   │   │   ├── library_intelligence.py    # Library analysis intelligence
│   │   │   ├── query_intelligence.py      # Query result analysis
│   │   │   ├── site_resolver.py           # Fuzzy site name resolution
│   │   │   ├── enterprise_operation_parser.py
│   │   │   ├── file_operation_parser.py
│   │   │   ├── hub_site_operation_parser.py
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
│   │   │       ├── hub_mixin.py
│   │   │       ├── library_mixin.py
│   │   │       └── metadata_mixin.py
│   │   ├── repositories/                  # Repository implementations
│   │   │   ├── graph_sharepoint_repository.py
│   │   │   ├── conversation_state_repository.py    # In-memory conversation state
│   │   │   ├── redis_conversation_state_repository.py  # Redis-backed conversation state
│   │   │   └── utils/                     # Graph API helpers
│   │   │       ├── canvas_builder.py
│   │   │       ├── canvas_editor.py
│   │   │       ├── payload_builders.py
│   │   │       ├── url_helpers.py
│   │   │       ├── error_handlers.py
│   │   │       └── constants.py
│   │   ├── services/                      # Infrastructure service implementations
│   │   │   ├── authentication_service.py  # MSAL token acquisition
│   │   │   ├── base_api_client.py         # Shared HTTP client base class
│   │   │   ├── graph_api_client.py        # Microsoft Graph API client
│   │   │   ├── rest_api_client.py         # SharePoint REST API client
│   │   │   ├── batch_operations_service.py # Graph API $batch requests
│   │   │   ├── cache_service.py           # In-memory / TTL cache
│   │   │   ├── content_analyzer.py        # Content analysis utilities
│   │   │   ├── document_index.py          # Document vector index
│   │   │   ├── document_parser.py         # File parsing (PDF, DOCX, etc.)
│   │   │   ├── duplicate_name_resolver.py # Resolve name collisions
│   │   │   ├── field_validator.py         # SharePoint field validation
│   │   │   ├── hub_site_registry_service.py # Hub site registry
│   │   │   ├── input_sanitizer.py         # Input sanitization & XSS prevention
│   │   │   ├── smart_resource_discovery.py # NL -> resource lookup
│   │   │   ├── token_validation_service.py # API key / JWT validation
│   │   │   ├── web_part_decision_engine.py # Web part selection logic
│   │   │   ├── heft_compiler_service.py   # HEFT build integration
│   │   │   └── sharepoint/               # Operation-specific service modules
│   │   │       ├── site_service.py
│   │   │       ├── list_service.py
│   │   │       ├── library_service.py
│   │   │       ├── page_service.py
│   │   │       ├── drive_service.py
│   │   │       ├── data_service.py
│   │   │       ├── enterprise_service.py
│   │   │       ├── permission_service.py
│   │   │       └── search_service.py
│   │   └── schemas/                       # Pydantic schemas for infra payloads
│   │       ├── blueprint_schemas.py
│   │       ├── query_schemas.py
│   │       └── validation_schemas.py
│   │
│   └── presentation/                      # HTTP API layer
│       ├── api/
│       │   ├── router.py                  # Route aggregation
│       │   ├── dependencies.py            # FastAPI dependency providers
│       │   ├── provision.py               # POST /api/v1/provision/
│       │   ├── chat.py                    # POST /api/v1/chat/
│       │   ├── query.py                   # POST /api/v1/query/
│       │   ├── files.py                   # File upload / download endpoints
│       │   ├── library_analysis.py        # Library analysis endpoints
│       │   ├── handlers/                  # Intent-based request handlers
│       │   │   ├── site_handler.py
│       │   │   ├── item_handler.py
│       │   │   ├── library_handler.py
│       │   │   ├── page_handler.py
│       │   │   ├── file_handler.py
│       │   │   ├── permission_handler.py
│       │   │   ├── enterprise_handler.py
│       │   │   ├── hub_site_handler.py
│       │   │   ├── analysis_handler.py
│       │   │   ├── delete_handler.py
│       │   │   ├── update_handler.py
│       │   │   └── handler_utils.py
│       │   ├── utils/
│       │   │   ├── message_resolver.py
│       │   │   ├── prompt_builder.py
│       │   │   └── response_formatter.py
│       │   └── schemas/
│       │       └── chat_schemas.py
│       └── schemas/                       # HTTP request/response Pydantic models
│
├── tests/
│   ├── conftest.py                        # Shared fixtures & mocks
│   ├── domain_test.py                     # Domain entity / logic tests
│   ├── application_test.py                # Use case tests (mocked repos)
│   ├── integration_test.py                # Endpoint integration tests
│   ├── test_handlers.py                   # Presentation handler tests
│   ├── test_list_item_operations.py       # List item CRUD tests
│   ├── test_rate_limiting.py              # Rate limiter tests
│   ├── test_site_service.py               # Site service tests
│   └── application/ domain/ infrastructure/ integration/ presentation/
│
├── data/
│   └── document_index/                    # Persisted document vector index
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pytest.ini
├── run_local.sh
├── run_docker_with_ollama.sh
├── restart_server.sh
└── restart_docker.sh
```

---

## 🌐 API Endpoints

### Chat (Conversational AI Agent)

**POST** `/api/v1/chat/`

Send a natural language message. The agent classifies intent and routes to the appropriate handler automatically.

```bash
curl -X POST http://localhost:8000/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{"message": "Create a project tasks list with status and due date columns"}'
```

**Response**:
```json
{
  "response": "I have created the 'Project Tasks' list with Status and DueDate columns.",
  "conversation_id": "conv-abc123",
  "intent": "create_list",
  "actions_taken": []
}
```

### Provision Resources

**POST** `/api/v1/provision/`

Directly provision SharePoint resources from a structured prompt.

```bash
curl -X POST http://localhost:8000/api/v1/provision/ \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Create an HR document library with department and retention columns"}'
```

**Response**:
```json
{
  "blueprint": {
    "reasoning": "...",
    "lists": [...],
    "pages": [...]
  },
  "created_lists": [...],
  "created_pages": [...]
}
```

### Query Data

**POST** `/api/v1/query/`

Query SharePoint data with natural language.

```bash
curl -X POST http://localhost:8000/api/v1/query/ \
  -H "Content-Type: application/json" \
  -d '{"query": "Show me all tasks due this week with status Pending"}'
```

### File Operations

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/files/upload/` | Upload a file to a library |
| GET | `/api/v1/files/{drive_id}/{item_id}` | Download a file |

### Library Analysis

**GET** `/api/v1/library-analysis/{library_name}` — Analyse a document library's structure and contents.

### Health Check

**GET** `/health`

```json
{"status": "healthy"}
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

### Testability
- Pure domain logic tested without any external dependencies
- Repository pattern enables clean mock implementations
- Use cases tested with injected mocks

### SOLID Principles
- **S** — Single Responsibility: one reason to change per class
- **O** — Open/Closed: extend via new implementations, not modification
- **L** — Liskov Substitution: all repository implementations are interchangeable
- **I** — Interface Segregation: small, focused repository interfaces per resource type
- **D** — Dependency Inversion: all cross-layer dependencies point toward abstractions

---

## 🔧 Design Patterns

| Pattern | Where Used |
|---------|-----------|
| **Repository** | `domain/repositories/` → `infrastructure/repositories/` |
| **Use Case** | `application/use_cases/` — one class per operation |
| **Command** | `application/commands/` — encapsulate user intent |
| **DTO** | `application/dtos/` — decouple domain from HTTP |
| **Factory** | `ai_client_factory.py` — Gemini / Ollama provider selection |
| **Strategy** | Provisioner classes per resource type |
| **Mixin** | Query intelligence sub-package |
| **Registry** | `template_registry.py`, `hub_site_registry_service.py` |
| **Dependency Injection** | FastAPI `Depends()` + `dependencies.py` |

---

## 🧪 Testing

### Test Pyramid

```
tests/integration_test.py         <- Full HTTP flow (mocked AI/Graph)
tests/test_handlers.py            <- Presentation handler tests
tests/application_test.py         <- Use case tests (mocked repos)
tests/domain_test.py              <- Pure domain logic (no mocking)
tests/test_list_item_operations.py
tests/test_rate_limiting.py
tests/test_site_service.py
```

### Running Tests

```bash
# All tests
pytest tests/ -v

# Single layer
pytest tests/domain_test.py -v
pytest tests/application_test.py -v
pytest tests/integration_test.py -v

# With coverage
pytest tests/ --cov=src --cov-report=html

# Pattern filter
pytest tests/ -k "list" -v
```

### Shared Fixtures (`tests/conftest.py`)

- `mock_sharepoint_repo` — async mock of `GraphAPISharePointRepository`
- `mock_ai_generator` — async mock of `AIBlueprintGenerator`
- `test_client` — FastAPI `TestClient` with overridden dependencies

---

## 🐳 Docker

### Docker Compose (recommended)

```bash
# Standard startup
docker-compose up --build

# With Ollama (local LLM)
bash run_docker_with_ollama.sh
```

The `docker-compose.yml` includes:
- `api` — FastAPI application
- `redis` — conversation state persistence (optional profile)
- Ollama profile — local LLM support

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

**2. Infrastructure** — implement in `GraphAPISharePointRepository`:
```python
async def archive_list(self, list_id: str) -> bool:
    # Call Graph API
    ...
```

**3. Application** — create a use case:
```python
# src/application/use_cases/archive_list_use_case.py
class ArchiveListUseCase:
    def __init__(self, repo: ListRepository):
        self._repo = repo

    async def execute(self, command: ArchiveListCommand) -> ArchiveListResponseDTO:
        success = await self._repo.archive_list(command.list_id)
        return ArchiveListResponseDTO(success=success)
```

**4. Presentation** — wire up to the relevant handler or add a new endpoint.

**5. Tests** — add tests at each layer.

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

```python
from src.infrastructure.config import settings
print(settings.TENANT_ID, settings.CLIENT_ID)  # Must not be empty
```

Ensure the Azure App Registration has the following **application** permissions:
- `Sites.FullControl.All`
- `Files.ReadWrite.All`
- `User.Read.All`

### AI provider not responding

- **Gemini**: verify `GEMINI_API_KEY` and model name (e.g. `gemini-1.5-flash`).
- **Ollama**: ensure Ollama is running (`ollama serve`) and the model is pulled (`ollama pull llama3`).

### Redis connection refused

If persistent conversation state is not needed, the application falls back to an in-memory store automatically. Set `REDIS_URL=` (empty) to disable Redis explicitly.

---

## 📚 Learn More

- **Domain-Driven Design** — Eric Evans
- **Clean Architecture** — Robert C. Martin
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Microsoft Graph API](https://learn.microsoft.com/en-us/graph/overview)
- [MSAL Python](https://github.com/AzureAD/microsoft-authentication-library-for-python)

---

**Last Updated**: April 2026  
**Architecture**: Domain-Driven Design + Clean Architecture  
**Framework**: FastAPI + Pydantic  
**Python Version**: 3.9+  
**AI Providers**: Google Gemini, Ollama (local)
