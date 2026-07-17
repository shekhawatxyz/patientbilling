"""Deterministic offline provider for local development and CI."""

import json

from zango.ai.providers.base import (
    BaseLLMProvider,
    LLMResponse,
    LLMStreamChunk,
    LLMToolCall,
    LLMUsage,
)
from zango.ai.providers.registry import register_provider


MODEL = "local-deterministic-v1"


@register_provider("local_fake", "Local Fake (Offline)", icon="openai.svg")
class LocalFakeProvider(BaseLLMProvider):
    """Return tool calls so the normal AgentClient loop remains under test."""

    supported_models = [{
        "id": MODEL,
        "name": "Local Deterministic Provider",
        "context_window": 32768,
        "max_output_tokens": 4096,
        "input_cost_per_mtok": 0,
        "output_cost_per_mtok": 0,
        "supports_tools": True,
        "supports_vision": False,
        "supports_streaming": True,
    }]
    config_fields = []

    def __init__(self, config):
        super().__init__(config)
        self._calls = 0

    @staticmethod
    def _agent_kind(system):
        prompt = (system or "").lower()
        if "appeal" in prompt:
            return "appeal-drafter"
        if "denial" in prompt:
            return "denial-analyzer"
        return "claim-validator"

    @staticmethod
    def _denial_root_cause(messages):
        for message in messages:
            content = getattr(message, "content", None)
            if isinstance(content, list):
                content = " ".join(
                    block.get("text", "")
                    for block in content
                    if isinstance(block, dict)
                )
            if not isinstance(content, str) or "ai_denial_analysis" not in content:
                continue
            try:
                payload = json.loads(content)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                findings = payload.get("ai_denial_analysis")
                if isinstance(findings, dict) and findings.get("root_cause"):
                    return findings["root_cause"]
        return None

    def complete(self, messages, model, tools=None, **kwargs):
        self._calls += 1
        available = {item.name for item in (tools or [])}
        called = []
        for message in messages:
            called.extend(
                call["function"]["name"] for call in (message.tool_calls or [])
            )
            if isinstance(message.content, list):
                called.extend(
                    block["name"]
                    for block in message.content
                    if block.get("type") == "tool_use"
                )
        kind = self._agent_kind(kwargs.get("system"))

        if "update_claim_ai_result" in called:
            return LLMResponse(
                content="Completed.",
                tool_calls=[],
                stop_reason="end_turn",
                usage=LLMUsage(input_tokens=0, output_tokens=0),
                model=model or MODEL,
                raw_response=None,
                latency_ms=0,
            )

        if "get_claim_details" not in called and "get_claim_details" in available:
            name, value = "get_claim_details", {}
        elif kind in {"claim-validator", "appeal-drafter"} and "get_patient_insurance" not in called and "get_patient_insurance" in available:
            name, value = "get_patient_insurance", {}
        else:
            name = "update_claim_ai_result"
            if kind == "claim-validator":
                value = json.dumps({"valid": True, "issues": [], "code_suggestions": [], "completeness_score": 100})
            elif kind == "denial-analyzer":
                value = json.dumps({"root_cause": "Documentation review required", "category": "other", "corrective_actions": ["Review the denial documentation."]})
            else:
                root_cause = self._denial_root_cause(messages)
                finding = (
                    f" We specifically address the denial finding: {root_cause}."
                    if root_cause
                    else ""
                )
                value = f"Dear Insurer,\n\nWe respectfully appeal the denial of this claim.{finding} The claim details support reconsideration.\n\nSincerely,\nBilling Department"

        return LLMResponse(
            content="",
            tool_calls=[LLMToolCall(
                id=f"local-fake-{self._calls}",
                name=name,
                input={"value": value} if name == "update_claim_ai_result" else {},
            )],
            stop_reason="tool_use",
            usage=LLMUsage(input_tokens=0, output_tokens=0),
            model=model or MODEL,
            raw_response=None,
            latency_ms=0,
        )

    def stream(self, messages, model, tools=None, **kwargs):
        response = self.complete(messages, model, tools=tools, **kwargs)
        yield LLMStreamChunk(is_final=True, usage=response.usage, stop_reason=response.stop_reason)

    def validate_config(self):
        return True, None

    def get_models(self):
        return self.supported_models
