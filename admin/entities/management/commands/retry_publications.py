"""Retry federation updates whose post-commit Redis delivery did not finish."""

from django.core.management.base import BaseCommand, CommandError

from entities.models import PendingPublication
from entities.publication import deliver_publication


class Command(BaseCommand):
    help = "Retry pending trust mark and subordinate Redis publications."

    def handle(self, *args, **options):
        """Attempt each pending job independently and report any remaining failures."""
        failed = 0
        # A failed job must not block a withdrawal for another resource.
        for pk in PendingPublication.objects.order_by("pk").values_list("pk", flat=True).iterator():
            try:
                deliver_publication(pk)
            except Exception as error:
                failed += 1
                self.stderr.write(f"Publication {pk} failed: {error}")
        if failed:
            raise CommandError(f"{failed} publication(s) failed")
