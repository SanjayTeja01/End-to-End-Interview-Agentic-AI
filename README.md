# End-to-End Interview Agent

An agentic AI platform that conducts **adaptive technical interviews by voice, without a human interviewer**. Institutions
can use it to give every student a realistic, consistent practice or screening interview, and get an evidence-based
report afterwards.

An institution defines an interview for a role and the skills it needs. A student joins from the browser. The AI
interviewer speaks each question and listens to the answer. It scores the answer against a rubric and picks the next
question from what that answer showed:

- a strong answer leads to a harder follow-up;
- a partial answer leads to a question about the missing concept;
- a vague answer leads to a request for a concrete example;
- a wrong answer leads to a simpler diagnostic question.

At the end, the platform produces a performance report, a readiness assessment and focused recommendations. All of
these feed into the student's next interview.

---

## Contents

- [Key features](#key-features)
- [How an interview works](#how-an-interview-works)
- [Architecture](#architecture)
- [Technology stack](#technology-stack)
- [Getting started](#getting-started)
- [Using the platform](#using-the-platform)
- [Configuration](#configuration)
- [Data storage and privacy](#data-storage-and-privacy)
- [Security](#security)
- [Testing](#testing)
- [Project structure](#project-structure)
- [Deployment notes](#deployment-notes)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [Roadmap](#roadmap)
- [Author](#author)

---

## Key features

**For institutions**
- Create interview campaigns per role (e.g. Backend Developer, AI/ML Engineer) with required skills, levels, topics,
  question count, duration and starting difficulty. The AI can also propose the skill list from a job description.
- Control access with a join code, schedules and per-interview eligibility rules.
- Upload a private knowledge base (PDF/DOCX) that grounds questions in the institution's own material (RAG).
- Watch interviews live (WebRTC) and terminate one if needed.
- Review each student's profile, resume analysis, skill gaps, interview history, scores and readiness.
- Remove a student and all of their data permanently (institution admin only).

**For students**
- Upload a resume. Skills and projects are extracted, and claims not supported by the resume text are discarded.
- Take voice interviews in the browser: questions are spoken aloud, answers are transcribed. A typed-answer fallback is
  available.
- See live progress for every answer ("Transcribing", "Evaluating", "Choosing your next question").
- Get a report per interview, with per-question scores, strengths, gaps and next steps, and track progress over time.

**Interview engine**
- A true turn-by-turn adaptive loop: the next question is chosen only after the previous answer has been evaluated and
  the candidate profile updated.
- Evidence-based adaptation using correctness, completeness, depth, evaluator confidence and missing concepts. Every
  threshold is configurable.
- Reliable under failure: bounded retries with timeouts, idempotent answer submission, a "Retry evaluation" action, and
  no fabricated scores when the AI service is unavailable.
- The final score is the exact aggregate of the stored per-question evaluations.

---

## How an interview works

```
Question generated ─► spoken to the candidate (Piper TTS)
        │
Candidate answers by voice ─► answer finalised (idempotent upload)
        │
Speech-to-text (faster-whisper, or the browser transcript)
        │
Answer Evaluation agent ─► rubric scores + missing concepts + confidence      [committed]
        │
Candidate profile updated (per-topic and per-skill performance)              [committed]
        │
Adaptive policy reads the evidence ─► next topic, difficulty and question type
        │
Adaptive Interview agent writes the next question (optionally grounded by RAG) ─► presented
        │
   … repeats until the question count, time limit, candidate "End" or institution "Terminate" …
        │
Performance ─► Readiness ─► Recommendations ─► Report (stored, PDF export) ─► candidate history
```

Each step is time-stamped on the answer record (`answer_finalized`, `evaluation_started`, `evaluation_completed`,
`profile_updated`, `next_question_decided`, `next_question_presented`). This makes the order of every turn auditable.

### Adaptive policy

The policy (`backend/app/domain/adaptive.py`) is deterministic and explains every decision in plain words. Each
explanation is stored with the question it produced.

| Evidence from the last answer | Next question |
|---|---|
| Strong answer | Harder follow-up on reasoning, application and trade-offs |
| Correct and complete but brief | Harder follow-up (brevity is not penalised) |
| Core idea correct, specific concepts missing | Same difficulty, targets the missing concept |
| Evaluator not confident (vague or ambiguous) | Asks the candidate to clarify with a concrete example |
| Partially complete | Same difficulty, probes the gaps |
| Incorrect / misconception | Easier, foundational diagnostic question |
| Two weak answers on a topic | Topic recorded as weak and the interview moves on |
| Two strong answers on a topic | Topic recorded as strong and the interview moves on |

The thresholds are environment variables: `ADAPTIVE_CLARIFY_CONFIDENCE`, `ADAPTIVE_GAP_MIN_CORRECTNESS`,
`ADAPTIVE_CONCISE_CORRECT_MIN` and `ADAPTIVE_CONCISE_COMPLETE_MIN`.

---

## Architecture

```
 Next.js 14 (student + institution apps)
   │  REST via same-origin /api proxy · WebSocket (live turn status, events, WebRTC signalling)
   ▼
 FastAPI ── JWT auth · role-based access · tenant scoping · validation · presigned URLs
   │
   ├── PostgreSQL   source of truth (SQLAlchemy 2 + Alembic)
   ├── MinIO        private files: resumes, knowledge base, answer audio, question audio, report PDFs
   ├── ChromaDB     vector index for RAG (derived data, rebuildable from Postgres + MinIO)
   └── Redis        Celery broker · pub/sub for live events · rate limiting
          │
          ▼
   Celery workers ── resume parsing · RAG ingestion · interview turns (STT → evaluation → next question → TTS) · reports
          │
          ▼
   LangGraph supervisor ── specialised agents ── LLM provider (Groq / xAI Grok / Gemini)
```

### Agents

| Agent | Responsibility |
|---|---|
| Supervisor (`app/graph/workflow.py`) | Routes `initialize` / `process_answer` / `next_question` / `finalize`, checks stop conditions, falls back to safe questions |
| Resume Analyzer | Structured extraction from the resume; ungrounded claims are dropped |
| Role & Skill | Proposes skills, levels (0–5), weights and topics from the role, job description and knowledge base |
| Interview Planning | Coverage plan from requirements, skill gaps, resume projects and past performance |
| RAG Knowledge | Decides when retrieval helps; tenant-filtered retrieval with sources |
| Adaptive Interview | Writes one question for the topic, difficulty and type chosen by the policy, and never repeats a question |
| Answer Evaluation | Rubric scoring grounded in the transcript |
| Performance | Aggregates evaluations by topic, skill, criterion and difficulty |
| Readiness | Evidence-weighted readiness level (an indicator, never a hiring decision) |
| Report | Structured report with a short narrative |

Speech, storage, the vector store and the LLM are infrastructure behind provider interfaces (`app/services`, `rag/`,
`storage/`), so each can be swapped without touching the agents. Design notes are in
[`docs/architecture.md`](docs/architecture.md). The adaptive-loop redesign is described in
[`docs/ADAPTIVE-INTERVIEW-FIX.md`](docs/ADAPTIVE-INTERVIEW-FIX.md).

---

## Technology stack

| Layer | Technologies |
|---|---|
| Frontend | Next.js 14, React 18, TypeScript, Tailwind CSS, Recharts |
| Backend API | FastAPI, Pydantic 2, SQLAlchemy 2, Alembic |
| Agents | LangGraph, OpenAI-compatible LLM APIs (Groq, xAI Grok), Google Gemini (optional) |
| Async processing | Celery 5, Redis 7 |
| Data | PostgreSQL 16, MinIO (S3-compatible), ChromaDB |
| Speech | faster-whisper (STT), Piper (TTS), browser Web Speech API as fallback |
| Real time | WebSockets, WebRTC |
| Documents | PyMuPDF, python-docx |
| Testing | Pytest, Vitest, Testing Library, Playwright, Postman |
| Packaging | Docker, Docker Compose |

---

## Getting started

### Prerequisites

- Docker Desktop (or Docker Engine with the Compose plugin), with at least 8 GB of RAM available to Docker
- An LLM API key: a [Groq](https://console.groq.com) key (`gsk_…`, free tier available) or an
  [xAI](https://console.x.ai) key (`xai-…`)
- Git, and a modern Chromium-based browser or Firefox with microphone access

### 1. Clone and configure

```bash
git clone https://github.com/SanjayTeja01/End-to-End-Interview-Agentic-AI.git
cd End-to-End-Interview-Agentic-AI
cp config/.env.example .env
```

Edit `.env` and set at least these values:

| Variable | Value |
|---|---|
| `JWT_SECRET` | A random string of 32+ characters: `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `POSTGRES_PASSWORD` | A strong password (use the same value inside `DATABASE_URL`) |
| `MINIO_SECRET_KEY` | A strong password for object storage |
| `LLM_PROVIDER` + key | `groq` with `GROQ_API_KEY`, or `grok` with `XAI_API_KEY` |

`.env` is git-ignored. Never commit it.

### 2. Build and start

```bash
docker compose build
docker compose run --rm backend sh /app/scripts/download_speech_models.sh   # one-off: Piper voice
docker compose up -d
docker compose exec worker python /app/scripts/check_grok.py               # verifies the LLM key and model
```

Database migrations run automatically when the backend starts.

| Service | URL |
|---|---|
| Web application | http://localhost:3000 |
| API documentation (Swagger) | http://localhost:8000/docs |
| MinIO console (stored files) | http://localhost:9001 |

Optional synthetic demo data: `docker compose exec backend python /app/scripts/seed.py`.

### Everyday commands

```bash
docker compose up -d                                     # start
docker compose ps                                        # status
docker compose logs -f backend worker                    # follow logs
docker compose up -d --build backend worker frontend     # apply code changes
docker compose down                                      # stop (data is kept)
```

### Running without Docker (development)

```bash
docker compose up -d postgres redis minio chroma
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-speech.txt
# export the variables from ../.env with hosts changed to localhost
alembic upgrade head
uvicorn app.main:app --reload --port 8000
celery -A app.workers.celery_app worker -Q default,media,rag,reports --loglevel=INFO   # second terminal
cd ../frontend && npm install && npm run dev                                           # third terminal
```

---

## Using the platform

1. **Register an institution** at http://localhost:3000/register. The account you create is the institution
   administrator. The dashboard shows the institution's **join code**.
2. **Create an interview**: set the role, job description, required skills and topics, number of questions, duration and
   starting difficulty, then **activate** it.
3. *(Optional)* **Upload knowledge-base documents** so questions draw on your own material.
4. **Students register** with the join code, set target roles and upload a resume.
5. Students **start an eligible interview**, allow the microphone, and answer each question aloud. Each answer shows its
   progress until the next question appears.
6. **Review results**: students see their reports and history. Institutions see every student's performance,
   readiness and skill gaps, and can monitor or terminate live interviews.

To verify the adaptive loop against the real LLM, run the end-to-end check. It plays six contrasting answers and prints
the timeline of every turn:

```bash
docker compose exec backend python /app/scripts/adaptive_e2e.py
```

---

## Configuration

All configuration is read from environment variables (see `backend/app/core/config.py` for defaults). `config/.env.example` is the template for `.env`. The main groups:

| Area | Variables |
|---|---|
| Core | `APP_ENV`, `JWT_SECRET`, `ACCESS_TOKEN_MINUTES`, `REFRESH_TOKEN_DAYS`, `CORS_ORIGINS`, `FRONTEND_URL`, `COOKIE_SECURE` |
| Database / cache | `DATABASE_URL`, `POSTGRES_*`, `REDIS_URL` |
| LLM | `LLM_PROVIDER` (`groq`, `grok`, `gemini`), `GROQ_API_KEY`, `GROQ_MODEL`, `XAI_API_KEY`, `XAI_MODEL`, `XAI_REASONING_EFFORT`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES`, `LLM_RATE_LIMIT_MAX_WAIT_SECONDS` |
| Embeddings / RAG | `EMBEDDING_PROVIDER` (`local` by default, no key needed), `EMBEDDING_MODEL`, `EMBEDDING_VERSION`, `CHROMA_HOST`, `CHROMA_PORT`, `CHROMA_COLLECTION` |
| Storage | `MINIO_ENDPOINT`, `MINIO_PUBLIC_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET` |
| Speech | `STT_PROVIDER`, `STT_MODEL`, `STT_TIMEOUT_SECONDS`, `TTS_PROVIDER`, `PIPER_VOICE_PATH`, `TTS_TIMEOUT_SECONDS` |
| Interview turns | `TURN_EVAL_ATTEMPTS`, `TURN_STUCK_SECONDS` |
| Adaptive policy | `ADAPTIVE_CLARIFY_CONFIDENCE`, `ADAPTIVE_GAP_MIN_CORRECTNESS`, `ADAPTIVE_CONCISE_CORRECT_MIN`, `ADAPTIVE_CONCISE_COMPLETE_MIN` |
| Live video | `WEBRTC_ICE_SERVERS` (add a TURN server for restrictive networks) |
| Browser (public) | `NEXT_PUBLIC_API_BASE`, `NEXT_PUBLIC_WS_BASE`, the only values exposed to the browser |

**LLM providers.** Every LLM call goes through `app/services/llm.py`. Replies use a Pydantic response schema (structured
output), are validated, and are retried a bounded number of times. Rate-limit responses (HTTP 429) honour `Retry-After`.
Invalid keys or models fail immediately instead of retrying.

**Embeddings.** The default `local` provider (all-MiniLM-L6-v2, 384 dimensions) runs inside the container and is baked
into the image. Every chunk records its embedding model and version. After changing either, run
`python /app/scripts/reindex_chroma.py --only-stale` (or `--reset`).

**Speech.** faster-whisper downloads its model on first use into the `speech_models` volume. Piper needs a voice file,
which `scripts/download_speech_models.sh` fetches. If server TTS is unavailable, the browser reads the question aloud.

---

## Data storage and privacy

All data stays on the machine running the stack, in Docker named volumes. Nothing is stored inside the repository.

| Volume | Contents | How to inspect |
|---|---|---|
| `pg_data` | Accounts, profiles, interviews, questions, answers (transcripts), evaluations, reports | `docker compose exec postgres psql -U <POSTGRES_USER> -d <POSTGRES_DB>`, or a client such as DBeaver on `localhost:5432` |
| `minio_data` | Resumes, knowledge-base files, answer audio, question audio, report PDFs | MinIO console at http://localhost:9001 |
| `chroma_data` | Vector embeddings of knowledge-base chunks (derived, rebuildable) | `scripts/reindex_chroma.py` |
| `speech_models` | Downloaded STT/TTS models | — |

The files inside these volumes are in each engine's internal format and are not meant to be opened directly. Use the
tools above. Passwords are stored only as Argon2id hashes. Other data is stored unencrypted at the application level,
so protect the host and its disks accordingly.

- **Remove one student:** Institution → Students → *student* → **Remove student**. This deletes the account, resume,
  sessions, answers, evaluations, reports and stored files.
- **Reset everything:** `docker compose down`, then `docker volume rm <project>_pg_data <project>_minio_data <project>_chroma_data`
  (check the names with `docker volume ls`). This cannot be undone.

Video is used only for the live interview and monitoring. There is **no** facial, emotion, gaze, personality or
biometric analysis, and evaluation uses answer content only.

---

## Security

- **Authentication.** Argon2id password hashing. Short-lived access tokens are kept in memory. Refresh tokens are
  httpOnly, SameSite=Strict cookies. Role and tenant are re-read from the database on every request, so a tampered
  token claim is rejected.
- **Tenant isolation.** Every query on tenant-owned data is scoped to the caller's institution. A cross-tenant id returns
  404, so the response does not reveal that the record exists. Students can reach only their own resume, sessions,
  reports and files.
- **Eligibility.** Enforced on the server when an interview starts: tenant, account state, interview status, schedule,
  assignment and role match.
- **Files.** Buckets are private. Files are served only through short-lived presigned URLs after authorisation.
  Uploads are validated by content sniffing, type and size.
- **WebSockets.** The client authenticates in the first message (no token in the URL). The server checks the origin,
  verifies the client may access the session, and relays only whitelisted message types.
- **Secrets.** No secret is hard-coded, and the frontend never receives one
  (`backend/tests/security/test_frontend_secrets.py` enforces this). Logs are structured JSON with correlation ids and
  redacted secrets.
- **Repository hygiene.** `.gitignore` excludes `.env`, keys, backups, archives, logs and runtime data. A pre-commit hook
  blocks commits that contain API keys or private keys. Enable it once per clone:

  ```bash
  git config core.hooksPath .githooks
  ```

If you discover a security issue, please report it privately to the author rather than opening a public issue.

---

## Testing

```bash
cd backend && pytest                 # unit, integration and security suites
cd frontend && npm test              # Vitest unit tests
cd frontend && npx playwright test   # UI end-to-end against a running, seeded stack (set E2E_PASSWORD)
docker compose exec backend python /app/scripts/adaptive_e2e.py   # live adaptive-loop check with the real LLM
```

The backend suites run without external services. They use SQLite (with foreign keys enforced), in-memory
implementations of MinIO, ChromaDB, the LLM, STT and TTS that share the production interfaces, and Celery in eager mode.
This covers authentication, tenant isolation, the full interview loop, adaptive decisions, failure and retry handling,
RAG ingestion and versioning, reports and student removal. A Postman collection is in `tests/postman/`, and
`tests/README.md` describes each suite.

---

## Project structure

```
backend/
  app/
    agents/       LangGraph agents and their output contracts
    api/          auth/RBAC dependencies and REST routes
    core/         configuration, database, security, logging, errors
    domain/       deterministic logic: rubric, adaptive policy, skills, readiness, lifecycle, eligibility
    graph/        LangGraph state, supervisor workflow, context loading, persistence
    models/       SQLAlchemy models
    schemas/      API request/response schemas
    services/     interviews, runtime (turn loop), resumes, knowledge, files, LLM, speech, analytics, reports
    websocket/    authenticated interview socket and WebRTC signalling relay
    workers/      Celery app and tasks (resume, RAG, media/turns, reports, interviews)
  db/alembic/     database migrations
  rag/            extraction, cleaning, chunking, embeddings, retrieval, ingestion, re-indexing
  storage/minio/  object storage client and key conventions
  tests/          unit, integration and security tests
frontend/
  src/app/        Next.js routes: login/register, institution app, student app, interview room
  src/components/ shared UI, charts, 3D scene, report view
  src/lib/        API client, auth, WebSocket, WebRTC, recorder, speech
  tests/          Vitest unit tests and Playwright end-to-end tests
scripts/          seed data, LLM checks, adaptive e2e check, Chroma re-index, speech model download
config/           .env.example (template for .env)
docs/             architecture and design notes
tests/postman/    API collection
docker-compose.yml
```

---

## Deployment notes

- Put a TLS-terminating reverse proxy in front of the stack. Then set `COOKIE_SECURE=true`, set `CORS_ORIGINS` and
  `FRONTEND_URL` to the public origin, and use `wss://` for `NEXT_PUBLIC_WS_BASE`.
- Set `MINIO_PUBLIC_ENDPOINT` to the hostname browsers use for presigned URLs.
- `backend` is stateless. Scale `worker` replicas horizontally; interview turns run on the `media` queue.
- Health checks: `GET /health` (liveness) and `GET /health/ready` (PostgreSQL, Redis, MinIO and ChromaDB).
- Schema changes: `alembic revision --autogenerate -m "…"`, review the generated file, then `alembic upgrade head`.
- Use a paid LLM tier or a higher rate limit for real cohorts. Free tiers rate-limit and slow down turns.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Backend exits with `JWT_SECRET must be set…` | Set a random secret of at least 32 characters in `.env` |
| An answer stays on "Evaluating" or shows "Retry evaluation" | Check the worker is running (`docker compose ps`) and the LLM key works (`check_grok.py`); then use **Retry evaluation** |
| Turns are slow, logs show `llm_provider_error` / 429 | The LLM provider is rate-limiting; the system waits and retries automatically. Use a higher tier for heavy use |
| A page says "Institution access required" | Another account signed in on the same browser; sign in again, or use a private window for the second account |
| Questions are read in the browser's voice | The Piper voice is missing; run `download_speech_models.sh` |
| Live video never appears for monitors | The network blocks peer-to-peer; add a TURN server to `WEBRTC_ICE_SERVERS` |
| Presigned file links fail | Set `MINIO_PUBLIC_ENDPOINT` to a host the browser can reach (e.g. `localhost:9000`) |
| RAG returns nothing after a Chroma wipe | Run `scripts/reindex_chroma.py --reset` |

---

## Contributing

1. Create a branch from `main`.
2. Enable the secret-scanning hook: `git config core.hooksPath .githooks`.
3. Keep changes covered by tests. Run `pytest` in `backend/` and `npm test` in `frontend/` before opening a pull
   request.
4. Never commit `.env`, keys, database dumps or recordings.

---

## Roadmap

- Human review and override of AI evaluations
- Coding-interview environment
- Multilingual speech-to-text and text-to-speech
- Cohort benchmarking and analytics exports
- PostgreSQL row-level security as an additional isolation layer
- Fine-grained audit logs

---

## Author

**Sanjay Teja** · [github.com/SanjayTeja01](https://github.com/SanjayTeja01)

No license file has been added yet, so all rights are reserved by the author. Contact the author before reusing the code.
