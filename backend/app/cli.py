"""Command line for the instance owner (Lot 10, issue #77).

No email is ever sent (no SMTP to configure on a self-hosted instance), so a
forgotten password is reset by an admin from the Settings — and when the
only admin is the one who forgot it, from the machine hosting the instance:

    docker exec crossstitchhelper python -m app.cli list-profiles
    docker exec crossstitchhelper python -m app.cli reset-password someone@example.com

`reset-password` prints a new random password to log in with (then change it
from Settings > My account) and ends every session of that profile.
"""

from __future__ import annotations

import argparse
import secrets
import sys

from sqlalchemy import select

from app import accounts
from app.db import get_session_factory
from app.models import User
from app.schema import ensure_schema


def _list_profiles() -> int:
    with get_session_factory()() as session:
        users = session.execute(select(User).order_by(User.first_name)).scalars().all()
        if not users:
            print("No profile yet: open the app to create the first admin.")
        for user in users:
            print(f"{user.email}\t{user.first_name} {user.last_name}\t{user.role}")
    return 0


def _reset_password(email: str) -> int:
    with get_session_factory()() as session:
        user = session.execute(
            select(User).where(User.email == accounts.normalise_email(email))
        ).scalar_one_or_none()
        if user is None:
            print(f"No profile with the email {email!r} (see `list-profiles`).", file=sys.stderr)
            return 1
        password = secrets.token_urlsafe(12)
        accounts.set_password(session, user, password)
        session.commit()
        print(f"New password for {user.first_name} {user.last_name}: {password}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list-profiles", help="List the profiles (email, name, role).")
    reset = commands.add_parser("reset-password", help="Give a profile a new random password.")
    reset.add_argument("email")
    args = parser.parse_args(argv)

    ensure_schema()
    if args.command == "list-profiles":
        return _list_profiles()
    return _reset_password(args.email)


if __name__ == "__main__":
    sys.exit(main())
