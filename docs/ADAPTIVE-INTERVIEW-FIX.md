# Adaptive interview: root cause and fix

## Why the first answer "took the whole interview"

Evidence from your machine (session 63a4bad2, 19 Oct):

| Time (UTC) | What happened | Source |
|---|---|---|
| 09:29:30 | Interview started (15 min) | backend log, `interview_sessions` |
| 09:29:34 | Question 1 asked | `questions.asked_at` |
| 09:31:03 | Answer 1 received as **audio only**, no browser transcript | backend log `"input": "audio"` |
| 09:31:03 to 09:44:45 | Answer never transcribed, never evaluated, no 2nd question. Worker printed nothing. | `answers.transcript` empty, 0 rows in `evaluations`, worker log |
| 09:44:45 | Timer ended the interview; answer marked `interview_ended` | `answers.updated_at`, worker log |

Root causes:

1. **The containers were running old code.** `check_pipeline.py` crashed with `'Settings' object has no attribute 'stt_beam_size'`, a setting added by the earlier fixes. The images were never rebuilt, so none of those fixes ever ran, including browser transcription.
2. **Server speech-to-text froze with no time limit.** Each turn first transcribed the audio with faster-whisper inside the worker. That native call hung, and nothing could interrupt it, so evaluation and the next question never started. Your sessions on 9 and 12 Oct also stopped at question 1.
3. **All worker logs were silently dropped.** `configure_logging` wrote to `sys.stdout`. Inside Celery worker processes that is Celery's logging proxy, so every record looped back and was discarded. LLM calls, errors and tracebacks were invisible. Reproduced here: 0 JSON lines from the worker before the fix, all present after.

## What changed

**Turn order is enforced and recorded.** Each turn runs as two committed stages:
1. Evaluate the answer and update the performance profile.
2. Decide and generate the next question from that stored evaluation.

Every step is timestamped on the answer (`metadata.timeline`) and logged as `turn_step`:

```
answer_finalized
  -> evaluation_started
  -> evaluation_completed
  -> profile_updated
  -> next_question_decided
  -> next_question_generated
  -> next_question_presented
```

The next question cannot be chosen unless the stored evaluation belongs to the current answer.

**The adaptive policy uses the full evaluation, not just the score band.** It reads:
- technical correctness, completeness and depth;
- the evaluator's confidence;
- the concepts the answer missed.

New follow-up kinds:

| Kind | When it is used |
|---|---|
| `follow_up_gap` | The answer is right but misses a concept; the next question tests that concept. |
| `follow_up_clarify` | The answer is too vague to judge; same difficulty, no penalty. |

Two existing behaviours now use the same evidence:
- A wrong answer gets an easier diagnostic question.
- A concise but correct answer counts as strong, so it is not held back.

The cut-offs are `ADAPTIVE_*` settings, documented in `config/.env.example` and `AdaptiveConfig`. The question writer now receives:
- the concepts to target;
- a compact profile of per-topic averages and weak and strong topics, instead of the transcript.

The evaluator is told not to penalise brevity.

**No invented scores.**
- The old provisional score of 50 for "LLM failed" is gone.
- Evaluation gets 3 bounded attempts (`TURN_EVAL_ATTEMPTS`). After that the answer is `evaluation_failed`, the interview stays on that question, and the candidate gets a **Retry evaluation** button.
- A wrong key or model fails immediately with a clear error.

**Speech can't freeze a turn.**
- Server STT gives up after `STT_TIMEOUT_SECONDS` (90) and asks the candidate to answer again or type.
- TTS gives up after 20 s and falls back to the browser voice.

**Stuck-turn recovery.** A turn with no progress for 120 s is re-queued, at most twice. Every stage is idempotent, so an already-evaluated answer is never scored again.

**Final report.** It averages the stored per-question evaluations; nothing is re-evaluated. An answer still in progress when time runs out is evaluated once at the end, so it is not lost.

**Frontend.** The interview screen shows "Transcribing / Evaluating (attempt n) / Choosing your next question", and Retry when evaluation failed. It refreshes on the new events and polls every 3 s as a safety net.

## Test results (here)

- Backend tests: **112 passed**. 10 of them are new: the policy evidence cases, the order timeline, "never invents a score + retry", "last answer scored at the end", and STT hang timeout.
- Frontend: typecheck clean, 10 tests pass, production build OK.
- Full stack run here: real Postgres, Redis, Celery worker (4 processes) and API, with an OpenAI-compatible stand-in for Groq. Groq and HuggingFace are blocked from this sandbox.
  - `e2e-run-mock-llm.txt`: 6 turns with contrasting answers. Strong led to a harder follow-up, weak to an easier diagnostic, vague to a clarification. All steps were in order, about 1.7 s per turn, and the final score equals the mean of the per-question scores.
  - `failure-scenarios-run.txt`: a 20 s slow evaluation moves on normally; a failing evaluation stops after 3 attempts with no score and no new question, and Retry then continues; ending mid-evaluation still reports correctly.
  - Screenshots: `1-evaluating.png`, `2-evaluation-failed.png`, `3-next-question.png`.
- **Not yet run with real Groq.** That is the `adaptive_e2e.py` command below.

## Verify on your machine

```
docker compose up -d --build
docker compose exec backend python /app/scripts/adaptive_e2e.py
```

The second command creates a throwaway institution and student, answers 6 questions with deliberately strong, weak, vague and concise answers written by Groq, prints the timeline, scores and reasons for each turn, and ends with `RESULT: PASS` or the checks that failed.

Your previous files are backed up in `backup-before-adaptive/before-adaptive.tgz`.
