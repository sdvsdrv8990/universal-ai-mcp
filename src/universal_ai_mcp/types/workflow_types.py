"""Type definitions for the GSD-inspired workflow engine."""

from enum import Enum


class WorkflowPhase(str, Enum):
    """Maps to GSD phases: New → Discuss → Plan → Execute → Verify → Ship."""

    INITIALIZE = "initialize"   # gsd-new-project equivalent
    DISCUSS = "discuss"         # Clarifying questions, decisions capture
    PLAN = "plan"               # Research + plan + verify
    EXECUTE = "execute"         # Parallel wave execution
    VERIFY = "verify"           # Acceptance testing, gap diagnosis
    SHIP = "ship"               # PR creation, milestone archive
