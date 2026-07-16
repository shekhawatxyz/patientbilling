"""
Google Gemini provider via OpenAI-compatible endpoint.
Registers as provider_slug "gemini" in the Zango App Panel.
"""

import time

from zango.ai.exceptions import LLMAPIError, LLMTimeoutError, RateLimitExceeded
from zango.ai.providers.base import (
    BaseLLMProvider,
    LLMResponse,
    LLMStreamChunk,
    LLMToolCall,
    LLMUsage,
)
from zango.ai.providers.registry import register_provider


@register_provider("gemini", "Google Gemini", icon="openai.svg")
class GeminiProvider(BaseLLMProvider):
    supported_models = [
        {
            "id": "gemini-2.0-flash-lite",
            "name": "Gemini 2.0 Flash Lite",
            "context_window": 1048576,
            "max_output_tokens": 8192,
            "input_cost_per_mtok": 0.075,
            "output_cost_per_mtok": 0.30,
            "supports_tools": True,
            "supports_vision": True,
            "supports_streaming": True,
        },
        {
            "id": "gemini-2.0-flash",
            "name": "Gemini 2.0 Flash",
            "context_window": 1048576,
            "max_output_tokens": 8192,
            "input_cost_per_mtok": 0.10,
            "output_cost_per_mtok": 0.40,
            "supports_tools": True,
            "supports_vision": True,
            "supports_streaming": True,
        },
        {
            "id": "gemini-1.5-flash",
            "name": "Gemini 1.5 Flash",
            "context_window": 1048576,
            "max_output_tokens": 8192,
            "input_cost_per_mtok": 0.075,
            "output_cost_per_mtok": 0.30,
            "supports_tools": True,
            "supports_vision": True,
            "supports_streaming": True,
        },
        {
            "id": "gemini-1.5-pro",
            "name": "Gemini 1.5 Pro",
            "context_window": 2097152,
            "max_output_tokens": 8192,
            "input_cost_per_mtok": 1.25,
            "output_cost_per_mtok": 5.00,
            "supports_tools": True,
            "supports_vision": True,
            "supports_streaming": True,
        },
    ]

    config_fields = [
        {
            "name": "api_key",
            "type": "secret",
            "required": True,
            "label": "Gemini API Key",
            "help_text": "From https://aistudio.google.com/app/apikey",
        },
        {
            "name": "default_model",
            "type": "select",
            "required": True,
            "label": "Default Model",
            "options_from": "supported_models",
        },
    ]

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

    def __init__(self, config):
        super().__init__(config)
        import openai
        self._openai = openai
        self._client = openai.OpenAI(
            api_key=config["api_key"],
            base_url=self.BASE_URL,
        )

    def _convert_messages(self, messages, system=None):
        result = []
        if system:
            result.append({"role": "system", "content": system})
        for msg in messages:
            content = getattr(msg, "build_content_for_openai", lambda: msg.content)()
            d = {"role": msg.role, "content": content}
            if getattr(msg, "tool_calls", None):
                d["tool_calls"] = msg.tool_calls
            if getattr(msg, "tool_call_id", None):
                d["tool_call_id"] = msg.tool_call_id
            result.append(d)
        return result

    def _map_stop_reason(self, finish_reason):
        return {
            "stop": "end_turn",
            "tool_calls": "tool_use",
            "length": "max_tokens",
        }.get(finish_reason or "stop", finish_reason or "end_turn")

    def format_tools_for_api(self, tools):
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in tools
        ]

    def complete(self, messages, model, tools=None, temperature=1.0, max_tokens=4096,
                 system=None, stop_sequences=None, **kwargs):
        api_kwargs = {
            "model": model,
            "messages": self._convert_messages(messages, system=system),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            api_kwargs["tools"] = self.format_tools_for_api(tools)

        start = time.monotonic()
        try:
            response = self._client.chat.completions.create(**api_kwargs)
        except self._openai.RateLimitError as e:
            raise RateLimitExceeded(str(e)) from e
        except self._openai.APITimeoutError as e:
            raise LLMTimeoutError(str(e)) from e
        except self._openai.APIError as e:
            raise LLMAPIError(str(e), status_code=getattr(e, "status_code", None), original_error=e) from e
        latency_ms = int((time.monotonic() - start) * 1000)

        choice = response.choices[0]
        tool_calls = []
        if choice.message.tool_calls:
            import json
            for tc in choice.message.tool_calls:
                tool_calls.append(LLMToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    input=json.loads(tc.function.arguments),
                ))

        return LLMResponse(
            content=choice.message.content or "",
            tool_calls=tool_calls,
            stop_reason=self._map_stop_reason(choice.finish_reason),
            usage=LLMUsage(
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
            ),
            model=response.model,
            raw_response=response,
            latency_ms=latency_ms,
        )

    def stream(self, messages, model, tools=None, temperature=1.0, max_tokens=4096,
               system=None, stop_sequences=None, **kwargs):
        api_kwargs = {
            "model": model,
            "messages": self._convert_messages(messages, system=system),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            api_kwargs["tools"] = self.format_tools_for_api(tools)

        try:
            for chunk in self._client.chat.completions.create(**api_kwargs):
                if not chunk.choices:
                    if getattr(chunk, "usage", None):
                        yield LLMStreamChunk(
                            is_final=True,
                            usage=LLMUsage(
                                input_tokens=chunk.usage.prompt_tokens,
                                output_tokens=chunk.usage.completion_tokens,
                            ),
                        )
                    continue
                delta = chunk.choices[0].delta
                finish_reason = chunk.choices[0].finish_reason
                if delta.content:
                    yield LLMStreamChunk(delta_text=delta.content)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        yield LLMStreamChunk(delta_tool_call={
                            "index": tc.index, "id": tc.id,
                            "name": getattr(tc.function, "name", None),
                            "arguments": getattr(tc.function, "arguments", None),
                        })
                if finish_reason:
                    yield LLMStreamChunk(is_final=True, stop_reason=self._map_stop_reason(finish_reason))
        except self._openai.RateLimitError as e:
            raise RateLimitExceeded(str(e)) from e
        except self._openai.APITimeoutError as e:
            raise LLMTimeoutError(str(e)) from e
        except self._openai.APIError as e:
            raise LLMAPIError(str(e), status_code=getattr(e, "status_code", None), original_error=e) from e

    def validate_config(self):
        try:
            self._client.chat.completions.create(
                model=self.config.get("default_model", "gemini-2.0-flash"),
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=1,
            )
            return (True, None)
        except Exception as e:
            return (False, str(e))

    def get_models(self):
        return self.supported_models
