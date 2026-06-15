from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import PROJECT_ROOT, Settings
from app.security import ALLOWED_EXACT_PATHS, ALLOWED_PREFIXES


def test_frontend_does_not_contain_hardcoded_login_credentials():
    app_js = (PROJECT_ROOT / "src/app/frontend/app.js").read_text(encoding="utf-8")

    assert '"username": "admin"' not in app_js
    assert '"password": "admin"' not in app_js


def test_public_auth_route_does_not_allow_similar_prefixes():
    assert "/auth/login" in ALLOWED_EXACT_PATHS
    assert "/auth" not in ALLOWED_PREFIXES


def test_production_rejects_unsafe_credentials():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            ENV="production",
            AUTH_SECRET="change-me",
            DEFAULT_USERNAME="admin",
            DEFAULT_PASSWORD="admin",
            INGEST_API_KEY="change-me-in-production",
        )


def test_project_root_is_independent_from_current_working_directory():
    assert (PROJECT_ROOT / "pyproject.toml").is_file()
