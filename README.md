# Production-Ready Enterprise RAG System

The backend implements a PDF RAG pipeline using Docling, Azure OpenAI,
Azure Blob Storage, PostgreSQL, and Pinecone:

1. Extract PDF text, headings, tables, images, page numbers, and bounding boxes.
2. Build deterministic, structure-aware chunks with source metadata.
3. Create embeddings in batches with an Azure OpenAI embedding deployment.
4. Store original PDFs in Azure Blob Storage.
5. Store document records and authoritative chunk text in PostgreSQL.
6. Upsert embeddings into an existing Pinecone host or create an index by name.
7. Fuse Pinecone semantic search with PostgreSQL full-text keyword search.
8. Generate a grounded Azure OpenAI answer with citations.

## Backend layout

```text
Backend/
  data/
    source_documents/        Local PDFs (Git-ignored)
    documents/               Extracted document artifacts (Git-ignored)
  rag_app/
    api.py                    FastAPI application assembly
    cli.py                    Local commands
    core/                     Configuration, shared schemas, exceptions
    document_extraction/      Docling extraction and structure-aware chunking
    document_storage/         Azure Blob and local document storage
    database/                 PostgreSQL models, sessions, and keyword search
    embedding_generation/     Azure OpenAI embeddings and chat completions
    vector_store_operations/  Pinecone index and vector operations
    retrieval/                Semantic/keyword reciprocal-rank fusion
    rag_pipeline/             Ingestion/query orchestration and use cases
    routing/                  Thin FastAPI endpoint adapters only
  tests/
```

`pyproject.toml` is the single dependency manifest. The duplicate backend
`requirements.txt` and the old compatibility wrapper packages were removed.

## Configure

Copy `Backend/.env.example` to `Backend/.env` for local development. In GitHub,
map protected environment secrets and variables to the same uppercase names.
Deployment variables must be Azure deployment names, which may differ from the
underlying model names. The Pinecone index dimension must equal
`EMBEDDING_DIMENSIONS`.

Required secrets:

- `AZURE_OPENAI_API_KEY`
- `PINECONE_API_KEY`
- `POSTGRES_PASSWORD`
- One Blob credential only when managed identity is unavailable:
  `AZURE_STORAGE_CONNECTION_STRING`, `AZURE_STORAGE_ACCOUNT_KEY`, or
  `AZURE_STORAGE_SAS_TOKEN`

Important variables include `AZURE_OPENAI_ENDPOINT`, `PINECONE_HOST`,
`POSTGRES_HOST`, `POSTGRES_DATABASE`, `POSTGRES_USER`,
`AZURE_STORAGE_ACCOUNT_URL`, and `AZURE_STORAGE_CONTAINER`. See
`Backend/.env.example` for the complete list.

The Azure API key that was previously stored in `embedding.ipynb` must be
revoked and regenerated before this application is used.

## Run

From the repository root:

```powershell
uv sync
uv run python -m Backend.rag_app.cli init-db
uv run python -m Backend.rag_app.cli init-index
uv run python -m Backend.rag_app.cli ingest "Backend/data/source_documents/10-Q4-2024-As-Filed.pdf"
uv run python -m Backend.rag_app.cli query "What is this document about?"
uv run python -m Backend.rag_app.cli keyword-search "revenue growth"
uv run uvicorn Backend.rag_app.api:app --reload
```

For a local PostgreSQL instance:

```powershell
docker compose up -d postgres
$env:POSTGRES_HOST="localhost"
$env:POSTGRES_PORT="5432"
$env:POSTGRES_DATABASE="rag_db"
$env:POSTGRES_USER="rag_app"
$env:POSTGRES_PASSWORD="local-rag-password"
$env:POSTGRES_SSLMODE="disable"
uv run python -m Backend.rag_app.cli init-db
```

API endpoints:

- `GET /health`
- `POST /v1/documents` with a PDF multipart upload and optional `namespace`
- `POST /v1/query` with `question`, optional `top_k`, `namespace`,
  `metadata_filter`, `score_threshold`, and `search_mode` (`hybrid`, `semantic`,
  or `keyword`)
- `POST /v1/search/keyword` with `query`, optional `top_k`, `namespace`, and
  `document_id`

Generated extraction artifacts are stored under `Backend/data/documents/` and
are intentionally ignored by Git.

The CI workflow uses an isolated PostgreSQL service container and does not
receive production cloud secrets. A deployment workflow should declare a
protected GitHub environment and explicitly map its `secrets` and `vars` into
the application runtime.

## Deploy to Azure Container Apps

The repository includes:

- `Dockerfile`: a non-root Python 3.12 production image.
- `Backend/rag_app/container.py`: initializes the PostgreSQL schema and starts
  Uvicorn on port 8000.
- `Infrastructure/azure/bootstrap-container-app.ps1`: creates the resource
  group, Azure Container Registry, Container Apps environment, and initial
  Container App. The app uses its managed identity to pull from ACR.
