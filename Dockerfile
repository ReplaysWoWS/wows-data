# Pinned to Debian 12 (bookworm). The unsuffixed `python:3.12-slim` tag now
# points to trixie, whose apt post-invoke clean script trips up older Docker
# storage drivers ("Problem executing scripts APT::Update::Post-Invoke …").
# Bookworm builds cleanly on every Docker we care about.
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# We deliberately do NOT run `apt-get install` here. Older Docker storage
# drivers fail apt's post-invoke cleanup, and a few hosts also see GPG
# verification failures fetching the bookworm InRelease files. The only
# system tools we used to need from apt were `git` (for pip's git+
# installer), `curl` (to fetch two release tarballs and the api
# healthcheck) and `ca-certificates`. All three are replaced below:
#   - `git` → pip installs wgc-download from a github tarball URL instead.
#   - `curl` → Python's stdlib `urllib.request` fetches the tarballs;
#     the healthcheck (in docker-compose.yml) uses `python -c` too.
#   - `ca-certificates` → `python:3.12-slim-bookworm` already ships
#     them, and Python uses them by default for HTTPS.

# wowsunpack: reads WG's .idx + .pkg layout and dumps GameParams.data → JSON.
# Pinned to a known release; bump deliberately when WG changes the format.
ARG WOWSUNPACK_VERSION=v0.8.0
RUN python -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], '/tmp/wowsunpack.tar.gz')" \
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
ARG WOWS_SHELL_VERSION=v0.3.0
RUN mkdir -p /opt/wows_shell \
 && python -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], '/tmp/wows_shell.tgz')" \
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
