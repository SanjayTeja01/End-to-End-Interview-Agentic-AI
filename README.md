# End-to-End Interview Agent

An institution-controlled, multi-tenant, agentic-AI platform that **autonomously conducts adaptive video interviews**.

Institutions create interview campaigns for roles (AI/ML Engineer, Software Engineer, DevOps…), supply or approve the
required skills, and activate them. Eligible students join a video interview in which an AI interviewer speaks each
question (TTS), listens to the spoken answer (STT), evaluates it against a rubric, and adapts the next question's topic
and difficulty. Each interview ends with performance analysis, a readiness assessment, focused improvement
recommendations and a stored report. Results feed into the candidate's history and shape future interviews.
No human interviewer is needed. Institutions *can* watch live, but the interview doesn't depend on it.

---

## Architecture

```
 Next.js (student + institution UIs)
   │  REST via same-origin /api proxy      WebSocket (state/events/WebRTC signalling)     WebRTC (camera → monitors)
   ▼
 FastAPI ── JWT auth · RBAC · tenant scoping · validation · presigned URLs
   │
   ├── PostgreSQL  structured source of truth (SQLAlchemy + Alembic)
   ├── MinIO       private blobs: resumes, KB docs, answer audio/video, TTS audio, report PDFs
   ├── ChromaDB    derived, disposable vector index (rebuildable from Postgres + MinIO)
   └── Redis       Celery broker · pub/sub fan-out · rate limiting (never a database)
          │
          ▼
   Celery workers ── resume parsing · RAG ingestion/re-index · STT → evaluation → next question → TTS · report PDF
          │
          ▼
   LangGraph supervisor ── 10 specialised agents ── Grok (xAI LLM) / embeddings provider
```

Full design notes: [`docs/architecture.md`](docs/architecture.md).

### Agents (LangGraph) vs. infrastructure

| Agents (`backend/app/agents`) | Responsibility |
|---|---|
| Supervisor / Orchestrator (`app/graph/workflow.py`) | Routes `initialize` / `process_answer` / `finalize`, checks stopping conditions, recovers (fallback questions, provisional evaluations) |
| Resume Analyzer | Structured extraction; drops claims not grounded in the resume text |
| Role & Skill | Proposes skills, levels (0–5), importance, topics from role + JD + tenant RAG; institution approves |
| Interview Planning | Deterministic coverage plan from requirements, skill gaps, resume projects, historical weak/strong topics |
| RAG Knowledge | Decides when retrieval helps; tenant-filtered retrieval with sources |
| Adaptive Interview | Words one question within the topic/difficulty chosen by the **deterministic policy** (`app/domain/adaptive.py`) |
| Answer Evaluation | Rubric scoring grounded in the transcript; final score computed deterministically |
| Performance | Aggregates evaluations (topic, skill, criterion, difficulty progression, trends) |
| Readiness | Evidence-weighted readiness (never a hiring guarantee) |
| Report | Structured report + short LLM narrative (template fallback) |

STT (faster-whisper), TTS (Piper), WebRTC, WebSockets, PostgreSQL, MinIO, ChromaDB, Redis, Celery and Grok are
**infrastructure**, behind provider interfaces in `app/services` and `rag/`.

### The autonomous loop

```
question generated → TTS (Piper → MinIO) → candidate hears it → speaks → MediaRecorder upload (idempotent)
 → Celery: STT → Answer Evaluation → shared state update → Supervisor: stop? → policy picks topic/difficulty
 → RAG if useful → Adaptive Interview Agent → next question → TTS → … → Performance → Readiness
 → Recommendations → Report → history (used by the next interview)
```

Adaptive policy: strong answer → harder follow-up (reasoning/trade-offs); average → same difficulty, probe gaps; weak →
easier foundational question; two weak answers in a row → topic marked weak and never revisited (recorded for
recommendations and future interviews); two strong in a row → topic marked strong, move on. The question count,
duration (enforced by both the server timer and per-turn checks), candidate "end", and institution "terminate" all stop
the interview.

---

## Technology stack

Next.js 14 · React 18 · TypeScript · Tailwind CSS · Recharts · lucide-react — FastAPI · SQLAlchemy 2 · Alembic · Pydantic 2 —
LangGraph · Grok (xAI REST API) — ChromaDB — PostgreSQL 16 — MinIO — Redis 7 + Celery 5 — PyMuPDF · python-docx —
faster-whisper · Piper — WebRTC · WebSockets — Pytest · Vitest · Playwright · Postman — Docker Compose.

## Directory structure

