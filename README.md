# RAG App (FastAPI + FAISS + SQLite + Ollama)

A local-first Retrieval-Augmented Generation (RAG) service built with FastAPI, FAISS, and SQLite.
Includes multi-tenant isolation, API key auth with roles, audit logging, and file upload (pdf/docx/pptx).

## Quickstart

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Run a local model (Ollama):

```bash
# example models
ollama pull llama3.1
ollama pull nomic-embed-text
```

3. Configure environment:

```bash
cp .env.example .env
# edit .env and set TENANT_API_KEYS + local model settings
```

4. Put your documents in `data/tenants/<tenant>/docs` (`.txt` or `.md`) or upload via the UI.
   - Example: if `TENANT_API_KEYS=acme:...`, the docs folder is `data/tenants/acme/docs`.

5. Run the API:

```bash
uvicorn app.main:app --reload
```

Open the UI at `http://127.0.0.1:8000/`.

6. Upload documents:

```bash
curl -X POST "http://127.0.0.1:8000/upload" \
  -H "X-API-Key: <your-key>" \
  -F "files=@/path/to/handbook.pdf"
```

7. Ingest documents:

```bash
curl -X POST "http://127.0.0.1:8000/ingest" \
  -H "X-API-Key: <your-key>"
```

8. Ask a question:

```bash
curl -X POST "http://127.0.0.1:8000/query" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-key>" \
  -d '{"question": "What is this project about?"}'
```

## Notes

- Set `rebuild=true` on `/ingest` to reset the index for the current tenant.
- Upload supports `.txt`, `.md`, `.pdf`, `.docx`, `.pptx`.
- Audit logs are stored in `data/audit/audit.db`.
- Optional: include `X-User` header to record user identity in audit logs.
- Roles: `reader` can query, `editor` can upload/ingest, `admin` is full access.
- To use OpenAI instead of local models, set `MODEL_PROVIDER=openai` and `OPENAI_API_KEY`.
# rag-prototype
# rag-prototype
# rag-prototype
