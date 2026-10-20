"""The frontend bundle must never reference backend secrets."""
import pathlib
import re

FRONTEND = pathlib.Path(__file__).resolve().parents[3] / "frontend"
SECRETS = re.compile(r"GEMINI_API_KEY|XAI_API_KEY|JWT_SECRET|MINIO_SECRET_KEY|MINIO_ACCESS_KEY|DATABASE_URL|POSTGRES_PASSWORD")


def test_frontend_source_has_no_backend_secrets():
    files = [p for p in FRONTEND.rglob("*") if p.suffix in {".ts", ".tsx", ".js", ".mjs", ".json"}
             and "node_modules" not in p.parts and ".next" not in p.parts]
    assert files, "frontend sources not found"
    offenders = [str(p) for p in files if SECRETS.search(p.read_text(errors="ignore"))]
    assert offenders == []


def test_only_public_env_vars_exposed():
    # Browser-delivered code lives in src/; test/e2e tooling may read local env vars.
    for p in (FRONTEND / "src").rglob("*.ts*"):
        for m in re.finditer(r"process\.env\.([A-Z0-9_]+)", p.read_text(errors="ignore")):
            assert m.group(1).startswith("NEXT_PUBLIC_"), (p, m.group(1))
