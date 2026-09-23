"""The two vendor adapters: request shape, response parsing, error translation.

**Nothing here makes a network call or costs anything.** Every test injects a
fake client that records what it was asked for and returns a hand-built SDK
object. That is possible because both adapters take an optional ``client``, and
it is the reason a real adapter can be tested at all without an account.

Three properties are asserted throughout:

* **The seam holds.** Both adapters satisfy ``LLMProvider`` and return the same
  ``LLMResponse`` shape from very different vendor payloads. The final class
  runs the identical assertions against both, which is what makes the
  abstraction evidence rather than a claim.
* **The translation is complete.** Every error in each SDK's hierarchy maps to a
  typed application error with the right ``retryable`` flag, and the ordering
  traps (a timeout *is* a connection error; a 500 *is* a status error) are
  asserted rather than assumed.
* **A missing key stops everything before a client exists**, so no test can
  reach a vendor even by mistake.
"""

from __future__ import annotations

import httpx2
import pytest

from app.core.config import Settings
from app.llm.anthropic_provider import (
    ANTHROPIC_PROVIDER_ID,
    AnthropicProvider,
)
from app.llm.anthropic_provider import DEFAULT_MODEL as ANTHROPIC_DEFAULT_MODEL
from app.llm.base import (
    LLMConfigurationError,
    LLMConnectionError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
)
from app.llm.models import CompletionRequest, LLMMessage
from app.llm.openai_provider import DEFAULT_MODEL as OPENAI_DEFAULT_MODEL
from app.llm.openai_provider import OPENAI_PROVIDER_ID, OpenAIProvider

# --- Fakes: SDK-shaped objects, built by hand -----------------------------


class Recorder:
    """Records the kwargs of the one call the adapter makes, and replies."""

    def __init__(self, reply=None, raises: Exception | None = None) -> None:
        self.reply = reply
        self.raises = raises
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return self.reply

    @property
    def last(self) -> dict:
        assert self.calls, "the adapter made no call"
        return self.calls[-1]


class FakeAnthropicClient:
    def __init__(self, reply=None, raises: Exception | None = None) -> None:
        self.messages = type(
            "Messages", (), {"create": staticmethod(Recorder(reply, raises))}
        )()

    @property
    def recorder(self) -> Recorder:
        return self.messages.create


class FakeOpenAIClient:
    def __init__(self, reply=None, raises: Exception | None = None) -> None:
        recorder = Recorder(reply, raises)
        completions = type("Completions", (), {"create": staticmethod(recorder)})()
        self.chat = type("Chat", (), {"completions": completions})()
        self._recorder = recorder

    @property
    def recorder(self) -> Recorder:
        return self._recorder


class Block:
    def __init__(self, type_: str, text: str = "") -> None:
        self.type = type_
        self.text = text


class AnthropicUsage:
    def __init__(self, input_tokens=0, output_tokens=0, cache_read_input_tokens=0):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_input_tokens = cache_read_input_tokens


class AnthropicMessage:
    def __init__(
        self, content, stop_reason="end_turn", model="claude-opus-5", usage=None
    ):
        self.content = content
        self.stop_reason = stop_reason
        self.model = model
        self.usage = usage or AnthropicUsage(120, 45, 0)


class OpenAIMessage:
    def __init__(self, content: str | None, refusal: str | None = None) -> None:
        self.content = content
        self.refusal = refusal


class OpenAIChoice:
    def __init__(self, message, finish_reason="stop") -> None:
        self.message = message
        self.finish_reason = finish_reason


class OpenAIPromptDetails:
    def __init__(self, cached_tokens=0) -> None:
        self.cached_tokens = cached_tokens


class OpenAIUsage:
    def __init__(self, prompt_tokens=0, completion_tokens=0, cached_tokens=0) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.prompt_tokens_details = OpenAIPromptDetails(cached_tokens)


class OpenAICompletion:
    def __init__(self, choices, model="gpt-5.5", usage=None) -> None:
        self.choices = choices
        self.model = model
        self.usage = usage or OpenAIUsage(120, 45, 0)


def anthropic_reply(text="Grounded answer [1].", stop_reason="end_turn", **kwargs):
    return AnthropicMessage([Block("text", text)], stop_reason=stop_reason, **kwargs)


def openai_reply(text="Grounded answer [1].", finish_reason="stop", refusal=None, **kw):
    choice = OpenAIChoice(OpenAIMessage(text, refusal), finish_reason)
    return OpenAICompletion([choice], **kw)


