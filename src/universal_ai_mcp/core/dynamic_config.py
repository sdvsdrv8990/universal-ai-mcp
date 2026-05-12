"""Dynamic configuration manager — AI selects workflow profiles to activate modules.

Workflow:
  1. AI (or user) calls analyze_task(task_description)  →  picks best WorkflowProfile
  2. activate_profile(profile_name) enables/disables modules in the ToolRegistry
  3. Feature flag overrides from the profile are applied to runtime settings
  4. All changes are reversible by calling activate_profile with a different name

The YAML file (config/workflow_profiles.yaml) is the single source of truth for
profile definitions and can be hot-reloaded without restarting the server.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
import yaml

from universal_ai_mcp.entities.workflow_profile_entity import (
    ActiveProfileState,
    WorkflowProfile,
)

if TYPE_CHECKING:
    from universal_ai_mcp.core.registry import ToolRegistry
    from universal_ai_mcp.modules.llm.router import LLMRouter

log = structlog.get_logger(__name__)

_PROFILES_YAML = Path(__file__).parent.parent.parent.parent / "config" / "workflow_profiles.yaml"

_CLASSIFY_SYSTEM_PROMPT = """You are a task classifier for an AI development assistant.
Given a task description, select the single most appropriate workflow profile.

Available profiles and their descriptions will be provided.

Rules:
1. Return ONLY valid JSON: {"profile": "<profile_name>", "confidence": <0.0-1.0>, "reason": "<one sentence>"}
2. "confidence" reflects how clearly the task matches the profile.
3. Use the default profile when unsure.
"""


class DynamicConfigManager:
    """Manages workflow profile selection and module activation at runtime."""

    def __init__(self, profiles_yaml: Path = _PROFILES_YAML) -> None:
        self._yaml_path = profiles_yaml
        self._profiles: dict[str, WorkflowProfile] = {}
        self._default_profile_name: str = "feature_build"
        self._classification_tier: str = "fast"
        self._active_state: ActiveProfileState | None = None
        self._load_profiles()

    # ------------------------------------------------------------------
    # Profile loading
    # ------------------------------------------------------------------

    def _load_profiles(self) -> None:
        """Load (or reload) profile definitions from YAML."""
        if not self._yaml_path.exists():
            log.warning("workflow_profiles_yaml_missing", path=str(self._yaml_path))
            return

        with self._yaml_path.open() as fh:
            raw = yaml.safe_load(fh)

        self._default_profile_name = raw.get("default_profile", "feature_build")
        self._classification_tier = raw.get("classification_tier", "fast")

        profiles_raw: dict[str, Any] = raw.get("profiles", {})
        self._profiles = {}
        for name, data in profiles_raw.items():
            data["name"] = name
            self._profiles[name] = WorkflowProfile.model_validate(data)

        log.info(
            "workflow_profiles_loaded",
            count=len(self._profiles),
            default=self._default_profile_name,
        )

    def reload_profiles(self) -> int:
        """Hot-reload profiles from disk. Returns the number of profiles loaded."""
        self._load_profiles()
        return len(self._profiles)

    # ------------------------------------------------------------------
    # Profile access
    # ------------------------------------------------------------------

    def list_profiles(self) -> list[WorkflowProfile]:
        return list(self._profiles.values())

    def get_profile(self, name: str) -> WorkflowProfile | None:
        return self._profiles.get(name)

    def get_default_profile(self) -> WorkflowProfile:
        return self._profiles.get(self._default_profile_name) or next(
            iter(self._profiles.values())
        )

    def get_active_state(self) -> ActiveProfileState | None:
        return self._active_state

    # ------------------------------------------------------------------
    # AI-driven classification
    # ------------------------------------------------------------------

    async def analyze_task(
        self,
        task_description: str,
        router: LLMRouter,
    ) -> tuple[WorkflowProfile, float]:
        """Use LLM to classify the task and return the best profile + confidence."""
        from universal_ai_mcp.entities.provider_entity import LLMMessage, LLMRequest

        if not self._profiles:
            return self.get_default_profile(), 0.0

        profiles_summary = "\n".join(
            f"  {name}: {p.description}  [modules: {', '.join(p.required_modules)}]"
            for name, p in self._profiles.items()
        )

        user_msg = (
            f"Task: {task_description}\n\n"
            f"Available profiles:\n{profiles_summary}\n\n"
            f"Default profile: {self._default_profile_name}\n\n"
            f"Select the best profile."
        )

        request = LLMRequest(
            model="auto",
            messages=[LLMMessage(role="user", content=user_msg)],
            system_prompt=_CLASSIFY_SYSTEM_PROMPT,
            max_tokens=256,
            temperature=0.0,
        )

        try:
            response = await router.complete(request, tier=self._classification_tier)
            data = json.loads(response.content)
            profile_name: str = data.get("profile", self._default_profile_name)
            confidence: float = float(data.get("confidence", 0.5))
            reason: str = data.get("reason", "")

            profile = self._profiles.get(profile_name, self.get_default_profile())
            log.info(
                "task_classified",
                profile=profile.name,
                confidence=confidence,
                reason=reason,
            )
            return profile, confidence

        except Exception as exc:
            log.warning("task_classification_failed", error=str(exc))
            return self.get_default_profile(), 0.0

    # ------------------------------------------------------------------
    # Profile activation
    # ------------------------------------------------------------------

    def activate_profile(
        self,
        profile_name: str,
        registry: ToolRegistry,
        task_description: str = "",
        confidence: float = 1.0,
    ) -> ActiveProfileState:
        """Activate a profile: enable/disable modules in the registry accordingly."""
        profile = self._profiles.get(profile_name)
        if profile is None:
            log.warning("unknown_profile_falling_back", profile=profile_name)
            profile = self.get_default_profile()

        all_registered = {m.name: m for m in registry.list_modules()}
        activated: list[str] = []
        deactivated: list[str] = []

        # Determine which modules should be active
        desired_active = set(profile.required_modules) | set(
            m for m in profile.optional_modules if m in all_registered
        )

        for mod_name, module in all_registered.items():
            should_be_active = mod_name in desired_active
            if module.enabled != should_be_active:
                module.enabled = should_be_active
                if should_be_active:
                    activated.append(mod_name)
                else:
                    deactivated.append(mod_name)

        # Build merged feature flags
        feature_flags = dict(profile.feature_overrides)

        self._active_state = ActiveProfileState(
            profile=profile,
            activated_modules=activated,
            deactivated_modules=deactivated,
            feature_flags=feature_flags,
            task_description=task_description,
            classification_confidence=confidence,
        )

        log.info(
            "profile_activated",
            profile=profile.name,
            activated=activated,
            deactivated=deactivated,
            features=feature_flags,
        )
        return self._active_state

    def get_effective_feature_flag(self, flag_name: str, default: Any = None) -> Any:
        """Return the current profile's override for a feature flag, or the default."""
        if self._active_state:
            return self._active_state.feature_flags.get(flag_name, default)
        return default

    def is_module_active(self, module_name: str, registry: ToolRegistry) -> bool:
        """Return True if the module is registered and currently enabled."""
        module = registry.get_module(module_name)
        return module is not None and module.enabled


_manager: DynamicConfigManager | None = None


def get_dynamic_config() -> DynamicConfigManager:
    global _manager
    if _manager is None:
        _manager = DynamicConfigManager()
    return _manager
