#!/usr/bin/env python3
"""Moco CLI - Thin wrapper for cli_main

This module serves as the entry point for the CLI. It handles early
environment initialization before delegating to cli_main.
"""

# ruff: noqa: E402

# ========================================
# Early initialization (must happen before other imports)
# ========================================
# Import env_loader to setup warning filters and load .env
from .utils.env_loader import load_dotenv_early, setup_warning_filters

# Setup warning filters (before any other imports)
setup_warning_filters()

# Load .env before other modules are imported
load_dotenv_early()

# ========================================
# Main logic imported from cli_main
# ========================================
from .cli_main import (
    app,
    main,
    sessions_app,
    skills_app,
    tasks_app,
    init_environment,
    resolve_provider,
)

__all__ = [
    "app",
    "main",
    "sessions_app",
    "skills_app",
    "tasks_app",
    "init_environment",
    "resolve_provider",
]
