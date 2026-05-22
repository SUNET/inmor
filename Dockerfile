# Pin the Rust toolchain to a specific minor so production builds are
# reproducible across release branches. Bump together with the Rust used
# by `just build-rs`. Tracks Debian 13 (trixie) to match the runtime
# stage below.
FROM rust:1.95-trixie AS build
RUN apt-get update && apt-get install -y --no-install-recommends \
        pkg-config libssl-dev cmake build-essential ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir /app
RUN --mount=type=bind,source=Cargo.toml,target=/app/Cargo.toml \
    --mount=type=bind,source=Cargo.lock,target=/app/Cargo.lock \
    --mount=type=bind,source=src,target=/app/src \
    cd /app && cargo build --release




##### Production image
FROM debian:13-slim
RUN <<EOT
groupadd -r app
useradd -r -d /app -g app -N app
EOT

RUN <<EOT
apt-get clean
apt update && apt install xmlsec1 redis ca-certificates curl -y
apt dist-upgrade -y

rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
EOT

# Copy from the build container
COPY --from=build --chown=app:app /app/target/release/inmor /app/
COPY --from=build --chown=app:app /app/target/release/inmor-collection /app/
COPY --from=build --chown=app:app /app/target/release/inmor-keygeneration /app/
COPY --chown=app:app templates/ /app/templates/

USER app
WORKDIR /app
EXPOSE 8080