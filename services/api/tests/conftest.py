"""Shared test fixtures and environment isolation."""

import os

import pytest

os.environ["DATABASE_URL"] = ""
os.environ["DB_URL"] = ""


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the opt-in flag that enables integration tests."""
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests that call real external APIs",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Skip integration-marked tests unless --run-integration is passed."""
    if config.getoption("--run-integration"):
        return
    skip_integration = pytest.mark.skip(
        reason="integration tests require --run-integration"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
