import djclick as click
from django.db import transaction

from entities.publication import queue_publication
from trustmarks.lib import issue_trustmark
from trustmarks.models import TrustMark


@click.command()
def command():
    """Persist and publish newly signed tokens for active trust marks."""
    for pk in TrustMark.objects.filter(active=True).values_list("pk", flat=True):
        with transaction.atomic():
            tm = TrustMark.objects.select_for_update().filter(pk=pk, active=True).first()
            if tm is None:
                continue
            # Persist the exact token so a retry never signs a different one.
            issue_trustmark(tm, tm.tmt.valid_for)
            tm.save(update_fields=["mark", "expire_at"])
            queue_publication(tm)
        click.secho(f"Reissued {tm.domain}")
