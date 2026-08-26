# Multi-stage build. Dependencies are compiled into a virtualenv in `builder` and
# copied into a runtime image that has no compiler, no pip cache, and no build
# headers — the toolchain is the largest part of a Python image and none of it is
# needed to serve a request.

# =============================================================== base ========
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ============================================================ builder ========
FROM base AS builder

# A compiler for any dependency without a manylinux wheel. This layer is
# discarded, so its size costs nothing in the final image. `libpq-dev` is here for
# psycopg should the driver ever change; asyncpg itself ships wheels.
RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build

# Copied on its own, before the source, so editing a module does not invalidate
# the dependency layer and re-run the whole install.
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# The two artifacts pip does not fetch. Neither the spaCy model nor NLTK's punkt
# data is a PyPI dependency of its library, so both are separate steps — and both
# belong here rather than at run time, because a container that downloads a model on
# first request is a container whose readiness depends on the network.
#
# `spacy download` installs the model as a pip package, so it lands inside
# /opt/venv and is copied with it. NLTK's downloader does not: left alone it writes
# to the *building* user's home, which is root's and is never copied. Hence the
# explicit directory, and NLTK_DATA in the runtime stage to point at it.
RUN python -m spacy download en_core_web_sm \
    && python -m nltk.downloader -d /opt/nltk_data punkt_tab stopwords

# ============================================================ runtime ========
FROM base AS runtime

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/nltk_data /opt/nltk_data
# NLTK searches the paths in NLTK_DATA before its built-in list, which is what makes
# a read-only, root-owned data directory work for the unprivileged runtime user.
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    NLTK_DATA=/opt/nltk_data

WORKDIR /app

# A fixed high uid, so a mounted volume's ownership is predictable across hosts.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin veritas

# Created here rather than left to the volume driver: a named volume inherits the
# ownership of the image directory it shadows, so making it `veritas`-owned now is
# what lets the process write Chroma's index at run time as a non-root user.
RUN mkdir -p /app/var && chown veritas:veritas /app/var

COPY --chown=veritas:veritas app ./app

USER veritas

EXPOSE 8000

# `python -c` rather than curl, so the image does not carry an HTTP client and a
# TLS stack it otherwise has no use for. Hits 127.0.0.1 directly — this is a
# liveness check on the local process, not a trip through any proxy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]

# One uvicorn process. Concurrency comes from running more replicas, which lets
# the orchestrator handle restarts and rollout instead of a worker manager inside
# the container. Behind a TLS-terminating proxy, add `--proxy-headers` and set
# `--forwarded-allow-ips` to that proxy's address.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
