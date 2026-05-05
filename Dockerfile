# syntax=docker/dockerfile:1.7

# Pinned to 3.12 for reliable wheel coverage of cryptography/pyhanko/reportlab.
# The project's pyproject.toml only requires >=3.11, so this is a deployment
# choice, not a project constraint.
ARG PYTHON_VERSION=3.12

# ---------- Stage 1: build wheels ----------
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Cache pinned runtime dependencies first so source-only changes do not
# invalidate this layer.
COPY requirements.txt ./
RUN pip wheel --wheel-dir=/wheels -r requirements.txt

# Build the project itself as a wheel against those dependencies.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip wheel --wheel-dir=/wheels --no-deps .

# ---------- Stage 2: runtime ----------
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# Non-root user the container runs as. UID/GID 1000 maps cleanly to most
# Linux desktops so bind-mounted output files are owned by the host user.
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd --system --gid ${APP_GID} app \
    && useradd --system --uid ${APP_UID} --gid app \
        --create-home --home-dir /home/app app

# Install the wheels produced by the builder stage. --no-index keeps the
# install fully offline so no PyPI fetch is attempted at image build time.
COPY --from=builder /wheels /tmp/wheels
RUN pip install --no-index --find-links=/tmp/wheels pick-at-random \
    && rm -rf /tmp/wheels

# Pre-create the bind-mount target directories with the right ownership.
RUN mkdir -p /data/in /data/out /run/secrets \
    && chown -R app:app /data /run/secrets

USER app
WORKDIR /home/app

ENTRYPOINT ["python", "-m", "pick_at_random.cli.main"]
CMD ["--help"]