def keyed(settings: Settings, provider: str) -> Settings:
    """Settings with a placeholder key. Never used to reach anything."""
    return settings.model_copy(
        update={"llm_provider": provider, "llm_api_key": "not-a-real-key-for-tests"}
    )


def request(user: str = "Question: why?") -> CompletionRequest:
    return CompletionRequest(
        system="Frozen system instructions.",
        messages=(LLMMessage(role="user", content=user),),
        max_tokens=1024,
    )


def status_error(sdk, cls, code: int, headers: dict | None = None):
    """Build a real SDK status error, so the tests exercise the real hierarchy."""
    http_request = httpx2.Request("POST", "https://example.invalid/v1")
    response = httpx2.Response(code, headers=headers or {}, request=http_request)
    return cls("boom", response=response, body=None)


# --- Construction ---------------------------------------------------------


class TestConstruction:
    @pytest.mark.parametrize(
        ("cls", "provider"),
        [(AnthropicProvider, "anthropic"), (OpenAIProvider, "openai")],
    )
    def test_a_missing_key_refuses_before_any_client_exists(
        self, llm_settings: Settings, cls, provider
    ):
        settings = llm_settings.model_copy(
            update={"llm_provider": provider, "llm_api_key": None}
        )
        with pytest.raises(LLMConfigurationError) as excinfo:
            cls(settings)
        assert "BKA_LLM_API_KEY" in str(excinfo.value)

    @pytest.mark.parametrize(
        ("cls", "provider"),
        [(AnthropicProvider, "anthropic"), (OpenAIProvider, "openai")],
    )
    def test_an_injected_client_needs_no_key_at_all(
        self, llm_settings: Settings, cls, provider
    ):
        """What keeps this whole test file free."""
        settings = llm_settings.model_copy(update={"llm_api_key": None})
        assert cls(settings, client=object()) is not None

    @pytest.mark.parametrize(
        ("cls", "expected"),
        [
            (AnthropicProvider, ANTHROPIC_DEFAULT_MODEL),
            (OpenAIProvider, OPENAI_DEFAULT_MODEL),
        ],
    )
    def test_each_adapter_owns_its_default_model(
        self, llm_settings: Settings, cls, expected
    ):
        assert cls(llm_settings, client=object()).model_id == expected

    @pytest.mark.parametrize("cls", [AnthropicProvider, OpenAIProvider])
    def test_a_configured_model_overrides_the_default(
        self, llm_settings: Settings, cls
    ):
        settings = llm_settings.model_copy(update={"llm_model": "some-other-model"})
        assert cls(settings, client=object()).model_id == "some-other-model"

    @pytest.mark.parametrize("cls", [AnthropicProvider, OpenAIProvider])
    def test_both_satisfy_the_provider_protocol(self, llm_settings: Settings, cls):
        assert isinstance(cls(llm_settings, client=object()), LLMProvider)

    def test_provider_ids_are_distinct_and_stable(self, llm_settings: Settings):
        a = AnthropicProvider(llm_settings, client=object())
        o = OpenAIProvider(llm_settings, client=object())
        assert a.provider_id == ANTHROPIC_PROVIDER_ID == "anthropic"
        assert o.provider_id == OPENAI_PROVIDER_ID == "openai"
        assert a.provider_id != o.provider_id


# --- What each adapter actually sends -------------------------------------


class TestAnthropicRequest:
    def test_the_system_prompt_goes_in_the_top_level_parameter(
        self, llm_settings: Settings
    ):
        client = FakeAnthropicClient(anthropic_reply())
        AnthropicProvider(llm_settings, client=client).complete(request())
        assert client.recorder.last["system"] == "Frozen system instructions."

    def test_the_system_prompt_is_not_smuggled_into_the_messages(
        self, llm_settings: Settings
    ):
        client = FakeAnthropicClient(anthropic_reply())
        AnthropicProvider(llm_settings, client=client).complete(request())
        roles = [m["role"] for m in client.recorder.last["messages"]]
        assert "system" not in roles

    def test_the_user_turn_is_passed_through_verbatim(self, llm_settings: Settings):
        client = FakeAnthropicClient(anthropic_reply())
        AnthropicProvider(llm_settings, client=client).complete(request("ask me this"))
        assert client.recorder.last["messages"] == [
            {"role": "user", "content": "ask me this"}
        ]

    def test_max_tokens_is_the_requests_ceiling(self, llm_settings: Settings):
        client = FakeAnthropicClient(anthropic_reply())
        AnthropicProvider(llm_settings, client=client).complete(request())
        assert client.recorder.last["max_tokens"] == 1024

    def test_no_sampling_parameters_are_sent(self, llm_settings: Settings):
        """Current models reject them, and faithfulness beats variety here."""
        client = FakeAnthropicClient(anthropic_reply())
        AnthropicProvider(llm_settings, client=client).complete(request())
        sent = client.recorder.last
        for banned in ("temperature", "top_p", "top_k", "thinking"):
            assert banned not in sent


