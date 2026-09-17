"""Apply migrations without requiring an untracked alembic.ini."""

import argparse
from pathlib import Path


def main():
    from alembic import command
    from alembic.config import Config

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sql",
        action="store_true",
        help="Print PostgreSQL migration SQL without connecting",
    )
    args = parser.parse_args()
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).parents[1] / "migrations")
    )
    command.upgrade(config, "head", sql=args.sql)


if __name__ == "__main__":
    main()
