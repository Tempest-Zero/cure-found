"""CureFound application Settings.

Pattern cribbed from full-stack-fastapi-template's `core/config.py`:
a single `Settings(BaseSettings)` class, loaded from `.env` at the
project root, with computed fields and a post-init validator that
fails loud on unsafe defaults outside local dev.

Why one class (not per-domain AuthConfig + RepurposeConfig as
zhanymkanov suggests): this project has one deployment surface
(uvicorn + optional Neo4j). Splitting by domain would double the
boilerplate without meaningfully isolating failure modes. When
Phase 5+ adds NER / embeddings services with their own credentials,
revisit.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import AnyUrl, BeforeValidator, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import (
    ARTIFACTS_DIR as _ARTIFACTS_DIR_DEFAULT,
)
from app.core.paths import (
    DATA_DIR as _DATA_DIR_DEFAULT,
)
from app.core.paths import (
    PROJECT_ROOT,
    resolve_project_path,
)
from app.core.paths import (
    RAW_DIR as _RAW_DIR_DEFAULT,
)
from app.core.paths import (
    SEED_KG_PATH as _SEED_KG_DEFAULT,
)


def _parse_cors(value: Any) -> list[str] | str:
    """Accept either a comma-separated string or a JSON-style list for
    BACKEND_CORS_ORIGINS. `.env` values are always strings, so the
    common path is the comma-split branch; Pydantic's own JSON parser
    is kept as a fallback so unit tests can pass a real list.
    """
    if isinstance(value, str) and not value.startswith("["):
        return [v.strip() for v in value.split(",") if v.strip()]
    if isinstance(value, (list, str)):
        return value
    raise ValueError(f"cannot parse CORS origins from {value!r}")


# Sentinel placeholders that must not survive into a non-local environment.
# Mirrors full-stack-fastapi-template's "changethis" guard.


class Settings(BaseSettings):
    """Runtime configuration. Read from `.env` at repo root + environ."""

    model_config = SettingsConfigDict(
        # `.env` sits next to `curefound/pyproject.toml`, i.e. the project root.
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- Runtime --------------------------------------------------------
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"
    PROJECT_NAME: str = "CureFound"
    API_V1_STR: str = "/api/v1"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # --- CORS -----------------------------------------------------------
    # Default matches the local dev surface (same-origin frontend + Vite
    # standalone + UI on 3000).
    BACKEND_CORS_ORIGINS: Annotated[list[AnyUrl] | str, BeforeValidator(_parse_cors)] = [
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
    ]

    # --- KG backend -----------------------------------------------------
    # Single in-process NetworkX backend. The legacy Neo4j path was removed
    # during cleanup (the deployed KG fits in memory at 673 nodes / ~1k
    # edges, so a graph DB is overkill for what we ship today).
    KG_BACKEND: Literal["networkx"] = "networkx"

    # --- Data paths (string inputs; computed fields resolve to Path) ----
    DATA_DIR: str = "data"
    SEED_KG_PATH: str = "data/seed/kg.json"
    ARTIFACTS_DIR: str = "data/artifacts"
    RAW_DIR: str = "data/raw"

    # --- Disease scope --------------------------------------------------
    DISEASE_SCOPE: Literal["lsd", "lsd_extended", "all"] = "lsd"

    # --- Server ---------------------------------------------------------
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    RELOAD: bool = True

    # -------------------- Computed / derived ---------------------------

    @computed_field  # type: ignore[prop-decorator]
    @property
    def data_dir(self) -> Path:
        return resolve_project_path(self.DATA_DIR, _DATA_DIR_DEFAULT)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def seed_kg_path(self) -> Path:
        return resolve_project_path(self.SEED_KG_PATH, _SEED_KG_DEFAULT)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def artifacts_dir(self) -> Path:
        return resolve_project_path(self.ARTIFACTS_DIR, _ARTIFACTS_DIR_DEFAULT)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def raw_dir(self) -> Path:
        return resolve_project_path(self.RAW_DIR, _RAW_DIR_DEFAULT)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_cors_origins(self) -> list[str]:
        """CORS origins as plain strings (FastAPI's middleware expects str,
        not AnyUrl). Trailing-slash-normalized so a browser with the
        origin `http://localhost:8000` matches a config value of
        `http://localhost:8000/`."""
        if isinstance(self.BACKEND_CORS_ORIGINS, str):
            return [self.BACKEND_CORS_ORIGINS.rstrip("/")]
        return [str(o).rstrip("/") for o in self.BACKEND_CORS_ORIGINS]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def openapi_url(self) -> str | None:
        """Hide OpenAPI JSON (and therefore /docs + /redoc) in non-local
        environments. Matches full-stack-fastapi-template's default.
        Return None to disable, a URL to enable.
        """
        if self.ENVIRONMENT == "local":
            return f"{self.API_V1_STR}/openapi.json"
        return None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def docs_enabled(self) -> bool:
        return self.ENVIRONMENT == "local"


# Module-level accessor. Tests override by constructing a fresh Settings
# and plumbing it through `create_app(settings=...)`.
_settings: Settings | None = None


def get_settings() -> Settings:
    """Lazy-construct and memoize. Pass-through for the hot path;
    `create_app(settings=...)` can bypass it for tests."""
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings


def reset_settings_cache() -> None:
    """Test hook. After `monkeypatch.setenv(...)`, tests call this so
    the next `get_settings()` re-reads the environment."""
    global _settings
    _settings = None