class TestOpenAIRequest:
    def test_the_system_prompt_becomes_a_system_role_message(
        self, llm_settings: Settings
    ):
        """The difference the seam absorbs: same prompt, other shape."""
        client = FakeOpenAIClient(openai_reply())
        OpenAIProvider(llm_settings, client=client).complete(request())
        messages = client.recorder.last["messages"]
        assert messages[0] == {
            "role": "system",
            "content": "Frozen system instructions.",
        }

    def test_there_is_no_top_level_system_parameter(self, llm_settings: Settings):
        client = FakeOpenAIClient(openai_reply())
        OpenAIProvider(llm_settings, client=client).complete(request())
        assert "system" not in client.recorder.last

    def test_the_user_turn_follows_the_system_message(self, llm_settings: Settings):
        client = FakeOpenAIClient(openai_reply())
        OpenAIProvider(llm_settings, client=client).complete(request("ask me this"))
        assert client.recorder.last["messages"][1] == {
            "role": "user",
            "content": "ask me this",
        }

    def test_the_ceiling_uses_max_completion_tokens_not_max_tokens(
        self, llm_settings: Settings
    ):
        """`max_tokens` is deprecated here and rejected by reasoning models."""
        client = FakeOpenAIClient(openai_reply())
        OpenAIProvider(llm_settings, client=client).complete(request())
        assert client.recorder.last["max_completion_tokens"] == 1024
        assert "max_tokens" not in client.recorder.last

    def test_no_sampling_parameters_are_sent(self, llm_settings: Settings):
        client = FakeOpenAIClient(openai_reply())
        OpenAIProvider(llm_settings, client=client).complete(request())
        for banned in ("temperature", "top_p", "n"):
            assert banned not in client.recorder.last


# --- What each adapter makes of the reply ---------------------------------


class TestAnthropicResponse:
    def test_text_is_read_from_the_text_blocks(self, llm_settings: Settings):
        client = FakeAnthropicClient(anthropic_reply("The switch rejects it [1]."))
        response = AnthropicProvider(llm_settings, client=client).complete(request())
        assert response.text == "The switch rejects it [1]."

    def test_a_leading_thinking_block_is_not_mistaken_for_the_answer(
        self, llm_settings: Settings
    ):
        """Reading content[0] positionally would return reasoning as the answer."""
        message = AnthropicMessage(
            [Block("thinking", "internal reasoning"), Block("text", "The answer [1].")]
        )
        client = FakeAnthropicClient(message)
        response = AnthropicProvider(llm_settings, client=client).complete(request())
        assert response.text == "The answer [1]."
        assert "internal reasoning" not in response.text

    def test_several_text_blocks_are_concatenated(self, llm_settings: Settings):
        message = AnthropicMessage([Block("text", "One. "), Block("text", "Two.")])
        client = FakeAnthropicClient(message)
        response = AnthropicProvider(llm_settings, client=client).complete(request())
        assert response.text == "One. Two."

    def test_the_answering_model_is_recorded_from_the_reply(
        self, llm_settings: Settings
    ):
        """Not the model that was asked for: they differ under a fallback."""
        client = FakeAnthropicClient(anthropic_reply(model="claude-opus-4-8"))
        response = AnthropicProvider(llm_settings, client=client).complete(request())
        assert response.model_id == "claude-opus-4-8"

    def test_usage_is_translated(self, llm_settings: Settings):
        message = AnthropicMessage(
            [Block("text", "x")], usage=AnthropicUsage(900, 120, 800)
        )
        client = FakeAnthropicClient(message)
        response = AnthropicProvider(llm_settings, client=client).complete(request())
        assert response.usage.input_tokens == 900
        assert response.usage.output_tokens == 120
        assert response.usage.cached_input_tokens == 800

    @pytest.mark.parametrize(
        ("vendor", "expected"),
        [
            ("end_turn", "end_turn"),
            ("max_tokens", "max_tokens"),
            ("refusal", "refusal"),
            ("stop_sequence", "other"),
            ("tool_use", "other"),
            ("pause_turn", "other"),
            ("model_context_window_exceeded", "error"),
            ("something_new", "other"),
            (None, "other"),
        ],
    )
    def test_every_stop_reason_is_mapped(
        self, llm_settings: Settings, vendor, expected
    ):
        client = FakeAnthropicClient(anthropic_reply(stop_reason=vendor))
        response = AnthropicProvider(llm_settings, client=client).complete(request())
        assert response.stop_reason == expected

    def test_an_oversized_input_is_an_error_not_a_truncated_answer(
        self, llm_settings: Settings
    ):
        """There is no answer to truncate: the prompt never fit."""
        client = FakeAnthropicClient(
            anthropic_reply("", stop_reason="model_context_window_exceeded")
        )
        response = AnthropicProvider(llm_settings, client=client).complete(request())
        assert response.stop_reason == "error"