- `.github/workflows/deploy-container-app.yml`: builds and pushes an immutable
  image tagged with the Git commit, deploys it, maps GitHub secrets into
  Container Apps secrets, and verifies `/health`.

### 1. Create the Azure infrastructure once

Install Azure CLI and Docker Desktop, then run from PowerShell:

```powershell
az login
.\Infrastructure\azure\bootstrap-container-app.ps1 `
  -SubscriptionId "<subscription-id>" `
  -ResourceGroup "rg-enterprise-rag-prod" `
  -Location "eastus" `
  -RegistryName "backendrag" `
  -ContainerAppsEnvironment "cae-enterprise-rag-prod" `
  -ContainerAppName "ca-enterprise-rag-api"
```

Azure Container Registry names must be globally unique and contain only
letters and numbers.

### 2. Configure GitHub-to-Azure authentication

The deployment uses an Azure service principal stored in the protected GitHub
environment named exactly `Production`.

Create this **environment secret**:

```text
Name: AZURE_CREDENTIALS
Value:
{
  "clientId": "<service-principal-application-client-id>",
  "clientSecret": "<service-principal-client-secret-value>",
  "subscriptionId": "<azure-subscription-id>",
  "tenantId": "<microsoft-entra-tenant-id>"
}
```

Use the service principal client secret **value**, not the Azure secret ID.
Assign the service principal **Contributor** on the Container App resource
group and **AcrPush** on the `backendrag` registry. The Container App uses its
own managed identity with **AcrPull**.

All application settings can remain in repository-level GitHub variables and
secrets. Environment-level values with the same name take precedence.

Add these deployment variables at repository level:

| GitHub variable | Example |
|---|---|
| `AZURE_RESOURCE_GROUP` | `rg-enterprise-rag-prod` |
| `AZURE_CONTAINER_REGISTRY_NAME` | `backendrag` (not `backendrag.azurecr.io`) |
| `AZURE_CONTAINER_APP_ENVIRONMENT` | `cae-enterprise-rag-prod` |
| `AZURE_CONTAINER_APP_NAME` | `ca-enterprise-rag-api` |
| `AZURE_CONTAINER_APP_MIN_REPLICAS` | `1` |
| `AZURE_CONTAINER_APP_MAX_REPLICAS` | `3` |
| `AZURE_CONTAINER_APP_CPU` | `1.0` |
| `AZURE_CONTAINER_APP_MEMORY` | `2.0Gi` |

Keep all application variables and secrets listed in the **Configure** section
at repository level. Store `AZURE_CREDENTIALS` in the `Production` environment
because it authorizes production deployment.

### 3. Configure PostgreSQL networking

The starter Container Apps environment uses Azure-managed public networking.
Its outbound IP addresses can change. A PostgreSQL Flexible Server that only
allows your laptop's IP will therefore reject the container.

For a temporary first launch, the PostgreSQL Networking page can enable
**Allow public access from any Azure service within Azure**. This is broad
access at the network layer, so keep strong database credentials and remove
the rule after testing.

For production, create the Container Apps environment in your own VNet and use
either:

- private connectivity to PostgreSQL, or
- a NAT Gateway with one static outbound IP and allow only that IP in the
  PostgreSQL firewall.

An environment's network type cannot be changed after creation, so choose the
VNet design before putting real data into production.

### 4. Deploy

The recommended production flow is:

1. Push your branch and open a pull request into `main`.
2. The **Backend CI** workflow tests the pull request. Pull requests do not
   deploy.
3. Merge the pull request into `main`.
4. **Backend CI** runs again for the merge commit.
5. When CI succeeds, **Deploy Backend to Azure Container Apps** automatically
   builds that exact commit, pushes it to `backendrag.azurecr.io`, and deploys
   it. A failed CI run does not deploy.

For the very first launch, after the deployment files are present on GitHub,
you may instead open **Actions > Deploy Backend to Azure Container Apps > Run
workflow** and select the `main` branch. Workflow dispatch is also useful for
retrying a deployment without creating another commit.

Do not run a production workflow dispatch from a feature branch unless you
intentionally want that branch deployed. The protected `Production`
environment can be configured to require approval as an additional safeguard.

When the workflow succeeds, its health-check step prints:

```text
Application URL: https://<app-fqdn>
Swagger UI: https://<app-fqdn>/docs
```

The deployment starts with one replica because PDF extraction can be slow and
the first request should not pay a cold-start penalty. Each image starts as a
non-root user. The workflow stores API keys and passwords as Container Apps
secrets and exposes them to the process only through secret references.

### Local Docker smoke test

After creating `Backend/.env`, run:

```powershell
docker build -t enterprise-rag-api:local .
docker run --rm -p 8000:8000 --env-file Backend/.env `
  -e AUTO_INIT_DB=true enterprise-rag-api:local
```

Then open `http://localhost:8000/docs`.

The current external endpoint has no application authentication. Do not upload
sensitive documents until authentication and authorization are added.