```
backend/
  app/
    agents/        10 agents + Pydantic output contracts
    api/           deps (auth/RBAC) + routes
    core/          config, database, security, logging, errors
    domain/        pure, deterministic logic (rubric, adaptive policy, skills, readiness, lifecycle, eligibility, …)
    graph/         LangGraph state, workflow (supervisor), context loader, persistence
    models/        SQLAlchemy models
    schemas/       API schemas
    services/      interviews, runtime, resumes, knowledge, files, LLM, speech, realtime, analytics, reports, jobs
    websocket/     authenticated interview socket (+ WebRTC signalling relay)
    workers/       Celery app + resume / rag / media / report / interview tasks
  db/alembic/      migrations (0001_initial_schema.py)
  rag/             extraction, cleaning, chunking, embeddings, retrieval, metadata, ingestion, reindexing
  storage/minio/   client, bucket management, key conventions, presigned URLs
  tests/           unit · integration · security
frontend/src/      app router pages, components, lib (api client, auth, websocket, WebRTC, recorder)
scripts/           reindex_chroma.py · seed.py · download_speech_models.sh
config/.env.example
docs/              architecture.md
tests/postman/     API collection
docker-compose.yml
```

---

## Quick start (Docker)

```bash
cp config/.env.example .env
# Required: set JWT_SECRET (python -c "import secrets;print(secrets.token_urlsafe(64))"),
#           XAI_API_KEY, POSTGRES_PASSWORD (and the same password inside DATABASE_URL), MINIO_SECRET_KEY.
docker compose build
docker compose run --rm backend sh /app/scripts/download_speech_models.sh   # Piper voice (one-off)
docker compose up -d
docker compose exec backend python /app/scripts/seed.py                     # optional synthetic demo data
```

* App: http://localhost:3000 · API docs: http://localhost:8000/docs · MinIO console: http://localhost:9001
* Migrations run automatically when the backend starts (`alembic upgrade head`).
* All persistent data lives in named Docker volumes (`pg_data`, `minio_data`, `chroma_data`, `speech_models`), never in the repo.

### Running services individually (development)

```bash
docker compose up -d postgres redis minio chroma
cd backend && python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-speech.txt
export $(grep -v '^#' ../.env | xargs)   # with hosts changed to localhost (DATABASE_URL, MINIO_ENDPOINT, REDIS_URL, CHROMA_HOST/PORT=8001)
alembic upgrade head
uvicorn app.main:app --reload --port 8000
celery -A app.workers.celery_app worker -Q default,media,rag,reports --loglevel=INFO   # second terminal
cd ../frontend && npm install && npm run dev                                           # third terminal
```

---

## Configuration

All configuration comes from environment variables (`config/.env.example` lists every one). Highlights:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL DSN (`postgresql+psycopg://…`) |
| `JWT_SECRET` | ≥32 random chars; startup fails if weak or missing |
| `LLM_PROVIDER`, `XAI_API_KEY`, `XAI_MODEL`, `XAI_REASONING_EFFORT` | Grok (xAI) credentials, model id and reasoning effort (`low` = fastest) |
| `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES` | Per-call timeout and extra attempts (kept small so interviews never stall) |
| `LLM_RATE_LIMIT_PER_MINUTE` | Redis-enforced cross-worker rate limit (Gemini path only) |
| `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_VERSION`, `EMBEDDING_DIMENSIONS` | Embedding abstraction; stored with every vector |
| `MINIO_ENDPOINT`, `MINIO_PUBLIC_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET` | Private object storage; presigned URLs are signed for the public endpoint |
| `REDIS_URL` | Celery broker / pub-sub / rate limits |
| `CHROMA_HOST`, `CHROMA_PORT`, `CHROMA_COLLECTION` | Vector index |
| `STT_PROVIDER`, `STT_MODEL` | `faster_whisper` (local, no API key) |
| `TTS_PROVIDER`, `PIPER_VOICE_PATH` | `piper` (local) or `none` (browser speech fallback) |
| `WEBRTC_ICE_SERVERS` | STUN/TURN list for peer connections (add a TURN server for restrictive networks) |
| `NEXT_PUBLIC_API_BASE`, `NEXT_PUBLIC_WS_BASE` | The only values exposed to the browser |

**Grok (xAI).** Set `XAI_API_KEY` (from console.x.ai). The default model is `grok-4.7` with `XAI_REASONING_EFFORT=low`.
Every call goes through `app/services/llm.py`: a Pydantic response schema sent as xAI structured output, validation of
the reply and one short retry. Bad keys/models fail immediately instead of retrying. Check the setup with
`docker compose exec worker python /app/scripts/check_grok.py`. Gemini is still available as an optional provider
(`LLM_PROVIDER=gemini`, plus `pip install -r requirements-gemini.txt`).
**Groq.** For a key that starts with `gsk_` (groq.com), set `LLM_PROVIDER=groq` and `GROQ_API_KEY`. The default model is
`openai/gpt-oss-120b`; the same check script works.

**Embeddings.** The default is `local`: all-MiniLM-L6-v2 (384 dimensions) running inside the container, baked into
the image at build time, no API key. xAI has no embeddings API; `EMBEDDING_PROVIDER=gemini` is still supported. Every chunk records `embedding_model` and
`embedding_version`. After changing either, run `python /app/scripts/reindex_chroma.py --only-stale` (or `--reset`).

