"""Project detection module — auto-detect stack, conventions, and adapt proposals."""

from universal_ai_mcp.modules.project_detection.convention_adapter import ConventionAdapter
from universal_ai_mcp.modules.project_detection.stack_advisor import StackAdvisor
from universal_ai_mcp.modules.project_detection.stack_detector import StackDetector

__all__ = ["StackDetector", "StackAdvisor", "ConventionAdapter"]
