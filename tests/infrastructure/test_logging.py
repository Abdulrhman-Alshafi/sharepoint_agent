"""Tests for infrastructure logging module."""

import logging
import pytest

from src.infrastructure.logging import setup_logging, get_logger


class TestSetupLogging:
    def test_setup_logging_debug_level(self):
        setup_logging(log_level="DEBUG", environment="test")
        root = logging.getLogger()
        assert root.level <= logging.DEBUG

    def test_setup_logging_info_level(self):
        setup_logging(log_level="INFO", environment="test")
        root = logging.getLogger()
        assert root.level <= logging.INFO

    def test_setup_logging_returns_none(self):
        result = setup_logging(log_level="WARNING", environment="production")
        assert result is None

    def test_setup_logging_quiets_httpx(self):
        setup_logging(log_level="DEBUG", environment="test")
        httpx_logger = logging.getLogger("httpx")
        assert httpx_logger.level >= logging.WARNING

    def test_setup_logging_quiets_httpcore(self):
        setup_logging(log_level="DEBUG", environment="test")
        httpcore_logger = logging.getLogger("httpcore")
        assert httpcore_logger.level >= logging.WARNING


class TestGetLogger:
    def test_get_logger_returns_logger(self):
        logger = get_logger("test_module")
        assert isinstance(logger, logging.Logger)

    def test_get_logger_name(self):
        logger = get_logger("my.module")
        assert logger.name == "my.module"

    def test_get_logger_different_names(self):
        l1 = get_logger("a")
        l2 = get_logger("b")
        assert l1 is not l2
