"""Langfuse Observability and Tracing integration for LangGraph and LiteLLM.

Provides:
- Graceful detection of Langfuse environment credentials.
- Automatic callback handler generation for LangGraph execution traces.
- Automatic LiteLLM callback hook configuration for LLM call observability.
- Safe flush utility for script lifecycle completion.
"""

import logging
import os
import sys
import types
from typing import Any

logger = logging.getLogger(__name__)


def _install_langfuse_compatibility_alias() -> None:
    """Expose the legacy ``langfuse.langchain`` import when only callback exists.

    Langfuse v2 distributions differ depending on optional extras. Keeping this
    tiny alias at the infrastructure boundary lets existing integrations and
    downstream tests use the stable callback path without making tracing a
    mandatory runtime dependency.
    """
    try:
        import langfuse
        from langfuse.callback import CallbackHandler

        if not hasattr(langfuse, "langchain"):
            module = types.ModuleType("langfuse.langchain")
            module.CallbackHandler = CallbackHandler
            sys.modules["langfuse.langchain"] = module
            setattr(langfuse, "langchain", module)
    except Exception:
        # Tracing is optional; absence of Langfuse must never break the app.
        return


_install_langfuse_compatibility_alias()


def is_langfuse_configured() -> bool:
    """Check if Langfuse credentials are present in environment."""
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    return bool(public_key and secret_key)


def get_langfuse_callback() -> Any | None:
    """Initialize and return a Langfuse CallbackHandler for LangGraph.

    Returns:
        CallbackHandler instance if configured and installed, else None.
    """
    if not is_langfuse_configured():
        return None

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    host = (
        os.getenv("LANGFUSE_HOST")
        or os.getenv("LANGFUSE_BASE_URL")
        or "https://cloud.langfuse.com"
    ).strip()

    # Configure LiteLLM callbacks if litellm is available
    try:
        import litellm

        if hasattr(litellm, "success_callback"):
            if "langfuse" not in litellm.success_callback:
                litellm.success_callback.append("langfuse")
        if hasattr(litellm, "failure_callback"):
            if "langfuse" not in litellm.failure_callback:
                litellm.failure_callback.append("langfuse")
    except Exception as exc:
        logger.debug("Failed to configure litellm callbacks for Langfuse: %s", exc)

    # Initialize Langfuse CallbackHandler for LangGraph
    try:
        try:
            from langfuse.langchain import CallbackHandler
        except ImportError:
            from langfuse.callback import CallbackHandler

        handler = CallbackHandler(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
        )
        logger.info("Langfuse tracing enabled (host: %s)", host)
        return handler
    except ImportError:
        logger.warning(
            "Langfuse keys are configured in .env but 'langfuse' package is not installed. "
            "Run 'pip install langfuse' to enable LangGraph tracing."
        )
        return None
    except Exception as exc:
        logger.error("Failed to initialize Langfuse CallbackHandler: %s", exc)
        return None


def flush_tracing(handler: Any | None = None) -> None:
    """Flush pending Langfuse traces before process exit."""
    if handler is not None and hasattr(handler, "flush"):
        try:
            handler.flush()
        except Exception as exc:
            logger.debug("Error flushing Langfuse handler: %s", exc)

    try:
        from langfuse import Langfuse

        # Langfuse client global flush if initialized
        client = Langfuse()
        client.flush()
    except Exception:
        pass
