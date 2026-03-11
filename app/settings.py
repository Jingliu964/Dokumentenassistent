import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Model provider
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "ollama").lower()

# OpenAI (optional)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

# Ollama (local)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "llama3.1")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))

# RAG
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "5"))
RAG_CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "1000"))
RAG_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "200"))

# Storage
DATA_DIR = os.getenv("RAG_DATA_DIR", os.path.join(BASE_DIR, "data"))
TENANTS_DIR = os.getenv("RAG_TENANTS_DIR", os.path.join(DATA_DIR, "tenants"))
AUDIT_DB_PATH = os.getenv("AUDIT_DB_PATH", os.path.join(DATA_DIR, "audit", "audit.db"))

# Uploads
UPLOAD_MAX_MB = int(os.getenv("UPLOAD_MAX_MB", "25"))

# Auth & tenancy
AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "true").lower() == "true"
DEFAULT_TENANT = os.getenv("DEFAULT_TENANT", "public")
TENANT_API_KEYS = os.getenv("TENANT_API_KEYS", "")


@dataclass(frozen=True)
class ApiKeyInfo:
    tenant_id: str
    role: str


def _parse_tenant_api_keys(raw: str) -> dict[str, ApiKeyInfo]:
    mapping: dict[str, ApiKeyInfo] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = [part.strip() for part in entry.split(":")]
        if len(parts) < 2:
            continue
        tenant_id = parts[0]
        api_key = parts[1]
        role = parts[2].lower() if len(parts) >= 3 and parts[2] else "reader"
        mapping[api_key] = ApiKeyInfo(tenant_id=tenant_id, role=role)
    return mapping


API_KEY_INFO = _parse_tenant_api_keys(TENANT_API_KEYS)


@dataclass(frozen=True)
class TenantPaths:
    base_dir: str
    docs_dir: str
    uploads_dir: str
    index_dir: str
    faiss_path: str
    sqlite_path: str


def get_tenant_paths(tenant_id: str) -> TenantPaths:
    base_dir = os.path.join(TENANTS_DIR, tenant_id)
    docs_dir = os.path.join(base_dir, "docs")
    uploads_dir = os.path.join(base_dir, "uploads")
    index_dir = os.path.join(base_dir, "index")
    faiss_path = os.path.join(index_dir, "faiss.index")
    sqlite_path = os.path.join(index_dir, "metadata.db")
    return TenantPaths(
        base_dir=base_dir,
        docs_dir=docs_dir,
        uploads_dir=uploads_dir,
        index_dir=index_dir,
        faiss_path=faiss_path,
        sqlite_path=sqlite_path,
    )
