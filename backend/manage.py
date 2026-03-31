#!/usr/bin/env python
import os
import sys
from pathlib import Path


def main() -> None:
    # Load .env from project root (one level above backend/)
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except ImportError:
        pass  # dotenv not installed — rely on environment variables

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "catalyst.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Is it installed and available on your "
            "PYTHONPATH environment variable? Did you forget to activate a "
            "virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
