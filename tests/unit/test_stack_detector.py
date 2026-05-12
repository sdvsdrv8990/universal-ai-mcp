"""Unit tests for StackDetector file-based detection logic."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from universal_ai_mcp.entities.project_entity import StackLanguage
from universal_ai_mcp.modules.project_detection.stack_detector import StackDetector


@pytest.fixture
def detector() -> StackDetector:
    return StackDetector()


@pytest.mark.asyncio
async def test_detect_python_project(tmp_path: Path, detector: StackDetector) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='myapp'\n[project.dependencies]\ndeps=['fastapi']")
    (tmp_path / "uv.lock").write_text("")

    ctx = await detector.detect(tmp_path)

    assert ctx.stack.primary_language == StackLanguage.PYTHON
    assert ctx.stack.package_manager == "uv"
    assert ctx.stack.confidence > 0.9


@pytest.mark.asyncio
async def test_detect_typescript_project(tmp_path: Path, detector: StackDetector) -> None:
    pkg = {"dependencies": {"next": "14.0.0", "react": "18.0.0"}, "devDependencies": {}}
    (tmp_path / "package.json").write_text(json.dumps(pkg))
    (tmp_path / "tsconfig.json").write_text("{}")
    (tmp_path / "bun.lockb").write_text("")

    ctx = await detector.detect(tmp_path)

    assert ctx.stack.primary_language == StackLanguage.TYPESCRIPT
    assert ctx.stack.package_manager == "bun"


@pytest.mark.asyncio
async def test_detect_unknown_project(tmp_path: Path, detector: StackDetector) -> None:
    ctx = await detector.detect(tmp_path)
    assert ctx.stack.primary_language == StackLanguage.UNKNOWN
    assert ctx.stack.confidence == 0.0
