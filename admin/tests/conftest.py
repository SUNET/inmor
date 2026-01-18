import os
import sys

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client
from dotenv import load_dotenv
from pytest_redis import factories
from redis.client import Redis

trdb = factories.redis_proc(port=6088)

rdb = factories.redisdb("trdb")


_ = load_dotenv()
sys.path.append(os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture(scope="function")
def db(request, django_db_setup, django_db_blocker):
    django_db_blocker.unblock()
    call_command("loaddata", "db.json")


@pytest.fixture(scope="function")
def loadredis(rdb: Redis) -> Redis:
    """Loads the test data into redis instance for testing."""
    redis = rdb
    # with open(os.path.join(dbpath, "dump.data"), "rb") as f:
    # data = f.read()
    # # Now redis-cli against this
    # _ = subprocess.run(["redis-cli", "-p", "6088", "--pipe"], input=data)
    return redis


@pytest.fixture(autouse=True)
def conf_settings(settings):
    # The `settings` argument is a fixture provided by pytest-django.
    settings.FOO = "bar"


@pytest.fixture
def user(db):
    """Create or get a test user for authentication."""
    user, created = User.objects.get_or_create(
        username="testuser",
        defaults={
            "email": "test@example.com",
            "is_staff": True,
            "is_superuser": True,
        },
    )
    if created:
        user.set_password("testpass123")
        user.save()
    return user


@pytest.fixture
def auth_client(user) -> Client:
    """Return an authenticated Django test client."""
    client = Client()
    client.login(username="testuser", password="testpass123")
    return client
