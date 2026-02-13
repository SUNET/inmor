FROM debian:13 AS build
RUN apt-get update && apt-get install -y curl build-essential pkg-config libssl-dev cmake && rm -rf /var/lib/apt/lists/*
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH=/root/.cargo/bin:$PATH

RUN mkdir /app
RUN --mount=type=bind,source=Cargo.toml,target=/app/Cargo.toml \
    --mount=type=bind,source=Cargo.lock,target=/app/Cargo.lock \
    --mount=type=bind,source=src,target=/app/src \
    cd /app && cargo build




##### Production image
FROM debian:13-slim
RUN <<EOT
groupadd -r app
useradd -r -d /app -g app -N app
EOT

RUN <<EOT
apt-get clean
apt update && apt install xmlsec1 redis ca-certificates -y
apt dist-upgrade -y

rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
EOT

# Copy from the build container
COPY --from=build --chown=app:app /app/target/debug/inmor /app/
COPY --from=build --chown=app:app /app/target/debug/inmor-collection /app/

USER app
WORKDIR /app
EXPOSE 8080