"""Convention adapter — translates server-side suggestions to match project conventions.

When the server proposes file names, directory paths, or code structures,
this adapter rewrites them to conform to the detected project conventions.
"""

from __future__ import annotations

import re

from universal_ai_mcp.entities.project_entity import NamingConventions


class ConventionAdapter:
    """Rewrites names and paths to match project-specific naming conventions."""

    def adapt_filename(self, name: str, conventions: NamingConventions) -> str:
        base = self._to_snake_case(name)
        if conventions.file_case == "kebab-case":
            return base.replace("_", "-")
        if conventions.file_case == "camelCase":
            return self._to_camel_case(base)
        if conventions.file_case == "PascalCase":
            return self._to_pascal_case(base)
        return base  # snake_case default

    def adapt_test_filename(self, name: str, conventions: NamingConventions) -> str:
        adapted = self.adapt_filename(name, conventions)
        prefix = conventions.test_prefix
        return f"{prefix}{adapted}" if prefix else f"{adapted}.spec"

    def adapt_directory(self, path: str, conventions: NamingConventions) -> str:
        parts = path.strip("/").split("/")
        adapted_parts = [self.adapt_filename(p, conventions) for p in parts]
        return "/".join(adapted_parts)

    def _to_snake_case(self, text: str) -> str:
        text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", text)
        text = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", text)
        return text.replace("-", "_").lower()

    def _to_camel_case(self, snake: str) -> str:
        parts = snake.split("_")
        return parts[0] + "".join(p.capitalize() for p in parts[1:])

    def _to_pascal_case(self, snake: str) -> str:
        return "".join(p.capitalize() for p in snake.split("_"))
