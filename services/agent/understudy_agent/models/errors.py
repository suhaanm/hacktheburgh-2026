"""Errors raised by model providers. Callers treat all of these as a failed step, never as success."""
from __future__ import annotations


class ProviderError(RuntimeError):
    """The provider call failed (network, quota, bad request, incomplete response)."""


class ModelRefusal(ProviderError):
    """The model refused to answer. Surface as a failed step; do not retry with the same prompt."""


class SchemaViolation(ProviderError):
    """The model output did not match the requested JSON schema."""


class ConfigError(RuntimeError):
    """Required configuration (model ids from env, API key) is missing. The message says how to fix it."""
