# Dev compose command (resolves paths from repo root)
dc := "docker compose -f dev/docker-compose.dev.yml --project-directory ."

_default:
  @just --list --unsorted


# To create the virtual environment for development
[working-directory: 'admin']
venv:
  uv sync

# To create a development environment
dev:
  uv run scripts/create-keys.py

# To run the frontend development server
[working-directory: 'admin/frontend']
dev-frontend:
  pnpm install
  pnpm dev

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

# To check for TypeScript errors in frontend
[working-directory: 'admin/frontend']
lint-frontend:
  pnpm vue-tsc --noEmit

# Lint target for both rust and python
lint: lint-rust lint-python

# To run inmor tests
test-ta *ARGS:
  # Run Rust unit tests first
  cargo test --lib
  # We have integration tests for the inmor rust binary
  uv run pytest -vvv {{ARGS}}

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
  {{dc}} build ta
  {{dc}} build admin
  {{dc}} build frontend

rebuild-ta:
  @cargo build
  {{dc}} restart ta

up:
  {{dc}} up -d

down:
  {{dc}} down

logs:
  {{dc}} logs -f 

t-admin *FLAGS:
  {{dc}} exec admin pytest -vvv {{FLAGS}}

debug-ta:
  {{dc}} run --rm ta /bin/bash

debug-admin:
  {{dc}} run --rm admin /bin/bash

# To remove the files of the dev environment
clean:
  rm -rf .venv
  rm -f public.json private.json admin/private.json

# To recreate db/redis on Fedora
recreate-fedora: down
  sudo rm -rf ./db ./redis
  mkdir db redis
  sudo chcon -Rt container_file_t ./db ./redis ./dev/localhost+2*.pem


# To recreate the db and redis data for tests
recreate-data: recreate-fedora up
  echo "Sleeping for 5 seconds"
  sleep 5
  {{dc}} exec -T -e DJANGO_SUPERUSER_PASSWORD=testpass admin python manage.py setup_admin --username admin --noinput --skip-checks
  INMOR_API_KEY=$({{dc}} exec -T admin python manage.py apikey create --username admin --skip-checks) python scripts/create_redis_db_data.py

# To regenerate the TA entity configuration
regenerate-entity:
  {{dc}} exec admin python manage.py regenerate_entity

# To run the collection walk inside the TA container
collection TA="https://ta.tiime2026.aai.garr.it":
  {{dc}} exec ta ./inmor-collection -c taconfig.toml {{TA}}

# To dump the redis data locally
dump-redis:
  {{dc}} exec redis redis-cli save
  docker cp inmor_redis_1:/data/dump.rdb .
