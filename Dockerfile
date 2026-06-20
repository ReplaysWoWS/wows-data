FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# wowsunpack: reads WG's .idx + .pkg layout and dumps GameParams.data → JSON.
# Pinned to a known release; bump deliberately when WG changes the format.
ARG WOWSUNPACK_VERSION=v0.8.0
RUN curl -fsSL -o /tmp/wowsunpack.tar.gz \
      "https://github.com/landaire/wowsunpack/releases/download/${WOWSUNPACK_VERSION}/wowsunpack_${WOWSUNPACK_VERSION}_x86_64-unknown-linux-musl.tar.gz" \
 && tar -xzf /tmp/wowsunpack.tar.gz -C /usr/local/bin \
 && chmod +x /usr/local/bin/wowsunpack \
 && rm /tmp/wowsunpack.tar.gz \
 && wowsunpack --version

# wows_shell: monstrofil/wows-sandbox binary that decrypts WG's obfuscated
# scripts.zip and runs the embedded modules so we can read enums (battle
# types, game modes, ribbons, …) directly from the source of truth. Pinned;
# bump when WG changes the obfuscation scheme. Lives at /opt/wows_shell so
# the binary, helpers/, and any user-supplied script all resolve relative
# paths the way the binary expects.
ARG WOWS_SHELL_VERSION=v0.5.0
RUN mkdir -p /opt/wows_shell \
 && curl -fsSL -o /tmp/wows_shell.tgz \
      "https://github.com/Monstrofil/wows-sandbox/releases/download/${WOWS_SHELL_VERSION}/wows_shell-linux-x86_64.tar.gz" \
 && tar -xzf /tmp/wows_shell.tgz -C /opt/wows_shell --strip-components=1 \
 && chmod +x /opt/wows_shell/wows_shell \
 && rm /tmp/wows_shell.tgz

WORKDIR /app

COPY pyproject.toml ./
RUN pip install .

COPY extractor ./extractor
COPY api ./api
COPY tools ./tools

EXPOSE 8000
