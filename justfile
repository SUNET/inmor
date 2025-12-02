_default:
  @just --list --unsorted


# To create the virtual environment for development
[working-directory: 'admin']
venv:
  uv sync

# To create a development environment
dev:
  uv run scripts/create-keys.py

# To check for formatting and clippy error in TA
lint-rust:
  cargo clippy
  cargo fmt --check

# To check for formatting and typing errors in Admin
[working-directory: 'admin']
lint-python: venv
  # The Python code is not packaged, so imports are currently
  # relative to the admin/ directory.
  # We don't check api_demo directory.
  . .venv/bin/activate && \
  ty check .  --exclude api_demo && \
  ruff format --check && \
  ruff check .

# Lint target for both rust and python
lint: lint-rust lint-python

# To run inmor tests
test-ta:
  # We have integration tests for the inmor rust binary
  uv run pytest -vvv

# To run django tests for admin
[working-directory: 'admin']
test-admin *ARGS:
  uv run pytest -vvv -s {{ARGS}}

# Test target for both rust and django code
test: test-ta test-admin

# To format the Rust and Python code
reformat:
  uv run ruff format
  cargo fmt

# Building rust binary to be able to be mounted
# inside other linux containers.
build-rs:
  docker run --rm -it \
  -v "$(pwd)":/code \
  -w /code \
  rust:1.88 \
  cargo build

build:
  docker compose build ta
  docker compose build admin

rebuild-ta:
  @cargo build
  docker compose restart ta

up:
  docker compose up -d

down:
  docker compose down

t-admin *FLAGS:
  docker compose exec admin pytest -vvv {{FLAGS}}

debug-ta:
  docker compose run --rm ta /bin/bash

debug-admin:
  docker compose run --rm admin /bin/bash

# To remove the files of the dev environment
clean:
  rm -rf .venv
  rm -f public.json private.json admin/private.json

# To recreate db/redis on Fedora
recreate-fedora: down
  sudo rm -rf ./db ./redis
  mkdir db redis
  sudo chcon -Rt container_file_t ./db ./redis


# To recreate the db and redis data for tests
recreate-data: recreate-fedora up
  echo "Sleeping for 5 seconds"
  sleep 5
  python scripts/create_redis_db_data.py

# To dump the redis data locally
dump-redis:
  docker compose exec redis redis-cli save
  docker cp inmor_redis_1:/data/dump.rdb .