class TestOpenAIResponse:
    def test_text_is_read_from_the_message_content(self, llm_settings: Settings):
        client = FakeOpenAIClient(openai_reply("The switch rejects it [1]."))
        response = OpenAIProvider(llm_settings, client=client).complete(request())
        assert response.text == "The switch rejects it [1]."

    def test_null_content_becomes_an_empty_string_not_a_crash(
        self, llm_settings: Settings
    ):
        client = FakeOpenAIClient(openai_reply(None))
        response = OpenAIProvider(llm_settings, client=client).complete(request())
        assert response.text == ""

    def test_a_refusal_on_the_message_wins_over_finish_reason(
        self, llm_settings: Settings
    ):
        """OpenAI reports a refusal beside a finish_reason of "stop".

        Trusting finish_reason alone would hand the empty string to the service
        labelled as a complete answer.
        """
        client = FakeOpenAIClient(
            openai_reply(None, finish_reason="stop", refusal="I can't help with that")
        )
        response = OpenAIProvider(llm_settings, client=client).complete(request())
        assert response.stop_reason == "refusal"

    @pytest.mark.parametrize(
        ("vendor", "expected"),
        [
            ("stop", "end_turn"),
            ("length", "max_tokens"),
            ("content_filter", "refusal"),
            ("tool_calls", "other"),
            ("function_call", "other"),
            ("something_new", "other"),
            (None, "other"),
        ],
    )
    def test_every_finish_reason_is_mapped(
        self, llm_settings: Settings, vendor, expected
    ):
        client = FakeOpenAIClient(openai_reply(finish_reason=vendor))
        response = OpenAIProvider(llm_settings, client=client).complete(request())
        assert response.stop_reason == expected

    def test_usage_is_translated_from_differently_named_fields(
        self, llm_settings: Settings
    ):
        completion = openai_reply(usage=OpenAIUsage(900, 120, 800))
        client = FakeOpenAIClient(completion)
        response = OpenAIProvider(llm_settings, client=client).complete(request())
        assert response.usage.input_tokens == 900
        assert response.usage.output_tokens == 120
        assert response.usage.cached_input_tokens == 800

    def test_a_reply_with_no_choices_raises(self, llm_settings: Settings):
        """Malformed, not empty. It must not read as 'nothing to say'."""
        client = FakeOpenAIClient(OpenAICompletion([]))
        with pytest.raises(LLMResponseError, match="no choices"):
            OpenAIProvider(llm_settings, client=client).complete(request())


# --- Error translation ----------------------------------------------------


