import djclick as click
from django_redis import get_redis_connection

from entities.lib import create_server_statement


@click.command()
def command():
    "Regenerates the Trust Anchor entity configuration and stores it in Redis."
    token = create_server_statement()
    con = get_redis_connection("default")
    con.set("inmor:entity_id", token)
    click.secho("Entity configuration regenerated.", fg="green")
