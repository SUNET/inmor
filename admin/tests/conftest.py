import os
import sys

import pytest
from django.core.management import call_command
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture
def db(request, django_db_setup, django_db_blocker):
    django_db_blocker.unblock()
    call_command("loaddata", "db.json")
