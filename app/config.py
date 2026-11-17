"""
Configuration management and API key loading.
"""
# fmt: skip
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# General-purpose default aspects (domain-agnostic)
DEFAULT_ASPECTS = [
    "quality",
    "value",
    "service",
    "features",
    "reliability",
    "usability",
]

# Model configuration
SENTENCE_TRANSFORMER_MODEL = "all-MiniLM-L6-v2"
CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Claude (API key read from ANTHROPIC_API_KEY, loaded from .env above)
CLAUDE_MODEL = "claude-sonnet-5-5"
# Effort per task type. "low" suits classification; report writing gets a bit more.
LABEL_EFFORT = "low"
WRITING_EFFORT = "medium"
