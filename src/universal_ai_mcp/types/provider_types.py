"""Type definitions for LLM provider routing."""

from enum import Enum
from typing import Literal

ModelTier = Literal["heavy", "balanced", "fast"]


class RoutingStrategy(str, Enum):
    PRIORITY = "priority"       # Use first enabled provider
    COST_OPTIMIZED = "cost"     # Minimize token cost
    QUALITY_OPTIMIZED = "quality"  # Maximize response quality
    ROUND_ROBIN = "round_robin" # Distribute load evenly
    TASK_BASED = "task"         # Route by task type (planning vs. execution)
