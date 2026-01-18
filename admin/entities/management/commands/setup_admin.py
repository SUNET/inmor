"""Management command to create an admin user for the Inmor frontend.

Usage:
    python manage.py setup_admin
    python manage.py setup_admin --username admin --email admin@example.com
"""

import getpass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create an admin user for the Inmor frontend"

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            help="Username for the admin user",
        )
        parser.add_argument(
            "--email",
            type=str,
            default="",
            help="Email for the admin user (optional)",
        )
        parser.add_argument(
            "--noinput",
            "--no-input",
            action="store_true",
            help="Do not prompt for input (requires --username and password via env)",
        )

    def handle(self, *args, **options):
        User = get_user_model()

        username = options.get("username")
        email = options.get("email") or ""
        noinput = options.get("noinput")

        # Check if any superuser exists
        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write(
                self.style.WARNING("An admin user already exists. Skipping creation.")
            )
            self.stdout.write("Existing admin users:")
            for user in User.objects.filter(is_superuser=True):
                self.stdout.write(f"  - {user.username}")
            return

        if noinput:
            raise CommandError(
                "Non-interactive mode requires --username. "
                "Set password via DJANGO_SUPERUSER_PASSWORD environment variable."
            )

        # Interactive mode
        if not username:
            username = input("Username: ").strip()
            if not username:
                raise CommandError("Username cannot be empty")

        # Check if username already exists
        if User.objects.filter(username=username).exists():
            raise CommandError(f"User '{username}' already exists")

        if not email:
            email = input("Email address (optional): ").strip()

        # Get password
        password = getpass.getpass("Password: ")
        password_confirm = getpass.getpass("Password (again): ")

        if password != password_confirm:
            raise CommandError("Passwords do not match")

        if len(password) < 8:
            raise CommandError("Password must be at least 8 characters")

        # Create the user
        user = User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
        )

        self.stdout.write(self.style.SUCCESS(f"Successfully created admin user: {user.username}"))
        self.stdout.write("You can now log in to the Inmor Admin frontend with these credentials.")
