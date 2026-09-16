#!/usr/bin/env python3
"""Create a local KANDOR .env with independent cryptographic secrets."""

from __future__ import annotations

import argparse
import secrets
import string
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / ".env.example"
TARGET = ROOT / ".env"
ALPHABET = string.ascii_letters + string.digits + "-_"


def random_value(length: int = 48) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def random_password(length: int = 24) -> str:
    """Return a random password that always satisfies KANDOR's class policy."""

    if length < 3:
        raise ValueError("password length must be at least 3")
    characters = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
    ]
    characters.extend(secrets.choice(ALPHABET) for _ in range(length - len(characters)))
    secrets.SystemRandom().shuffle(characters)
    return "".join(characters)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a local KANDOR .env")
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing .env (the old file is not retained)",
    )
    args = parser.parse_args()

    if TARGET.exists() and not args.force:
        parser.error(f"{TARGET} already exists; use --force only if replacement is intended")

    database_admin_password = random_value()
    database_app_password = random_value()
    redis_password = random_value()
    replacements = {
        "CHANGE_ME_local_database_admin_password": database_admin_password,
        "CHANGE_ME_local_database_app_password": database_app_password,
        "CHANGE_ME_local_redis_password": redis_password,
        "CHANGE_ME_64_character_random_signing_secret_0000000000000000000000": random_value(72),
        "CHANGE_ME_admin_development_password_1": random_password(),
        "CHANGE_ME_operator_development_password_1": random_password(),
        "CHANGE_ME_viewer_development_password_1": random_password(),
        "CHANGE_ME_demo_bootstrap_secret_at_least_32_characters": random_value(48),
    }

    content = EXAMPLE.read_text(encoding="utf-8")
    for placeholder, generated in replacements.items():
        content = content.replace(placeholder, generated)

    TARGET.write_text(content, encoding="utf-8", newline="\n")
    try:
        TARGET.chmod(0o600)
    except OSError:
        pass

    print(f"Created {TARGET}")
    print("Development account passwords are stored in that file; protect it and never commit it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
