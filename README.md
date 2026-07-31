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
receive production cloud secrets.

## Build and push the container image

The GitHub workflow only builds the Docker image and pushes it to Azure
Container Registry. It does not create, update, or restart a Container App, and
it does not copy application runtime secrets into Azure.

The relevant files are:

- `Dockerfile`: a non-root Python 3.12 production image.
- `Backend/rag_app/container.py`: initializes PostgreSQL and starts Uvicorn on
  port 8000.
- `.github/workflows/build-push-acr.yml`: builds and pushes the image to
  `backendrag.azurecr.io`.

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
Assign the service principal **AcrPush** and **Reader** on the `backendrag`
registry. It does not need permission to modify Container Apps.

Add this repository variable:

| GitHub variable | Example |
|---|---|
| `AZURE_CONTAINER_REGISTRY_NAME` | `backendrag` (not `backendrag.azurecr.io`) |

`AZURE_RESOURCE_GROUP` and all `AZURE_CONTAINER_APP_*` variables are not used
by this workflow. Existing repository application secrets may remain in
GitHub, but they are not embedded in the image or sent to Container Apps.

### 2. Build and push

The recommended production flow is:

1. Push your branch and open a pull request into `main`.
2. The **Backend CI** workflow tests the pull request. Pull requests do not
   push an image.
3. Merge the pull request into `main`.
4. **Backend CI** runs again for the merge commit.
5. When CI succeeds, **Build and Push Backend Image to ACR** builds that exact
   commit and pushes it to `backendrag.azurecr.io`. A failed CI run does not
   push an image.

You can also use **Actions > Build and Push Backend Image to ACR > Run
workflow** and select `main`. Workflow dispatch is useful for the first build
or for retrying without another commit.

The workflow pushes two tags:

```text
backendrag.azurecr.io/enterprise-rag-api:<git-commit-sha>
backendrag.azurecr.io/enterprise-rag-api:latest
```

Prefer the commit SHA tag when manually creating a production revision because
it is immutable and makes rollback unambiguous.

### 3. Create or update Container Apps manually

In the Azure portal, select the image from the `backendrag` registry and
configure:

- container target port `8000`;
- external or internal ingress as required;
- `AUTO_INIT_DB=true`;
- the application variables and secret references listed in
  `Backend/.env.example`;
- a managed identity with **AcrPull** on `backendrag`.

Repository secrets are not automatically available to a manually configured
Container App. Add them as Container Apps secrets in Azure.

PostgreSQL must also allow network traffic from the Container Apps environment.
For production, prefer private connectivity or a VNet with NAT Gateway rather
than allowing every Azure service.

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
