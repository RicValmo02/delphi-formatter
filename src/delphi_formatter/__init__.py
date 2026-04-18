"""Configurable formatter for Delphi / Object Pascal source code."""

from .formatter import format_source
from .config import load_config, default_config, save_config

__version__ = "0.1.0"
__all__ = ["format_source", "load_config", "default_config", "save_config"]
