"""Environment loader utilities for early initialization.

This module provides functions to load environment variables and setup
warning filters before other modules are imported.
"""

import os
import warnings
from pathlib import Path


def find_dotenv():
    """Find .env file, searching up from current directory."""
    current = Path.cwd()
    while current != current.parent:
        env_path = current / ".env"
        if env_path.exists():
            return str(env_path)
        current = current.parent
    return None


def load_dotenv_early():
    """Load .env file early in the startup process."""
    try:
        from dotenv import load_dotenv
        
        env_path = find_dotenv()
        if env_path:
            load_dotenv(env_path)
        else:
            # Try package-relative .env
            package_env = Path(__file__).parent.parent.parent.parent / ".env"
            if package_env.exists():
                load_dotenv(str(package_env))
    except ImportError:
        # dotenv not installed, skip
        pass


def init_environment(override=False):
    """Initialize environment variables.

    Args:
        override: If True, override existing environment variables.
    """
    try:
        from dotenv import load_dotenv

        env_path = find_dotenv()
        if env_path:
            load_dotenv(env_path, override=override)
        else:
            package_env = Path(__file__).parent.parent.parent.parent / ".env"
            if package_env.exists():
                load_dotenv(str(package_env), override=override)
    except ImportError:
        pass


def setup_warning_filters():
    """Setup warning filters to reduce noise during startup."""
    # Suppress common warnings that clutter output
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
    warnings.filterwarnings("ignore", message=".*pkg_resources.*")
    warnings.filterwarnings("ignore", message=".*google._upb._message.*")
