import os
import time
import uuid

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .auth import require_tenant, require_role, TenantContext
from .audit import log_event
from .loaders import SUPPORTED_EXTENSIONS
from .schemas import IngestResponse, QueryRequest, QueryResponse, Citation, UploadResponse
from .rag import ingest_documents, query_rag, rebuild_index
from .settings import UPLOAD_MAX_MB, get_tenant_paths

app = FastAPI(title="RAG App", version="0.1.0")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ingest", response_model=IngestResponse)
def ingest(
    request: Request,
    rebuild: bool = False,
    ctx: TenantContext = Depends(require_tenant),
):
    require_role(ctx, "editor")
    start = time.monotonic()
    request_id = _request_id(request)
    ip = request.client.host if request and request.client else None
    try:
        if rebuild:
            rebuild_index(ctx.tenant_id)
        files, chunks = ingest_documents(ctx.tenant_id)
        log_event(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            role=ctx.role,
            action="ingest",
            status="ok",
            detail={"files_processed": files, "chunks_added": chunks, "rebuild": rebuild},
            latency_ms=_latency_ms(start),
            request_id=request_id,
            ip=ip,
        )
        return IngestResponse(files_processed=files, chunks_added=chunks)
    except Exception as exc:  # pragma: no cover - safety net
        log_event(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            role=ctx.role,
            action="ingest",
            status="error",
            detail={"error": str(exc)},
            latency_ms=_latency_ms(start),
            request_id=request_id,
            ip=ip,
        )
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/query", response_model=QueryResponse)
def query(
    request: Request,
    req: QueryRequest,
    ctx: TenantContext = Depends(require_tenant),
):
    require_role(ctx, "reader")
    start = time.monotonic()
    request_id = _request_id(request)
    ip = request.client.host if request and request.client else None
    try:
        answer, citations = query_rag(ctx.tenant_id, req.question, req.top_k)
        citation_models = [Citation(source=s, chunk_id=c) for s, c in citations]
        log_event(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            role=ctx.role,
            action="query",
            status="ok",
            detail={"top_k": req.top_k, "question_len": len(req.question)},
            latency_ms=_latency_ms(start),
            request_id=request_id,
            ip=ip,
        )
        return QueryResponse(answer=answer, citations=citation_models)
    except RuntimeError as exc:
        log_event(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            role=ctx.role,
            action="query",
            status="error",
            detail={"error": str(exc)},
            latency_ms=_latency_ms(start),
            request_id=request_id,
            ip=ip,
        )
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # pragma: no cover - safety net
        log_event(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            role=ctx.role,
            action="query",
            status="error",
            detail={"error": str(exc)},
            latency_ms=_latency_ms(start),
            request_id=request_id,
            ip=ip,
        )
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/upload", response_model=UploadResponse)
def upload_files(
    request: Request,
    files: list[UploadFile] = File(...),
    ctx: TenantContext = Depends(require_tenant),
):
    require_role(ctx, "editor")
    start = time.monotonic()
    request_id = _request_id(request)
    ip = request.client.host if request and request.client else None
    paths = get_tenant_paths(ctx.tenant_id)
    os.makedirs(paths.uploads_dir, exist_ok=True)

    saved = 0
    failures: list[str] = []
    max_bytes = UPLOAD_MAX_MB * 1024 * 1024

    for file in files:
        original_name = file.filename or "upload"
        safe_name = os.path.basename(original_name)
        ext = os.path.splitext(safe_name)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            failures.append(f"{safe_name}: unsupported file type")
            continue

        stem = os.path.splitext(safe_name)[0] or "upload"
        unique_name = f"{stem}-{uuid.uuid4().hex}{ext}"
        target_path = os.path.join(paths.uploads_dir, unique_name)

        try:
            _save_upload(file, target_path, max_bytes)
            saved += 1
        except ValueError as exc:
            failures.append(f"{safe_name}: {exc}")
        except Exception as exc:  # pragma: no cover - safety net
            failures.append(f"{safe_name}: {exc}")

    if failures and saved > 0:
        status = "partial"
    elif failures:
        status = "error"
    else:
        status = "ok"
    log_event(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        role=ctx.role,
        action="upload",
        status=status,
        detail={"files_saved": saved, "files_failed": len(failures)},
        latency_ms=_latency_ms(start),
        request_id=request_id,
        ip=ip,
    )

    return UploadResponse(files_saved=saved, files_failed=len(failures), failures=failures)


def _save_upload(file: UploadFile, target_path: str, max_bytes: int) -> None:
    size = 0
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    try:
        with open(target_path, "wb") as out:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError(f"file exceeds {UPLOAD_MAX_MB} MB limit")
                out.write(chunk)
    except Exception:
        if os.path.exists(target_path):
            os.remove(target_path)
        raise
    finally:
        try:
            file.file.close()
        except Exception:
            pass


def _request_id(request: Request | None) -> str:
    if not request:
        return str(uuid.uuid4())
    return request.headers.get("X-Request-Id") or str(uuid.uuid4())


def _latency_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)
