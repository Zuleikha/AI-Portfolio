"""
Shared pytest configuration, fixtures, and environment setup.

os.environ assignments at module level run before any src.* modules are
imported, ensuring pydantic-settings can validate required API keys even in
CI environments where a .env file may not exist.
"""

import os

import pytest

for _key, _val in [
    ("ANTHROPIC_API_KEY", "sk-ant-test-placeholder-0000000000000000000000000000"),
    ("PINECONE_API_KEY", "test-pinecone-placeholder-000000000000000000000000000"),
    ("COHERE_API_KEY", "test-cohere-placeholder"),
]:
    os.environ.setdefault(_key, _val)


@pytest.fixture(autouse=True)
def reset_metrics():
    """Reset the metrics singleton between tests to prevent state bleed."""
    from src.monitoring import metrics as metrics_module

    metrics_module._metrics = metrics_module.RequestMetrics()
    yield
