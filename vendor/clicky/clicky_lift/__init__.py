# Adapted from rickkdev/clicky (fork of farzaa/clicky) (MIT) hermes-clicky-plugin (package layout and naming only)
# Copyright (c) 2026 Farza. Full licence text: vendor/clicky/LICENSE.
"""Understudy's reshaped lifts from Clicky's Hermes plugin (CLK-1). Standard library only.

* `lease`: time-boxed, revocable permission leases for child agents.
* `postcheck`: declarative postconditions checked after an agent step.

See vendor/clicky/README.md for how the agent-runtime and safety tracks adopt them.
"""
from .lease import Lease, LeaseBook, LeaseDecision, LeaseError, LeaseLimits, StopReason
from .postcheck import (
                        Check,
                        Condition,
                        Observation,
                        PostResult,
                        absent,
                        changed,
                        contains,
                        equals,
                        in_range,
                        matches,
                        present,
                        run_step,
                        verify,
)

__all__ = ["Check", "Condition", "Lease", "LeaseBook", "LeaseDecision", "LeaseError", "LeaseLimits", "Observation",
           "PostResult", "StopReason", "absent", "changed", "contains", "equals", "in_range", "matches", "present",
           "run_step", "verify"]
