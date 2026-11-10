import os


def _list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


DATABASE_URL = os.environ.get("DATABASE_URL", "")
CORS_ORIGINS = _list(os.environ.get("CORS_ORIGINS", "http://localhost:3000"))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_EMBED_MODEL = os.environ.get("GEMINI_EMBED_MODEL", "gemini-embedding-001")
