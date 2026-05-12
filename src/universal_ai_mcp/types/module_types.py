"""Type definitions for the module system."""

from enum import Enum
from typing import Literal

ComplexityLevel = Literal["simple", "medium", "complex"]


class ModuleCategory(str, Enum):
    PLANNING = "planning"
    CONTEXT = "context"
    LLM = "llm"
    PROJECT = "project"
    SOLUTIONS = "solutions"
    WORKFLOW = "workflow"
    CONFIG = "config"


class TaskCategory(str, Enum):
    """Maps to workflow profile names defined in config/workflow_profiles.yaml."""
    QUICK_QUESTION = "quick_question"
    CODE_REVIEW = "code_review"
    DEBUG = "debug"
    FEATURE_BUILD = "feature_build"
    RESEARCH = "research"
    REFACTOR = "refactor"
    DEVOPS = "devops"
