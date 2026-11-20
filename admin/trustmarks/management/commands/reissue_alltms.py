import djclick as click
from django.db import transaction
from django_redis import get_redis_connection

from trustmarks.lib import add_trustmark
from trustmarks.models import TrustMark


@click.command()
def command():
    "Reissues TrustMarks for activated entities from the Database."
    con = get_redis_connection("default")
    for pk in TrustMark.objects.filter(active=True).values_list("pk", flat=True):
        with transaction.atomic():
            tm = TrustMark.objects.select_for_update().filter(pk=pk, active=True).first()
            if tm is not None:
                _ = add_trustmark(
                    tm.domain, tm.tmt.tmtype, tm.tmt.valid_for, tm.additional_claims, con
                )
                click.secho(f"Reissued {tm.domain}")
