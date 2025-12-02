import djclick as click
from django_redis import get_redis_connection
import hashlib

from trustmarks.models import TrustMark


@click.command()
def command():
    "Reload TrustMarks for activated entities from the Database to redis."
    con = get_redis_connection("default")
    tms = TrustMark.objects.all()
    for tm in tms:
        if tm.active and tm.mark:
            # Means we can reissue this one
            h = hashlib.new("sha256")
            h.update(tm.mark.encode("utf-8"))
            _ = con.sadd("inmor:tm:alltime", h.hexdigest())
            click.secho(f"Reloaded {tm.domain} - {tm.tmt.tmtype}")
