"""Privacy and egress (PRV-1 to PRV-4): the spine every extension layer sends through.

Import paths for the other tracks (everything below is also importable from this package):

    from understudy_engine.privacy import egress                       # egress.send(purpose, payload)
    from understudy_engine.privacy.payload import SafePayload, Vocab, register_payload, register_vocabulary
    from understudy_engine.privacy.bucket import Count, Attendees, TimeOfDay, DurationMin, Hours, Ratio, Numbers, register_feature
    from understudy_engine.privacy.purposes import CalendarSuggestionWording, GitHabitWording, BriefingCardWording, DigestMeta
    from understudy_engine.privacy.testing import CapturingPort, canary_flow
    from understudy_engine.privacy.canary import plant, assert_no_canaries

Off by default behind ``UNDERSTUDY_X_PRIVACY`` / ``UNDERSTUDY_X`` for the HTTP routes; the library itself is plain code.
"""
from . import bucket, flags, ledger, patterns, payload, purposes  # noqa: F401  (purposes registers the built-in ones)
from .payload import (  # noqa: F401
    Bucket, SafePayload, UnsafeFieldError, Vocab, get_purpose, register_payload, register_vocabulary,
)