class TestErrorTranslation:
    """Both hierarchies, both directions, including the ordering traps."""

    @pytest.mark.parametrize(
        ("cls", "client_cls", "sdk"),
        [
            (AnthropicProvider, FakeAnthropicClient, "anthropic"),
            (OpenAIProvider, FakeOpenAIClient, "openai"),
        ],
    )
    def test_a_timeout_becomes_a_retryable_timeout(
        self, llm_settings: Settings, cls, client_cls, sdk
    ):
        import importlib

        module = importlib.import_module(sdk)
        exc = module.APITimeoutError(
            request=httpx2.Request("POST", "https://example.invalid/v1")
        )
        client = client_cls(raises=exc)
        with pytest.raises(LLMTimeoutError) as excinfo:
            cls(llm_settings, client=client).complete(request())
        assert excinfo.value.retryable is True

    @pytest.mark.parametrize(
        ("cls", "client_cls", "sdk"),
        [
            (AnthropicProvider, FakeAnthropicClient, "anthropic"),
            (OpenAIProvider, FakeOpenAIClient, "openai"),
        ],
    )
    def test_a_rate_limit_carries_the_advertised_cool_off(
        self, llm_settings: Settings, cls, client_cls, sdk
    ):
        import importlib

        module = importlib.import_module(sdk)
        exc = status_error(sdk, module.RateLimitError, 429, {"retry-after": "30"})
        client = client_cls(raises=exc)
        with pytest.raises(LLMRateLimitError) as excinfo:
            cls(llm_settings, client=client).complete(request())
        assert excinfo.value.retryable is True
        assert excinfo.value.retry_after_seconds == 30.0

    @pytest.mark.parametrize(
        ("cls", "client_cls", "sdk"),
        [
            (AnthropicProvider, FakeAnthropicClient, "anthropic"),
            (OpenAIProvider, FakeOpenAIClient, "openai"),
        ],
    )
    def test_an_absent_retry_after_stays_none_rather_than_zero(
        self, llm_settings: Settings, cls, client_cls, sdk
    ):
        """ "No advice given" must not read as "retry immediately"."""
        import importlib

        module = importlib.import_module(sdk)
        client = client_cls(raises=status_error(sdk, module.RateLimitError, 429))
        with pytest.raises(LLMRateLimitError) as excinfo:
            cls(llm_settings, client=client).complete(request())
        assert excinfo.value.retry_after_seconds is None

    @pytest.mark.parametrize(
        ("cls", "client_cls", "sdk"),
        [
            (AnthropicProvider, FakeAnthropicClient, "anthropic"),
            (OpenAIProvider, FakeOpenAIClient, "openai"),
        ],
    )
    def test_an_http_date_retry_after_degrades_to_none(
        self, llm_settings: Settings, cls, client_cls, sdk
    ):
        import importlib

        module = importlib.import_module(sdk)
        exc = status_error(
            sdk,
            module.RateLimitError,
            429,
            {"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"},
        )
        client = client_cls(raises=exc)
        with pytest.raises(LLMRateLimitError) as excinfo:
            cls(llm_settings, client=client).complete(request())
        assert excinfo.value.retry_after_seconds is None

    @pytest.mark.parametrize(
        ("cls", "client_cls", "sdk", "error", "code"),
        [
            (
                AnthropicProvider,
                FakeAnthropicClient,
                "anthropic",
                "AuthenticationError",
                401,
            ),  # noqa: E501
            (
                AnthropicProvider,
                FakeAnthropicClient,
                "anthropic",
                "PermissionDeniedError",
                403,
            ),  # noqa: E501
            (AnthropicProvider, FakeAnthropicClient, "anthropic", "NotFoundError", 404),
            (OpenAIProvider, FakeOpenAIClient, "openai", "AuthenticationError", 401),
            (OpenAIProvider, FakeOpenAIClient, "openai", "PermissionDeniedError", 403),
            (OpenAIProvider, FakeOpenAIClient, "openai", "NotFoundError", 404),
        ],
    )
    def test_credential_and_model_problems_are_configuration_errors(
        self, llm_settings: Settings, cls, client_cls, sdk, error, code
    ):
        """The environment is wrong, not the request. Never retryable."""
        import importlib

        module = importlib.import_module(sdk)
        client = client_cls(raises=status_error(sdk, getattr(module, error), code))
        with pytest.raises(LLMConfigurationError) as excinfo:
            cls(llm_settings, client=client).complete(request())
        assert excinfo.value.retryable is False

    @pytest.mark.parametrize(
        ("cls", "client_cls", "sdk", "code"),
        [
            (AnthropicProvider, FakeAnthropicClient, "anthropic", 500),
            (AnthropicProvider, FakeAnthropicClient, "anthropic", 503),
            (OpenAIProvider, FakeOpenAIClient, "openai", 500),
            (OpenAIProvider, FakeOpenAIClient, "openai", 503),
        ],
    )
    def test_a_server_error_is_retryable(
        self, llm_settings: Settings, cls, client_cls, sdk, code
    ):
        """The gap Stage 4's taxonomy had, and why LLMConnectionError exists."""
        import importlib

        module = importlib.import_module(sdk)
        client = client_cls(raises=status_error(sdk, module.InternalServerError, code))
        with pytest.raises(LLMConnectionError) as excinfo:
            cls(llm_settings, client=client).complete(request())
        assert excinfo.value.retryable is True

    @pytest.mark.parametrize(
        ("cls", "client_cls", "sdk"),
        [
            (AnthropicProvider, FakeAnthropicClient, "anthropic"),
            (OpenAIProvider, FakeOpenAIClient, "openai"),
        ],
    )
    def test_an_unreachable_provider_is_retryable(
        self, llm_settings: Settings, cls, client_cls, sdk
    ):
        import importlib

        module = importlib.import_module(sdk)
        exc = module.APIConnectionError(
            request=httpx2.Request("POST", "https://example.invalid/v1")
        )
        client = client_cls(raises=exc)
        with pytest.raises(LLMConnectionError) as excinfo:
            cls(llm_settings, client=client).complete(request())
        assert excinfo.value.retryable is True

    @pytest.mark.parametrize(
        ("cls", "client_cls", "sdk"),
        [
            (AnthropicProvider, FakeAnthropicClient, "anthropic"),
            (OpenAIProvider, FakeOpenAIClient, "openai"),
        ],
    )
    def test_a_timeout_is_not_coarsened_into_a_connection_error(
        self, llm_settings: Settings, cls, client_cls, sdk
    ):
        """APITimeoutError subclasses APIConnectionError in both SDKs.

        Reversing two lines in the translation table would silently coarsen the
        mapping rather than break anything, so the ordering is asserted.
        """
        import importlib

        module = importlib.import_module(sdk)
        assert issubclass(module.APITimeoutError, module.APIConnectionError)
        exc = module.APITimeoutError(
            request=httpx2.Request("POST", "https://example.invalid/v1")
        )
        client = client_cls(raises=exc)
        with pytest.raises(LLMTimeoutError):
            cls(llm_settings, client=client).complete(request())

    @pytest.mark.parametrize(
        ("cls", "client_cls", "sdk"),
        [
            (AnthropicProvider, FakeAnthropicClient, "anthropic"),
            (OpenAIProvider, FakeOpenAIClient, "openai"),
        ],
    )
    def test_a_rejected_request_is_a_provider_error(
        self, llm_settings: Settings, cls, client_cls, sdk
    ):
        import importlib

        module = importlib.import_module(sdk)
        client = client_cls(raises=status_error(sdk, module.BadRequestError, 400))
        with pytest.raises(LLMProviderError) as excinfo:
            cls(llm_settings, client=client).complete(request())
        assert excinfo.value.retryable is False

    @pytest.mark.parametrize(
        ("cls", "client_cls"),
        [(AnthropicProvider, FakeAnthropicClient), (OpenAIProvider, FakeOpenAIClient)],
    )
    def test_an_entirely_unexpected_exception_is_still_wrapped(
        self, llm_settings: Settings, cls, client_cls
    ):
        """No raw SDK or runtime exception escapes the layer."""
        client = client_cls(raises=ValueError("something nobody anticipated"))
        with pytest.raises(LLMProviderError) as excinfo:
            cls(llm_settings, client=client).complete(request())
        assert "ValueError" in str(excinfo.value)

    @pytest.mark.parametrize(
        ("cls", "client_cls"),
        [(AnthropicProvider, FakeAnthropicClient), (OpenAIProvider, FakeOpenAIClient)],
    )
    def test_the_original_cause_is_preserved(
        self, llm_settings: Settings, cls, client_cls
    ):
        original = ValueError("the real reason")
        client = client_cls(raises=original)
        with pytest.raises(LLMProviderError) as excinfo:
            cls(llm_settings, client=client).complete(request())
        assert excinfo.value.__cause__ is original

    @pytest.mark.parametrize(
        ("cls", "client_cls", "sdk"),
        [
            (AnthropicProvider, FakeAnthropicClient, "anthropic"),
            (OpenAIProvider, FakeOpenAIClient, "openai"),
        ],
    )
    def test_no_error_message_can_contain_the_api_key(
        self, llm_settings: Settings, cls, client_cls, sdk
    ):
        """A 401 message is the most likely place a key would be echoed."""
        import importlib

        module = importlib.import_module(sdk)
        settings = keyed(llm_settings, sdk)
        client = client_cls(raises=status_error(sdk, module.AuthenticationError, 401))
        with pytest.raises(LLMConfigurationError) as excinfo:
            cls(settings, client=client).complete(request())
        assert "not-a-real-key-for-tests" not in str(excinfo.value)


