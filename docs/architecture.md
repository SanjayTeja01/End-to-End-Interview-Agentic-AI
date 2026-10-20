# Architecture notes

## Source-of-truth rules

| Store | Role | Rebuildable? |
|---|---|---|
| PostgreSQL | Structured source of truth: identity, tenancy, interviews, sessions, questions, answers, evaluations, snapshots, reports, KB metadata, jobs | No — back it up |
| MinIO | Binary source of truth (private bucket) | No — back it up |
| ChromaDB | Derived vector index | Yes — `scripts/reindex_chroma.py` |
| Redis | Celery broker, pub/sub fan-out, rate-limit counters | Transient |

PostgreSQL stores **object keys** (`files.object_key`), never URLs. Access goes object key → authorisation → presigned
URL (default 5 minutes).

### Object key convention (tenant-prefixed)

```
resumes/{institute_id}/{candidate_id}/{uuid}.pdf
knowledge/{institute_id}/{document_id}/version-{n}.pdf
interviews/{institute_id}/{interview_id}/{candidate_id}/audio/{uuid}.webm
interviews/{institute_id}/{interview_id}/{candidate_id}/video/{uuid}.webm
interviews/{institute_id}/{interview_id}/{candidate_id}/tts/{uuid}.wav
reports/{institute_id}/{candidate_id}/{interview_id}/report-v{n}.pdf
```

The keys add an `institute_id` segment to the examples in the specification, so multi-tenancy is visible at the storage
layer. `store_file` refuses any key whose tenant segment doesn't match the record it is written for.

## Data model (abridged)

`institutions` ─< `users` ─1 `candidate_profiles`
`users` ─< `resumes` (versioned) · `candidate_skills` (evidence per source: resume / interview / profile)
`roles` ─< `interviews` ─< `role_skills` (per-interview requirements, approval status) · `interview_candidates` (eligibility/assignment)
`interviews` ─< `interview_sessions` (one per candidate; JSON state snapshot) ─< `questions` ─1 `answers` ─1 `evaluations`
`interview_sessions` ─1 `performance` · `readiness` · `interview_history` · `reports` (versioned) · `interview_recommendations`
`knowledge_documents` ─< `knowledge_document_versions` ; `files` (blob metadata) ; `jobs` (async status)
`skill_gaps` = required − estimated level, with priority = gap × importance and the evidence used.

Performance and readiness are **derived from evaluations**. They are snapshotted when a session completes, together with
`method_version` and the weights used, so historical reports don't change when the algorithms change later.

## Interview lifecycle

```
draft ─▶ pending_approval (AI-inferred requirements) ─▶ approved ─▶ scheduled ─▶ active ─▶ completed ─▶ closed
   └──────────── (institution-provided skills) ──────────▲                 └─▶ cancelled (from any pre-active state)
```

`app/domain/lifecycle.py` rejects invalid transitions. Activation requires `skill_approval_state ∈ {approved, not_required}`
and at least one approved skill. `scheduled` becomes `active` at `start_time` and `completed` after `end_time`
(evaluated on read, so no scheduler is needed).

Sessions: `initializing → in_progress → finalizing → completed` (or `failed`). There is one session per candidate per
interview, and reconnecting resumes it.

## LangGraph design

The interview is turn-based and waits on a human, so the graph does not run as a long-lived process. Each turn is a
**single graph invocation** inside a Celery task. The Supervisor node is the entry point and routes on `next_action`:

```
START → supervisor ─┬─ initialize ─▶ load_context → plan_interview → decide_next ─┬─▶ retrieve_context → generate_question → END
                    ├─ process_answer ─▶ evaluate_answer ───────────▲              ├─▶ generate_question → END
                    └─ finalize ───────────────────────────────▶ performance ◀─────┘ (complete)
                                                                  → readiness → recommendations → report → END
```

The resulting state is JSON-serialised into `interview_sessions.state` under a row lock (`SELECT … FOR UPDATE`), so turns
for one session are serialised and survive worker restarts. Binary data never enters the state; only file ids and object keys do.

### What is deterministic vs. LLM-generated

| Decision | Made by |
|---|---|
| Which topic next, difficulty, follow-up vs. new topic, when to stop | `domain/adaptive.py` (deterministic, unit-tested) |
| Coverage plan and priorities | `domain/planning.py` |
| Final answer score (weighted rubric), bands | `domain/rubric.py` |
| Performance, readiness, recommendations | `domain/performance.py`, `domain/readiness.py`, `domain/recommendations.py` |
| Eligibility / access | `domain/eligibility.py` + backend authorisation |
| Question wording, criterion scores with evidence, resume extraction, proposed requirements, report narrative | Grok (xAI) via validated Pydantic schemas |

### Explainability

Each evaluation stores criterion scores, grounded strengths (verbatim quotes are checked against the transcript),
weaknesses, missing concepts, improvement actions, a suggested answer structure, an evidence summary, the rubric weights,
and the **reason for the next question** (taken from the policy decision). Each question stores the decision that produced
it. Hidden reasoning is never requested or stored.

### Failure handling

* LLM: schema-validated, retried on malformed output with backoff, and rate-limited through Redis. A failed question
  generation falls back to a templated question. If evaluation still fails on the worker's final retry, the answer gets
  a provisional evaluation (confidence 0, `needs_review`) so the interview can continue. Report narrative falls back to a template.
* STT failure: the task retries. If that still fails, the candidate is asked to answer again; the audio is kept.
* Answers: an idempotency key makes resubmission safe, a second answer to the same question is rejected, and an answer
  to a question that is no longer current is rejected.
* Realtime: publishing is best-effort; state is always in Postgres. Clients get a full snapshot on every (re)connect and
  poll as a safety net.
* Duration: a delayed Celery task terminates the interview server-side even if the browser closes.

## Real-time channels

* `interview:session:{id}` — events: `question`, `answer_received`, `transcript`, `evaluation_update`, `session_state`,
  `connection_status`, `interview_finalizing`, `interview_completed`, `error`.
* `interview:signal:{id}:{candidate|monitor}` — WebRTC SDP/ICE relay. The candidate publishes its camera stream
  peer-to-peer to each monitor; the server only relays signalling.

## Memory layers

| Layer | Where |
|---|---|
| Session memory | `interview_sessions` row + JSON state (current question, topic, difficulty, progress, transcript, topic stats) |
| Candidate memory | `candidate_profiles`, `resumes.analysis`, `candidate_skills`, open `interview_recommendations` |
| Historical memory | `interview_history` (weak/strong topics, difficulty responses, repeated mistakes) → loaded at the next interview and boosts weak topics in the plan |
| Knowledge memory | `knowledge_documents` + ChromaDB chunks (tenant-filtered) |

"Continuous learning" here means that historical candidate performance changes how future interviews adapt. No model is
fine-tuned or retrained.
