"""Management command to create an API key for a user.

Usage:
    python manage.py create_api_key --username admin
    python manage.py create_api_key --username admin --key-name "CI script key"
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apikeys.models import APIKey


class Command(BaseCommand):
    help = "Create an API key for a user. Prints the plaintext key to stdout."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            required=True,
            help="Username of the key owner",
        )
        parser.add_argument(
            "--key-name",
            type=str,
            default="auto-generated",
            help="Descriptive name for the API key",
        )

    def handle(self, *args, **options):
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
