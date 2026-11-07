"""Model provider port and providers. `get_model_port()` is the single entry point for agent code.

REQ-5 phase C adds a flag-gated Gemini provider, role routing by code (`routing.ModelRouter`), a cost and latency meter, and
`models_status()`. None of it is imported on the default path.
"""
from .boot import BootReport, boot_check, gemini_boot_check
from .config import GeminiModelIds, ModelIds, gemini_flag_enabled, mock_enabled
from .errors import ConfigError, ModelRefusal, ProviderError, SchemaViolation
from .factory import get_model_port, reset_model_port
from .port import Action, Done, ModelPort, SafetyStop

__all__ = [
    "Action", "Done", "ModelPort", "SafetyStop",
    "get_model_port", "reset_model_port", "boot_check", "gemini_boot_check", "BootReport", "ModelIds", "GeminiModelIds",
    "mock_enabled", "gemini_flag_enabled",
    "ConfigError", "ModelRefusal", "ProviderError", "SchemaViolation",
]