# --- The cost guard --------------------------------------------------------


class TestTheCostGuard:
    """Nothing else stands between an exported key and a bill."""

    def test_the_mock_is_not_a_paid_provider(self, llm_settings: Settings):
        from app.llm.factory import is_paid_provider

        assert is_paid_provider(llm_settings) is False

    @pytest.mark.parametrize("provider", ["anthropic", "openai"])
    def test_both_adapters_are_paid_providers(self, llm_settings: Settings, provider):
        from app.llm.factory import is_paid_provider

        settings = llm_settings.model_copy(update={"llm_provider": provider})
        assert is_paid_provider(settings) is True

    @pytest.mark.parametrize("provider", ["anthropic", "openai"])
    def test_the_agent_demo_refuses_a_paid_run_without_the_flag(
        self, monkeypatch, capsys, provider
    ):
        """A refusal, not a warning: demo is 7 questions, so 7 billed calls."""
        from app.agent import __main__ as agent_cli

        monkeypatch.setenv("BKA_LLM_PROVIDER", provider)
        monkeypatch.setenv("BKA_LOG_TO_FILE", "false")
        monkeypatch.setattr(agent_cli, "get_settings", Settings)
        exit_code = agent_cli.main(["demo"])
        assert exit_code == 2
        output = capsys.readouterr().out
        assert "REFUSED" in output
        assert "PAID" in output

    @pytest.mark.parametrize("provider", ["anthropic", "openai"])
    def test_the_llm_demo_refuses_a_paid_run_without_the_flag(
        self, monkeypatch, capsys, provider
    ):
        from app.llm import __main__ as llm_cli

        monkeypatch.setenv("BKA_LLM_PROVIDER", provider)
        monkeypatch.setenv("BKA_LOG_TO_FILE", "false")
        monkeypatch.setattr(llm_cli, "get_settings", Settings)
        assert llm_cli.main(["demo"]) == 2
        assert "REFUSED" in capsys.readouterr().out

    @pytest.mark.parametrize("provider", ["anthropic", "openai"])
    def test_both_clis_warn_through_one_shared_implementation(
        self, monkeypatch, capsys, provider
    ):
        """Stage 15: the guard was copy-pasted and its wording had already drifted.

        Two copies mean a correction to one can silently miss the other, so the
        warning is asserted to come from a single function both CLIs call.
        """
        from app.agent import __main__ as agent_cli
        from app.llm import __main__ as llm_cli
        from app.llm.factory import warn_if_paid

        assert agent_cli.warn_if_paid is warn_if_paid
        assert llm_cli.warn_if_paid is warn_if_paid

        settings = Settings(llm_provider=provider)
        assert warn_if_paid(settings) is True
        output = capsys.readouterr().out
        assert "PAID" in output
        assert f"BKA_LLM_PROVIDER={provider}" in output

    def test_the_shared_warning_stays_silent_for_the_mock(self, capsys):
        from app.llm.factory import warn_if_paid

        assert warn_if_paid(Settings(llm_provider="mock")) is False
        assert capsys.readouterr().out == ""

    def test_the_refusal_happens_before_the_index_or_the_client_is_built(
        self, monkeypatch, capsys
    ):
        """The guard must come first, or it has already cost time and money."""
        from app.agent import __main__ as agent_cli

        def fail(*_args, **_kwargs):
            raise AssertionError("the demo built an agent before refusing")

        monkeypatch.setenv("BKA_LLM_PROVIDER", "anthropic")
        monkeypatch.setenv("BKA_LOG_TO_FILE", "false")
        monkeypatch.setattr(agent_cli, "get_settings", Settings)
        monkeypatch.setattr(agent_cli, "get_agent", fail)
        assert agent_cli.main(["demo"]) == 2

    def test_the_mock_demo_is_never_refused(self, monkeypatch, capsys):
        """The guard must not get in the way of the free path."""
        from app.agent import __main__ as agent_cli

        monkeypatch.setenv("BKA_LLM_PROVIDER", "mock")
        monkeypatch.setenv("BKA_LOG_TO_FILE", "false")
        monkeypatch.setattr(agent_cli, "get_settings", Settings)
        called: list[bool] = []
        monkeypatch.setattr(
            agent_cli, "get_agent", lambda *_a, **_k: called.append(True) or _Stub()
        )
        agent_cli.main(["demo"])
        assert called, "the free path was blocked by the cost guard"