**Speech.** faster-whisper downloads its model on first use into the `speech_models` volume (`HF_HOME=/models/hf`). Piper
needs a voice `.onnx`, which `scripts/download_speech_models.sh` fetches. If TTS isn't available, the browser's speech
synthesis reads the question instead. If the microphone fails, the room offers a typed-answer fallback.

---

## RAG

* **Ingest:** upload in Knowledge Base → MinIO (`knowledge/{institute}/{doc}/version-{n}.ext`) → Postgres metadata and a
  version row → Celery: PyMuPDF/python-docx extraction → cleaning → paragraph-aware chunking → embeddings → ChromaDB.
  Each chunk carries `doc_id, institute_id, source_key, version, chunk_id, embedding_model, embedding_version,
  source_title, topic, skill, role, difficulty, content_type`.
* **Versioning:** a new version replaces that document's vectors, and older versions are marked `superseded`. Deactivating
  or deleting a document removes its vectors.
* **Retrieval:** `institute_id` is mandatory. The vector store raises if it's missing, and results are re-checked
  afterwards. Filters narrow by role, then skill, then document type, and never widen past the tenant.
* **Rebuild:** ChromaDB is disposable. `python /app/scripts/reindex_chroma.py --reset` rebuilds everything from
  Postgres + MinIO. `--institute <uuid>` rebuilds one tenant. The UI has a "Re-index all" button per institution.

## Security model

* Argon2id password hashing. Short-lived access JWTs are held in memory, and refresh tokens are httpOnly SameSite=Strict
  cookies on the same origin. Role and tenant are re-read from the database on every request, so tampered claims are rejected.
* Every query on tenant-owned rows is scoped to the authenticated `institute_id` (`services/tenancy.py`). Cross-tenant
  ids return 404, which avoids leaking whether a record exists. Students can only reach their own resume, sessions,
  reports and files.
* Eligibility is enforced by the backend at join time: tenant, account state, interview status, schedule, assignment or
  revocation, and role match. Semantic similarity can add a match but can never grant access on its own.
  Frontend filtering is only for display.
* MinIO buckets are private. Files are served only through short-lived presigned URLs, issued after authorisation, and
  the object key's tenant prefix is checked again. Uploads are validated by content sniffing, size and allowed type.
* WebSockets authenticate in the first message (no token in the URL), check the Origin, verify session ownership or
  institution membership, and relay only whitelisted message types.
* No secret is hard-coded, and the frontend never receives one (enforced by `tests/security/test_frontend_secrets.py`).
  Logs are structured JSON with correlation ids, and secrets are redacted.
* Video is used only for the live interview and monitoring. There is **no** facial, emotion, gaze, personality or
  biometric analysis. Evaluation uses answer content only.

## Testing

```bash
cd backend && pytest                 # unit + integration + security (SQLite + in-memory doubles, Celery eager)
cd frontend && npm test              # Vitest unit tests
cd frontend && npx playwright test   # UI e2e against a running, seeded stack (set E2E_PASSWORD)
```

The Postman collection is in `tests/postman/`. See `tests/README.md` for what each suite covers.

## Deployment notes

* Put a TLS-terminating reverse proxy in front of the stack. Then set `COOKIE_SECURE=true`, set `CORS_ORIGINS` and
  `FRONTEND_URL` to the public origin, and use `wss://` for `NEXT_PUBLIC_WS_BASE`.
* Set `MINIO_PUBLIC_ENDPOINT` to the hostname browsers use to fetch presigned URLs.
* Scale `worker` replicas horizontally; the `media` queue carries interview turns. `backend` is stateless.
* Health checks: `GET /health` (liveness) and `GET /health/ready` (Postgres, Redis, MinIO and Chroma).
* Migrations: `alembic upgrade head` (runs automatically on backend start). New schema changes need
  `alembic revision --autogenerate -m "…"`, followed by a review of the generated file.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Backend exits with `JWT_SECRET must be set…` | Set a random secret of at least 32 characters in `.env` |
| Questions are read by the browser voice | The Piper voice is missing; run `download_speech_models.sh` |
| Answers stay "Evaluating…" | Check that the `worker` container is running and that `XAI_API_KEY` is valid (`docker compose exec worker python /app/scripts/check_grok.py`) |
| Live video never appears for monitors | The network blocks peer-to-peer; add a TURN server to `WEBRTC_ICE_SERVERS` |
| Presigned links fail in the browser | Set `MINIO_PUBLIC_ENDPOINT` to a host the browser can reach (e.g. `localhost:9000`) |
| RAG returns nothing after a Chroma wipe | Run `scripts/reindex_chroma.py --reset` |

## Extension points

These are designed for, not built: human review/override of evaluations (provisional evaluations are already flagged
`needs_review`), coding-interview environment, multilingual STT/TTS (provider settings), cohort benchmarking, PostgreSQL
row-level security as defence in depth, and fine-grained audit logs.
