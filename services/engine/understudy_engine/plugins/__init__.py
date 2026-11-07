"""Source plugin framework (PLG-1) and adapters (PLG-2). Off the P0 path: nothing here is imported unless a flagged layer
asks for it (``UNDERSTUDY_X`` or ``UNDERSTUDY_X_CALENDAR`` / ``_GIT``).

    from understudy_engine.plugins import Source, RawItem, load_source, register_manifest, register_schema

Raw items hold raw content in memory only; see ``base.py`` for the rules. ``python -m understudy_engine.plugins validate``
checks the bundled manifests.
"""
from .base import RawItem, Source, SourceError
from .loader import PluginDisabled, discover, is_enabled, load_source, load_source_class, register_manifest, validate_paths
from .manifest import ManifestError, PluginManifest, load_manifest
from .schemas import FieldSpec, ItemSchema, check_item, get_schema, register_schema, schema_ids, strip_sensitive

__all__ = [
    "FieldSpec", "ItemSchema", "ManifestError", "PluginDisabled", "PluginManifest", "RawItem", "Source", "SourceError",
    "check_item", "discover", "get_schema", "is_enabled", "load_manifest", "load_source", "load_source_class",
    "register_manifest", "register_schema", "schema_ids", "strip_sensitive", "validate_paths",
]
