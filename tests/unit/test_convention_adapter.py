"""Unit tests for ConventionAdapter naming transformations."""

from __future__ import annotations

import pytest

from universal_ai_mcp.entities.project_entity import NamingConventions
from universal_ai_mcp.modules.project_detection.convention_adapter import ConventionAdapter


@pytest.fixture
def adapter() -> ConventionAdapter:
    return ConventionAdapter()


def snake_conventions() -> NamingConventions:
    return NamingConventions(file_case="snake_case", test_prefix="test_")


def kebab_conventions() -> NamingConventions:
    return NamingConventions(file_case="kebab-case", test_prefix="")


def pascal_conventions() -> NamingConventions:
    return NamingConventions(file_case="PascalCase", test_prefix="")


def test_adapt_camel_to_snake(adapter: ConventionAdapter) -> None:
    result = adapter.adapt_filename("userService", snake_conventions())
    assert result == "user_service"


def test_adapt_pascal_to_snake(adapter: ConventionAdapter) -> None:
    result = adapter.adapt_filename("UserService", snake_conventions())
    assert result == "user_service"


def test_adapt_to_kebab(adapter: ConventionAdapter) -> None:
    result = adapter.adapt_filename("UserService", kebab_conventions())
    assert result == "user-service"


def test_adapt_test_filename_snake(adapter: ConventionAdapter) -> None:
    result = adapter.adapt_test_filename("userService", snake_conventions())
    assert result == "test_user_service"


def test_adapt_directory(adapter: ConventionAdapter) -> None:
    result = adapter.adapt_directory("src/UserModule/AuthService", snake_conventions())
    assert result == "src/user_module/auth_service"