class _StubProvider:
    provider_id = "mock"
    model_id = "mock-deterministic-v1"


class _StubEmbedder:
    model_id = "hashing"


class _StubService:
    provider = _StubProvider()


class _StubRetriever:
    embedder = _StubEmbedder()


class _Stub:
    """Just enough agent for the free-path guard test."""

    llm_service = _StubService()
    retriever = _StubRetriever()

    def ask(self, question: str):
        from app.agent.models import (
            AgentAnswer,
            RetrievalDecision,
            RetrievalSummary,
        )
        from app.llm.models import GroundedAnswer

        return AgentAnswer(
            question=question,
            text="stub",
            sources=(),
            decision=RetrievalDecision(
                retrieve=False, reason="no_searchable_content", explanation="Stub."
            ),
            retrieval=RetrievalSummary.not_performed(),
            answer=GroundedAnswer(
                question=question,
                text="stub",
                refused=True,
                llm_called=False,
                prompt_version="1.0.0",
            ),
        )


# --- The point of building two ---------------------------------------------


class TestTheSeamIsProved:
    """The identical assertions against both adapters.

    Two vendors, two request shapes, two response shapes, two error
    hierarchies - and one ``LLMResponse`` out. This class is the evidence that
    the abstraction does something, which a single adapter could not provide.
    """

    @pytest.fixture(params=["anthropic", "openai"])
    def adapter(self, request, llm_settings: Settings):
        if request.param == "anthropic":
            client = FakeAnthropicClient(anthropic_reply("Answer [1]."))
            return AnthropicProvider(llm_settings, client=client), client
        client = FakeOpenAIClient(openai_reply("Answer [1]."))
        return OpenAIProvider(llm_settings, client=client), client

    def test_both_return_the_same_response_shape(self, adapter):
        provider, _ = adapter
        response = provider.complete(request())
        assert response.text == "Answer [1]."
        assert response.stop_reason == "end_turn"
        assert response.is_complete is True
        assert response.usage.total_tokens == 165
        assert response.provider_id in {"anthropic", "openai"}
        assert response.model_id

    def test_both_make_exactly_one_call_per_request(self, adapter):
        provider, client = adapter
        provider.complete(request())
        assert len(client.recorder.calls) == 1

    def test_both_send_the_question_and_the_system_prompt(self, adapter):
        provider, client = adapter
        provider.complete(request("Question: what handles card auth?"))
        sent = str(client.recorder.last)
        assert "what handles card auth?" in sent
        assert "Frozen system instructions." in sent

    def test_both_work_through_the_service_unchanged(
        self, adapter, llm_settings: Settings, retrieval
    ):
        """The layer above cannot tell which vendor answered.

        This is the claim Stage 4 made and could not demonstrate.
        """
        from app.llm.service import LLMService

        provider, _ = adapter
        answer = LLMService(provider, llm_settings).answer(
            "What component handles card authentication?", retrieval
        )
        assert answer.is_grounded
        assert answer.text == "Answer [1]."
        assert answer.sources

    def test_both_refuse_without_a_call_when_there_is_no_evidence(
        self, adapter, llm_settings: Settings, empty_retrieval
    ):
        """The no-evidence guard holds for a paid provider too - which is the
        version of it that actually costs money to get wrong."""
        from app.llm.service import LLMService

        provider, client = adapter
        answer = LLMService(provider, llm_settings).answer(
            "What is the capital of France?", empty_retrieval
        )
        assert answer.refused is True
        assert client.recorder.calls == []

    def test_both_work_through_the_agent_unchanged(
        self, adapter, llm_settings: Settings, retriever
    ):
        from app.agent.agent import KnowledgeAgent
        from app.llm.service import LLMService

        provider, _ = adapter
        agent = KnowledgeAgent(
            retriever, LLMService(provider, llm_settings), llm_settings
        )
        answer = agent.ask("What component handles card authentication?")
        assert answer.is_grounded
        assert answer.text == "Answer [1]."


