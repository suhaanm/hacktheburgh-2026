"""Context engineering for every model-facing path (REQ-8). Small, typed, deterministic. No model calls, no network.

    ContextPacket, Section, Item, Trust, Keep   typed sections with trust, source, freshness, priority, budget; cache-ordered assembly
    Assembled, Manifest                         the prompt and its metadata-only manifest (names, token counts, hashes, never content)
    WorkingMemory, StepRecord, TaskState        long-run state kept by code: task state, last K steps, rolling summary
    FrameRetention, FramePlan                   screenshot retention: the latest frame, at most one small previous thumbnail
    retrieve, lines_from_doc                    keyed retrieval from the worker's memory file (never the whole file)
    MAX_AGE_S, status_of                        the shared freshness table
    estimate_tokens, estimate_image_tokens      the deterministic estimator

See docs/CONTEXT_ENGINEERING.md for the audit, the rules and the migration note per owner. This package imports nothing from the
model clients, the providers, the egress guard or the network; the privacy static guard checks that.
"""
from .adapters import computer_use_text, manifest_of_parts, split_tier2_state, tier2_messages
from .frames import Frame, FramePlan, FrameRetention
from .freshness import MAX_AGE_S, Status, age_s, is_fresh, status_of
from .manifest import Manifest, SectionStat, assert_metadata_only
from .packet import (AUDIENCES, REQUIRED_NAMES, Assembled, ContextPacket, Item, Keep, PacketError, Section, Trust, TrustViolation,
                     split_items)
from .retrieval import MemoryLine, Retrieval, lines_from_doc, retrieve
from .tokens import estimate_error, estimate_image_tokens, estimate_tokens
from .working import Outcome, PageState, StepRecord, TaskState, TypedIdError, WorkingMemory, code_of

__all__ = [
    "AUDIENCES", "Assembled", "ContextPacket", "Frame", "FramePlan", "FrameRetention", "Item", "Keep", "MAX_AGE_S", "Manifest",
    "MemoryLine", "Outcome", "PacketError", "PageState", "REQUIRED_NAMES", "Retrieval", "Section", "SectionStat", "Status",
    "StepRecord", "TaskState", "Trust", "TrustViolation", "TypedIdError", "WorkingMemory", "age_s", "assert_metadata_only",
    "code_of", "computer_use_text", "estimate_error", "estimate_image_tokens", "estimate_tokens", "is_fresh", "lines_from_doc",
    "manifest_of_parts", "retrieve", "split_items", "split_tier2_state", "status_of", "tier2_messages",
]
