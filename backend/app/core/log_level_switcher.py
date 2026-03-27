"""
Log level switcher for runtime log level adjustment.

This module allows runtime adjustment of log levels without restarting the server.
Useful for debugging specific issues.
"""

import logging
from typing import Optional, Literal


LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def set_log_level(
    level: LogLevel,
    logger_name: Optional[str] = None
):
    """
    Set log level at runtime.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        logger_name: Specific logger name (None for root logger)

    Example:
        set_log_level("DEBUG")  # Set root logger to DEBUG
        set_log_level("DEBUG", "app.core.streaming.stream_coordinator")  # Specific logger
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    if logger_name:
        logger = logging.getLogger(logger_name)
        logger.setLevel(numeric_level)
        print(f"[OK] Set logger '{logger_name}' to {level}")
    else:
        logger = logging.getLogger()
        logger.setLevel(numeric_level)
        print(f"[OK] Set root logger to {level}")


def enable_debug_mode():
    """Enable DEBUG mode for all loggers."""
    import sys
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        stream=sys.stdout
    )
    print("[OK] DEBUG mode enabled for all loggers")


def get_current_log_level(logger_name: Optional[str] = None) -> str:
    """
    Get current log level.

    Args:
        logger_name: Specific logger name (None for root logger)

    Returns:
        Current log level as string
    """
    logger = logging.getLogger(logger_name) if logger_name else logging.getLogger()
    level = logger.getEffectiveLevel()
    return logging.getLevelName(level)


def list_loggers() -> dict:
    """
    List all active loggers and their levels.

    Returns:
        Dict of logger names and their levels
    """
    loggers = {}
    root = logging.getLogger()

    # Get root logger
    loggers["root"] = logging.getLevelName(root.getEffectiveLevel())

    # Get all child loggers
    for name, logger in logging.Logger.manager.loggerDict.items():
        if isinstance(logger, logging.Logger):
            loggers[name] = logging.getLevelName(logger.getEffectiveLevel())

    return loggers


# CLI interface for easy usage
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python log_level_switcher.py <LEVEL> [LOGGER_NAME]")
        print("Example: python log_level_switcher.py DEBUG")
        print("Example: python log_level_switcher.py DEBUG app.core.streaming.stream_coordinator")
        sys.exit(1)

    level = sys.argv[1]
    logger_name = sys.argv[2] if len(sys.argv) > 2 else None

    set_log_level(level, logger_name)

    # Print current state
    print(f"\nCurrent log levels:")
    for name, lvl in list_loggers().items():
        print(f"  {name}: {lvl}")
