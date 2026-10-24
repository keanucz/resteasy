"""Create an app login (Supabase Auth user, already confirmed) and link it to an existing contact.

    uv run python -m scripts.create_login <username> <contact_id> [--password PASSWORD]

Without --password a random one is generated and printed once; it is never stored anywhere.
"""

import argparse
import secrets

from supabase import Client, create_client

from app.core.config import get_settings
from scripts.scripts_constants import GENERATED_PASSWORD_BYTES, USERNAME_EMAIL_DOMAIN


def username_to_email(username: str) -> str:
    """Use an email as given; a plain name becomes <name>@pillow.test, the address they then log in with."""
    trimmed = username.strip().lower()
    return trimmed if "@" in trimmed else f"{trimmed}@{USERNAME_EMAIL_DOMAIN}"


def create_login(db: Client, username: str, password: str, contact_id: str) -> str:
    """Create a confirmed auth user, link it to `contact_id`, and return the new user's id."""
    response = db.auth.admin.create_user(
        {"email": username_to_email(username), "password": password, "email_confirm": True}
    )
    user_id = response.user.id
    linked = db.table("contacts").update({"user_id": user_id}).eq("id", contact_id).execute()
    if not linked.data:
        db.auth.admin.delete_user(user_id)
        raise SystemExit(f"No contact {contact_id}; the login was not created")
    return user_id


def main() -> None:
    """Parse arguments and create the login."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("username")
    parser.add_argument("contact_id")
    parser.add_argument("--password", help="defaults to a random password, printed once")
    args = parser.parse_args()

    settings = get_settings()
    db = create_client(settings.supabase_url, settings.supabase_secret_key)
    password = args.password or secrets.token_urlsafe(GENERATED_PASSWORD_BYTES)
    user_id = create_login(db, args.username, password, args.contact_id)
    print(f"Created login '{args.username}' (auth user {user_id}) for contact {args.contact_id}")
    if not args.password:
        print(f"Password (shown once): {password}")


if __name__ == "__main__":
    main()
