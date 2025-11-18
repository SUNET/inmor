FROM python:3.13 as build
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
RUN <<EOT
apt update && apt install xmlsec1 redis vim curl -y
EOT

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=python3.13 \
    UV_PROJECT_ENVIRONMENT=/app

RUN --mount=type=cache,target=/root/.cache \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync \
        --locked \
        --no-dev \
        --no-install-project

##### Production image
FROM python:3.13
ENV DEBIAN_FRONTEND=noninteractive
ENV PATH=/app/bin:$PATH
# Don't run your app as root.
RUN <<EOT
groupadd -r app
useradd -r -d /app -g app -N app
EOT

RUN <<EOT
apt-get clean
apt update && apt install xmlsec1 redis -y
apt dist-upgrade -y

rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
EOT
# Copy from the build container
COPY --from=build --chown=app:app /app /app
COPY ./inmoradmin /app/inmoradmin
COPY ./entities /app/entities
COPY ./trustmarks /app/trustmarks
COPY ./docker-entrypoint.sh /app/
COPY ./manage.py /app/

USER app
WORKDIR /app

