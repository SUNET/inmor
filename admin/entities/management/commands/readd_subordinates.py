import djclick as click
from django_redis import get_redis_connection

from entities.models import Subordinate


@click.command()
def command():
    "Readds all subordinates from the Database."
    con = get_redis_connection("default")
    # First clean up the existing HashMap in redis
    con.delete("inmor:subordinates")
    subs = Subordinate.objects.all()
    for sub in subs:
        # Means we can reissue this one
        # TODO: reissue and save here
        click.secho(f"Reissued {sub.entityid}")
