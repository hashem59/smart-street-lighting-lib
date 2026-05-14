"""
Centralised LLM configuration.

All LM Studio connection settings are read from environment variables once
and imported by other modules. No hardcoded fallbacks scattered across files.
"""

import os

from dotenv import load_dotenv

# Walks up from CWD to find a `.env`; works for both local dev and installed package.
load_dotenv()

# --- LM Studio connection ---

LM_STUDIO_BASE_URL: str = os.environ.get(
    "LM_STUDIO_BASE_URL", "http://localhost:1234/v1"
)

LM_STUDIO_LLM_MODEL: str = os.environ.get(
    "LM_STUDIO_LLM_MODEL", "qwen2.5-7b-instruct"
)

LM_STUDIO_PARSE_MODEL: str = os.environ.get(
    "LM_STUDIO_PARSE_MODEL", LM_STUDIO_LLM_MODEL
)

LM_STUDIO_EMBED_MODEL: str = os.environ.get(
    "LM_STUDIO_EMBED_MODEL", "text-embedding-nomic-embed-text-v1.5"
)

# --- Timeouts (connect, read) in seconds ---

# For lightweight LLM calls (query parsing, intent classification)
FAST_LLM_TIMEOUT: tuple[int, int] = (10, 30)

# For heavy LLM calls (report generation via LlamaIndex).
# A 7B local model under sustained chat-completion load can take several
# minutes for a multi-section report; allow override via env var.
REPORT_LLM_TIMEOUT: tuple[int, int] = (
    10,
    int(os.environ.get("REPORT_LLM_TIMEOUT_SEC", "600")),
)

# --- Generation parameters for lightweight LLM calls ---

PARSE_MAX_TOKENS: int = 200
INTENT_MAX_TOKENS: int = 150
FAST_LLM_TEMPERATURE: float = 0.0