# --- The shared Retry-After reader (Stage 15) ------------------------------


class TestTheSharedRetryAfterReader:
    """Reading a Retry-After header is HTTP, not vendor-specific.

    It was duplicated verbatim in both adapters. One copy, tested once.
    """

    def test_a_numeric_header_is_read_as_seconds(self):
        from app.llm.base import read_retry_after

        exc = _HeaderBearingError({"retry-after": "30"})
        assert read_retry_after(exc) == 30.0

    def test_no_response_means_no_advice(self):
        from app.llm.base import read_retry_after

        assert read_retry_after(Exception("plain")) is None

    def test_a_missing_header_means_no_advice(self):
        from app.llm.base import read_retry_after

        assert read_retry_after(_HeaderBearingError({})) is None

    def test_an_http_date_is_not_guessed_at(self):
        """None means "the provider did not say", which is the safe reading."""
        from app.llm.base import read_retry_after

        exc = _HeaderBearingError({"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"})
        assert read_retry_after(exc) is None

    @pytest.mark.parametrize(
        "module_name",
        ["app.llm.anthropic_provider", "app.llm.openai_provider"],
    )
    def test_both_adapters_use_the_shared_reader(self, module_name):
        import importlib

        from app.llm.base import read_retry_after

        module = importlib.import_module(module_name)
        assert module.read_retry_after is read_retry_after


class _HeaderBearingError(Exception):
    """An SDK error shaped like the ones both vendors raise."""

    def __init__(self, headers: dict[str, str]) -> None:
        super().__init__("rate limited")
        self.response = type("_Response", (), {"headers": headers})()
