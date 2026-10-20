# Tests

| Suite | Location | Run |
|---|---|---|
| Backend unit (pure domain logic: rubric, adaptive policy, skills, readiness, lifecycle, eligibility, chunking, keys, recommendations, graph routing) | `backend/tests/unit` | `cd backend && pytest tests/unit` |
| Backend API / integration (auth, lifecycle, end-to-end interview loop, RAG ingestion/versioning/re-index, files) | `backend/tests/integration` | `cd backend && pytest tests/integration` |
| Security (tenant isolation, cross-student access, JWT, WebSocket auth, presigned URLs, frontend secrets) | `backend/tests/security` | `cd backend && pytest tests/security` |
| Frontend unit (Vitest + Testing Library) | `frontend/tests/unit` | `cd frontend && npm test` |
| UI end-to-end (Playwright, needs running stack + `scripts/seed.py`) | `frontend/tests/e2e` | `cd frontend && E2E_PASSWORD=... npx playwright test` |
| API collection (Postman) | `tests/postman/interview-agent.postman_collection.json` | Import into Postman, set `baseUrl` |

Backend integration tests use SQLite plus in-memory implementations of MinIO, ChromaDB, Gemini, STT and TTS that share the
production interfaces, with Celery in eager mode — so the full API → LangGraph → agents → persistence path runs without
external services. Run the same flows against the real stack with Postman/Playwright after `docker compose up`.
