"""Management command for API key management.

Usage:
    python manage.py apikey create --username admin --key-name "CI deploy"
    python manage.py apikey list --username admin
    python manage.py apikey list --all
    python manage.py apikey revoke --username admin --key-name "CI deploy"
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apikeys.models import APIKey


class Command(BaseCommand):
    help = "Manage API keys: create, list, or revoke."

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest="subcommand")
        subparsers.required = True

        # create
        create_parser = subparsers.add_parser("create", help="Create a new API key")
        create_parser.add_argument(
            "--username", type=str, required=True, help="Username of the key owner"
        )
        create_parser.add_argument(
            "--key-name",
            type=str,
            default="auto-generated",
            help="Descriptive name for the API key",
        )

        # list
        list_parser = subparsers.add_parser("list", help="List API keys")
        list_group = list_parser.add_mutually_exclusive_group(required=True)
        list_group.add_argument("--username", type=str, help="Username to list keys for")
        list_group.add_argument(
            "--all", action="store_true", dest="all_users", help="List keys for all users"
        )

        # revoke
        revoke_parser = subparsers.add_parser("revoke", help="Revoke an API key")
        revoke_parser.add_argument(
            "--username", type=str, required=True, help="Username of the key owner"
        )
        revoke_parser.add_argument(
            "--key-name", type=str, required=True, help="Name of the key to revoke"
        )

    def handle(self, *args, **options):
        subcommand = options["subcommand"]
        if subcommand == "create":
            self.handle_create(options)
        elif subcommand == "list":
            self.handle_list(options)
        elif subcommand == "revoke":
            self.handle_revoke(options)

    def handle_create(self, options):
        User = get_user_model()
        username = options["username"]
        key_name = options["key_name"]

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f"User '{username}' does not exist")

        _, plaintext_key = APIKey.create_key(name=key_name, user=user)

        # Print only the key so it can be captured by scripts
        self.stdout.write(plaintext_key)

    def handle_list(self, options):
        User = get_user_model()
        show_all = options.get("all_users", False)

        if show_all:
            keys = APIKey.objects.select_related("user").all()
        else:
            username = options["username"]
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                raise CommandError(f"User '{username}' does not exist")
            keys = APIKey.objects.filter(user=user)

        if not keys.exists():
            self.stdout.write("No API keys found.")
            return

        # Header
        if show_all:
            self.stdout.write(
                f"{'Name':<25} {'Prefix':<10} {'User':<15} {'Active':<8} "
                f"{'Created':<20} {'Expires':<20} {'Last Used':<20}"
            )
            self.stdout.write("-" * 118)
        else:
            self.stdout.write(
                f"{'Name':<25} {'Prefix':<10} {'Active':<8} "
                f"{'Created':<20} {'Expires':<20} {'Last Used':<20}"
            )
            self.stdout.write("-" * 103)

        for key in keys:
            created = key.created_at.strftime("%Y-%m-%d %H:%M") if key.created_at else "-"
            expires = key.expires_at.strftime("%Y-%m-%d %H:%M") if key.expires_at else "never"
            last_used = key.last_used_at.strftime("%Y-%m-%d %H:%M") if key.last_used_at else "never"
            active = "yes" if key.is_active else "no"

            if show_all:
                self.stdout.write(
                    f"{key.name:<25} {key.prefix:<10} {key.user.username:<15} "
                    f"{active:<8} {created:<20} {expires:<20} {last_used:<20}"
                )
            else:
                self.stdout.write(
                    f"{key.name:<25} {key.prefix:<10} {active:<8} "
                    f"{created:<20} {expires:<20} {last_used:<20}"
                )

    def handle_revoke(self, options):
        User = get_user_model()
        username = options["username"]
        key_name = options["key_name"]

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f"User '{username}' does not exist")

        keys = APIKey.objects.filter(user=user, name=key_name, is_active=True)
        count = keys.count()

        if count == 0:
            raise CommandError(f"No active API key named '{key_name}' found for user '{username}'")

        keys.update(is_active=False)
        self.stdout.write(f"Revoked {count} key(s) named '{key_name}' for user '{username}'.")
