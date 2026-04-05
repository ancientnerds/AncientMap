"""Tests for the unified LLM abstraction layer in config.py."""
from unittest.mock import MagicMock, patch

import pytest

from pipeline.lyra.config import LyraSettings


@pytest.fixture
def anthropic_settings():
    return LyraSettings(
        anthropic_api_key="sk-ant-test",
        llm_backend="anthropic",
    )


@pytest.fixture
def minimax_settings():
    return LyraSettings(
        minimax_api_key="sk-cp-test",
        minimax_base_url="https://api.minimax.io/anthropic",
        llm_backend="minimax",
    )


class TestClientSelection:
    def test_anthropic_backend_uses_anthropic_client(self, anthropic_settings):
        from pipeline.lyra.config import _get_client

        with patch("pipeline.lyra.config._get_anthropic_client") as mock:
            mock.return_value = MagicMock()
            client = _get_client(anthropic_settings)
            mock.assert_called_once_with("sk-ant-test")

    def test_minimax_backend_uses_minimax_anthropic_client(self, minimax_settings):
        from pipeline.lyra.config import _get_client

        with patch("pipeline.lyra.config._get_minimax_anthropic_client") as mock:
            mock.return_value = MagicMock()
            client = _get_client(minimax_settings)
            mock.assert_called_once_with(minimax_settings)
