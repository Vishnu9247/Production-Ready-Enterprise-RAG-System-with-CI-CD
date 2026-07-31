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
8. Use a bounded LangGraph workflow to complete contextual questions, retrieve,
   deduplicate, rerank, and generate a grounded answer.
9. Store sessions and message history in PostgreSQL and mirror message
   embeddings into a separate Pinecone history namespace.

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
    agents/                   LangGraph query, retrieval, reranking, answer agents
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
`EMBEDDING_DIMENSIONS`. The configured chat deployment must support Azure
OpenAI structured outputs; `AZURE_OPENAI_API_VERSION=2024-10-21` is the
default.

Required secrets:

- `AZURE_OPENAI_API_KEY`
- `PINECONE_API_KEY`
- `POSTGRES_PASSWORD`
- One Blob credential only when managed identity is unavailable:
  `AZURE_STORAGE_CONNECTION_STRING`, `AZURE_STORAGE_ACCOUNT_KEY`, or
  `AZURE_STORAGE_SAS_TOKEN`

Important variables include `AZURE_OPENAI_ENDPOINT`, `PINECONE_HOST`,
`POSTGRES_HOST`, `POSTGRES_DATABASE`, `POSTGRES_USER`,
`AZURE_STORAGE_ACCOUNT_URL`, `AZURE_STORAGE_CONTAINER`,
`PINECONE_HISTORY_NAMESPACE`, and the history/reranking limits. See
`Backend/.env.example` for the complete list.

GitHub secrets are available only to workflows. The application reads runtime
configuration from environment variables, so a manually created Container App
must receive the same sensitive values as Azure Container Apps secrets (or
Key Vault references). Do not put any API key, database password, storage
credential, or service-principal credential in `Frontend/.env`; Vite variables
are delivered to the browser.

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
- `POST /v1/sessions` with `name` and `namespace`
- `GET /v1/sessions/{session_id}` with optional `limit`
- `POST /v1/query` with `session_id`, `query`, optional `top_k`,
  `metadata_filter`, `score_threshold`, and `search_mode` (`hybrid`, `semantic`,
  or `keyword`). The server uses the namespace assigned to the session.
- `POST /v1/search/keyword` with `query`, optional `top_k`, `namespace`, and
  `document_id`

## Frontend

The React frontend provides document upload, backend-managed sessions, queries,
and persisted session history. Copy `Frontend/.env.example` to `Frontend/.env`
and set `VITE_API_BASE_URL` to the backend URL. This URL is public
configuration and belongs in a GitHub variable if the frontend is built in CI;
it is not a secret.

```powershell
cd Frontend
npm install
npm run dev
```

For a deployed frontend, set `CORS_ALLOWED_ORIGINS` on the backend Container
App to the frontend origin. Multiple origins can be comma-separated.

Generated extraction artifacts are stored under `Backend/data/documents/` and
are intentionally ignored by Git.

The CI workflow uses an isolated PostgreSQL service container and does not
receive production cloud secrets.

## Build, push, and deploy the backend

The production GitHub workflow builds the backend Docker image, pushes both an
immutable commit tag and `latest` to Azure Container Registry, synchronizes
runtime secrets and variables to the existing Container App, and changes the
Container App image to the immutable tag. Azure Container Apps creates a new
revision for the deployment.

The relevant files are:

- `Dockerfile`: a non-root Python 3.12 production image.
- `Backend/rag_app/container.py`: initializes PostgreSQL and starts Uvicorn on
  port 8000.
- `.github/workflows/deploy-container-app.yml`: builds, pushes, configures, and
  deploys the backend.

### 1. Configure GitHub authentication

The workflow uses an Azure service principal stored in the protected GitHub
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
Assign the service principal:

- **AcrPush** on the `backendrag` registry;
- **Container Apps Contributor** on the existing Container App or its resource
  group; and
- **Reader** on resources the workflow must resolve.

Add these repository variables:

