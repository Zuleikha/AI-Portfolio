"""The single place the application decides which LLM provider to use.

Mirrors :func:`app.rag.embeddings.get_embedder`: one function, driven by
configuration, so adding a vendor is a new module plus a branch here — never a
change to the service, the agent, or the API layer.

**Three providers are registered, and the default is the free one.**
``BKA_LLM_PROVIDER`` accepts ``mock`` (default), ``anthropic`` and ``openai``.
The default is deliberately unchanged by Stage 5: cloning this repository and
running the suite still costs nothing, and a real API call — a **paid** call —
happens only when somebody deliberately sets that variable *and* supplies a key.
Two properties keep that honest rather than aspirational: the default is
asserted by a test, and neither adapter can be constructed without a key.

**Vendor names appear here; vendor code does not.** The two SDK imports live in
the adapter modules, and are reached through a deferred import inside the branch
that needs one. So this module stays importable — and the whole application
stays runnable on the mock — even if neither SDK is installed. An
:class:`ImportError` from a missing SDK is translated into a configuration
error, because "the package is not installed" is an environment problem and
should read like one.

**An unknown provider is a loud failure, not a fallback.** Falling back to the
mock would be far worse than an error: the application would start, answer
questions, and look entirely healthy while a deterministic stub stood in for a
model — and the only evidence would be a wording change nobody reads.
"""

from __future__ import annotations

from app.core.cli import RULE
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.tracing import traced
from app.llm.base import LLMConfigurationError, LLMProvider
from app.llm.mock import MOCK_PROVIDER_ID, MockLLMProvider
from app.llm.service import LLMService

logger = get_logger(__name__)

ANTHROPIC_PROVIDER_ID = "anthropic"
OPENAI_PROVIDER_ID = "openai"

AVAILABLE_PROVIDERS = (MOCK_PROVIDER_ID, ANTHROPIC_PROVIDER_ID, OPENAI_PROVIDER_ID)
"""Providers this build can construct. The mock is first, and is the default."""

PAID_PROVIDERS = (ANTHROPIC_PROVIDER_ID, OPENAI_PROVIDER_ID)
"""Providers whose ``complete()`` costs money. Named so the fact is greppable
rather than folklore — the CLI reads this to warn before it runs."""


def is_paid_provider(settings: Settings | None = None) -> bool:
    """Whether the configured provider bills for every ``complete()`` call.

    Exists so the CLIs can warn before spending rather than after. The knowledge
    of which providers cost money lives here, beside the registry, so a future
    adapter cannot be added to one list and forgotten in the other.
    """
    return (settings or get_settings()).llm_provider in PAID_PROVIDERS


def warn_if_paid(settings: Settings | None = None) -> bool:
    """Print a cost warning when a billed provider is configured.

    Lives beside :data:`PAID_PROVIDERS` because it is the money guard, and a
    money guard with two copies is a money guard that can be corrected in one
    place and left stale in the other. Both CLIs held their own copy until
    Stage 15, and their wording had already drifted apart.

    Args:
        settings: Application settings. Defaults to the cached singleton.

    Returns:
        Whether the configured provider costs money. Callers use this to decide
        whether to refuse outright -- a warning alone never stops a run.
    """
    if not is_paid_provider(settings):
        return False
    resolved = settings or get_settings()
    print(RULE)
    print(f"!! BKA_LLM_PROVIDER={resolved.llm_provider} - this is a PAID API.")
    print("!! Every answered question is a billed call. Unset the variable, or")
    print("!! set BKA_LLM_PROVIDER=mock, to run free.")
    print(RULE)
    return True


@traced
def get_provider(settings: Settings | None = None) -> LLMProvider:
    """Build the configured provider.

    Args:
        settings: Application settings. Defaults to the cached singleton.

    Returns:
        An :class:`~app.llm.base.LLMProvider`.

    Raises:
        LLMConfigurationError: If ``BKA_LLM_PROVIDER`` names a provider this
            build cannot construct, if the named provider's SDK is not
            installed, or if a paid provider is configured without a key.
    """
    resolved = settings or get_settings()
    requested = resolved.llm_provider

    if requested == MOCK_PROVIDER_ID:
        logger.info("llm.provider_selected", provider=requested, paid=False)
        return MockLLMProvider()

    if requested in PAID_PROVIDERS:
        provider = _build_paid_provider(requested, resolved)
        logger.info(
            "llm.provider_selected",
            provider=requested,
            model=provider.model_id,
            # Loud in the log, because this is the line that separates a free
            # run from a billed one.
            paid=True,
        )
        return provider

    raise LLMConfigurationError(
        f"BKA_LLM_PROVIDER='{requested}' is not available in this build. "
        f"Available: {', '.join(AVAILABLE_PROVIDERS)}. The mock is the default "
        "and is never substituted silently for a provider that was asked for."
    )


def _build_paid_provider(requested: str, settings: Settings) -> LLMProvider:
    """Import and construct one of the vendor adapters.

    The import is deferred to here so that a missing SDK cannot stop the
    application from starting, running on the mock, or serving ``/health``.
    """
    try:
        if requested == ANTHROPIC_PROVIDER_ID:
            from app.llm.anthropic_provider import AnthropicProvider

            return AnthropicProvider(settings)

        from app.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(settings)
    except ImportError as exc:
        raise LLMConfigurationError(
            f"BKA_LLM_PROVIDER='{requested}' needs its SDK, which is not "
            f"installed in this environment ({exc}). Install the pinned "
            "dependencies: pip install -r requirements.txt"
        ) from exc


@traced
def get_llm_service(settings: Settings | None = None) -> LLMService:
    """Build an :class:`~app.llm.service.LLMService` over the configured provider.

    The convenience entry point for callers that do not care which provider is
    in use — which, by design, is all of them.

    Args:
        settings: Application settings. Defaults to the cached singleton.

    Returns:
        A ready-to-use service.

    Raises:
        LLMConfigurationError: If the configured provider is unavailable.
    """
    resolved = settings or get_settings()
    return LLMService(get_provider(resolved), resolved)
