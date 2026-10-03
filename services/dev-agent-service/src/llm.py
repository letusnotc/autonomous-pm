"""
llm.py – Loads the shared packages/llm-client, wherever the service runs from.

Locally the package lives at <repo>/packages; in Docker it's copied to
/app/packages. APM_PACKAGES_DIR overrides both.
"""
import os
import sys
from pathlib import Path


def _packages_dir() -> Path:
    candidates = [Path(os.environ["APM_PACKAGES_DIR"])] if os.getenv("APM_PACKAGES_DIR") else []
    candidates += [p / "packages" for p in Path(__file__).resolve().parents]
    for c in candidates:
        if (c / "llm-client" / "llm_client.py").exists():
            return c
    raise ImportError("packages/llm-client not found – set APM_PACKAGES_DIR")


sys.path.insert(0, str(_packages_dir() / "llm-client"))
from llm_client import call_llm, parse_json_response, active_model, LLM_PROVIDER  # noqa: E402

_KEY_VARS = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY"}


def llm_configured() -> bool:
    """True when the selected provider has a key that isn't a template placeholder."""
    key = os.getenv(_KEY_VARS.get(LLM_PROVIDER, "OPENAI_API_KEY"), "")
    return bool(key) and not key.endswith("...")


__all__ = ["call_llm", "parse_json_response", "active_model", "llm_configured"]