| GitHub variable | Example / purpose |
|---|---|
| `AZURE_CONTAINER_REGISTRY_NAME` | `backendrag` (not `backendrag.azurecr.io`) |
| `AZURE_RESOURCE_GROUP` | Resource group containing the Container App |
| `AZURE_CONTAINER_APP_NAME` | Existing backend Container App name |
| `CONTAINER_IMAGE_NAME` | Optional; defaults to `enterprise-rag-api` |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI resource endpoint |
| `AZURE_OPENAI_API_VERSION` | Optional; defaults to `2024-10-21` |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | Embedding deployment name |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | Chat deployment name |
| `EMBEDDING_DIMENSIONS` | Optional; defaults to `1536` |
| `PINECONE_HOST` | Existing Pinecone index host |
| `PINECONE_INDEX_NAME` | Optional; defaults to `enterprise-rag` |
| `PINECONE_NAMESPACE` | Optional; defaults to `default` |
| `PINECONE_HISTORY_NAMESPACE` | Optional; defaults to `conversation-history` |
| `PINECONE_CLOUD` | Optional; defaults to `aws` |
| `PINECONE_REGION` | Pinecone index region |
| `POSTGRES_HOST` | Azure PostgreSQL server host |
| `POSTGRES_PORT` | Optional; defaults to `5432` |
| `POSTGRES_DATABASE` | Database name |
| `POSTGRES_USER` | Database user |
| `POSTGRES_SSLMODE` | Optional; defaults to `require` |
| `OBJECT_STORAGE_PROVIDER` | Optional; defaults to `azure_blob` |
| `AZURE_STORAGE_ACCOUNT_URL` | Blob account URL |
| `AZURE_STORAGE_CONTAINER` | Blob container name |
| `AZURE_STORAGE_PREFIX` | Optional; defaults to `documents` |
| `CORS_ALLOWED_ORIGINS` | Frontend origins, comma-separated |

The chunking, retrieval, reranking, connection-pool, and history variables in
`Backend/.env.example` are optional repository variables. The workflow supplies
the documented defaults when they are absent.

Create these repository secrets:

- `AZURE_OPENAI_API_KEY`
- `PINECONE_API_KEY`
- `POSTGRES_PASSWORD`
- one optional Blob credential: `AZURE_STORAGE_CONNECTION_STRING`,
  `AZURE_STORAGE_ACCOUNT_KEY`, or `AZURE_STORAGE_SAS_TOKEN`

If no Blob credential is supplied, the backend uses the Container App managed
identity. That identity must have a Blob data role such as **Storage Blob Data
Contributor** on the storage account.

Secrets are written to the Container App secret store and exposed to the
container through `secretref:` environment references. They are not embedded
in the Docker image.

### 2. Build and push

The recommended production flow is:

1. Push your branch and open a pull request into `main`.
2. The **Backend CI** workflow tests the pull request. Pull requests do not
   push an image.
3. Merge the pull request into `main`.
4. **Backend CI** runs again for the merge commit.
5. When CI succeeds, **Build, Push, and Deploy Backend** builds that exact
   commit, pushes it to `backendrag.azurecr.io`, updates runtime configuration,
   and deploys a new Container App revision. A failed CI run does not deploy.

You can also use **Actions > Build, Push, and Deploy Backend > Run workflow**
and select `main`. Workflow dispatch builds and deploys the selected commit; it
is useful for the first deployment or a retry.

The workflow pushes two tags:

```text
backendrag.azurecr.io/enterprise-rag-api:<git-commit-sha>
backendrag.azurecr.io/enterprise-rag-api:latest
```

Prefer the commit SHA tag when manually creating a production revision because
it is immutable and makes rollback unambiguous.

### 3. One-time Container App prerequisites

The existing Container App must have:

- ingress target port `8000`;
- external ingress if the browser frontend will call it directly;
- a managed identity with **AcrPull** on `backendrag`, or an existing valid ACR
  registry configuration;
- PostgreSQL firewall/private-network access;
- Blob access through either the synchronized credential or managed identity.

The workflow sets `AUTO_INIT_DB=true`, so a deployment creates any missing
PostgreSQL tables before Uvicorn starts.

PostgreSQL must allow network traffic from the Container Apps environment. For
production, prefer private connectivity or a VNet with NAT Gateway rather than
allowing every Azure service.

### Start the frontend against the cloud backend

The frontend is intentionally separate from the backend container. To run it
locally against the deployed Container App:

```powershell
cd Frontend
$env:VITE_API_BASE_URL="https://<your-container-app-fqdn>"
npm install
npm run dev
```

Open `http://localhost:5173`. Set the backend repository variable
`CORS_ALLOWED_ORIGINS` to include `http://localhost:5173`; for example:

```text
http://localhost:5173,https://your-future-frontend.example.com
```

After changing `CORS_ALLOWED_ORIGINS`, run the deployment workflow again. The
frontend will then create sessions through `/v1/sessions`, send questions to
`/v1/query`, and load persisted history from `/v1/sessions/{session_id}`.

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
