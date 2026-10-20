"""Application settings. Every secret is read from the environment — nothing is hard-coded."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: str = "development"
    app_name: str = "End-to-End Interview Agent"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"
    frontend_url: str = "http://localhost:3000"

    database_url: str = "postgresql+psycopg://interview:interview@localhost:5432/interview_agent"

    jwt_secret: SecretStr = SecretStr("")
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    cookie_secure: bool = False

    # "grok" (xAI, key starts xai-), "groq" (groq.com, key starts gsk_) or "gemini" (optional, needs google-genai)
    llm_provider: str = "grok"
    xai_api_key: SecretStr = SecretStr("")
    xai_base_url: str = "https://api.x.ai/v1"
    xai_model: str = "grok-4.7"
    # Grok 4.x always reasons; "low" keeps each call fast. Use "none" for a model that does not accept the setting.
    xai_reasoning_effort: str = "low"
    groq_api_key: SecretStr = SecretStr("")
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "openai/gpt-oss-120b"
    # gpt-oss models accept low/medium/high; use "none" for llama models
    groq_reasoning_effort: str = "low"
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.8-flash"
    # true = call Gemini through the Vertex AI endpoint (needed for some "AQ." service-account-bound keys)
    gemini_use_vertex: bool = False
    # Comma-separated models tried when the main one is overloaded (503/429)
    gemini_fallback_models: str = ""
    # Per-call HTTP timeout and extra attempts. Kept small: a live interview cannot wait minutes per question.
    llm_timeout_seconds: int = 45
    llm_max_retries: int = 1
    llm_rate_limit_per_minute: int = 60
    # On HTTP 429 the client waits the provider's Retry-After, at most this long, before its retry
    llm_rate_limit_max_wait_seconds: int = 15

    # Live interview turn handling. A turn is: answer finalised -> evaluated -> profile updated -> next question.
    # Evaluation attempts per answer (each attempt already includes LLM_MAX_RETRIES quick retries). When all fail the
    # answer is marked evaluation_failed and the candidate can retry; no score is ever invented.
    turn_eval_attempts: int = 3
    # A turn with no progress for this long (worker crash, lost task) is re-queued by the interview clock.
    turn_stuck_seconds: int = 120

    # Adaptive policy cut-offs (rubric 0-10 scale; see app/domain/adaptive.AdaptiveConfig for what each one does)
    adaptive_clarify_confidence: float = 0.5
    adaptive_gap_min_correctness: float = 6.0
    adaptive_concise_correct_min: float = 8.0
    adaptive_concise_complete_min: float = 7.0

    # "local" = MiniLM ONNX model bundled with chromadb (no API key; xAI has no embeddings API), or "gemini"
    embedding_provider: str = "local"
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_version: str = "1"
    embedding_dimensions: int = 384

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = ""
    minio_secret_key: SecretStr = SecretStr("")
    minio_bucket: str = "interview-agent"
    minio_secure: bool = False
    minio_public_endpoint: str | None = None
    presigned_url_expiry_seconds: int = 300

    redis_url: str = "redis://localhost:6379/0"

    chroma_host: str = "localhost"
    chroma_port: int = 8000
    chroma_collection: str = "knowledge_chunks"

    stt_provider: str = "faster_whisper"
    stt_model: str = "base.en"
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"
    # beam 1 (greedy) is several times faster on CPU than 5 with nearly the same accuracy for English answers
    stt_beam_size: int = 1
    # threads per transcription; 0 = all cores (fine for one interview, set 2-4 when several run at once)
    stt_cpu_threads: int = 0
    # Hard limits for server-side speech so a stuck model can never freeze a turn (see speech.call_with_timeout).
    # Transcription covers the first model load too; on timeout the candidate is asked to answer again or type.
    stt_timeout_seconds: int = 90
    tts_timeout_seconds: int = 20
    tts_provider: str = "piper"
    piper_voice_path: str = "/models/piper/en_US-lessac-medium.onnx"

    webrtc_ice_servers: str = "stun:stun.l.google.com:19302"

    max_upload_mb: int = 20
    max_media_upload_mb: int = 100

    # Celery runs tasks inline when true (tests / single-process dev only)
    celery_eager: bool = Field(default=False)

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_strength(cls, v: SecretStr, info):  # noqa: ANN001
        # Validated lazily in `require_secrets` so tooling (alembic, tests) can import settings.
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def ice_server_list(self) -> list[str]:
        return [s.strip() for s in self.webrtc_ice_servers.split(",") if s.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    def require_secrets(self) -> None:
        """Fail fast at API/worker start-up if mandatory secrets are missing or weak."""
        secret = self.jwt_secret.get_secret_value()
        if len(secret) < 32 or secret.startswith("replace-with"):
            raise RuntimeError("JWT_SECRET must be set to a random value of at least 32 characters")
        provider = self.llm_provider.strip().lower()
        if provider in ("grok", "xai") and not self.xai_api_key.get_secret_value():
            raise RuntimeError("XAI_API_KEY must be provided via the environment (LLM_PROVIDER=grok)")
        if provider == "groq" and not self.groq_api_key.get_secret_value():
            raise RuntimeError("GROQ_API_KEY must be provided via the environment (LLM_PROVIDER=groq)")
        if provider == "gemini" and not self.gemini_api_key.get_secret_value():
            raise RuntimeError("GEMINI_API_KEY must be provided via the environment")


@lru_cache
def get_settings() -> Settings:
    return Settings()
