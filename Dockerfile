FROM rust:1.90 as build
RUN mkdir /app
RUN --mount=type=cache,target=/root/.cargo \
    --mount=type=bind,source=Cargo.toml,target=/app/Cargo.toml \
    --mount=type=bind,source=Cargo.lock,target=/app/Cargo.lock \
    --mount=type=bind,source=src,target=/app/src \
    cd /app && cargo build




##### Production image
FROM debian:12-slim
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
COPY --from=build --chown=app:app /app/target/debug/inmor /app/

USER app
WORKDIR /app
#RUN bash .docker/scripts/setup-sass.sh
EXPOSE 8080
