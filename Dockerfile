# Hashemwise
#
# python:3.12-slim rather than alpine. Alpine would need gcc + musl-dev in the
# image to build wheels that Debian gets prebuilt, which makes it both slower to
# build and larger by the time the toolchain is installed.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first: this layer is cached and only rebuilds when the
# requirements actually change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# The ledger lives on a bind mount, and the container must be able to write to
# it as a non-root user.
RUN useradd --create-home --uid 10001 hashemwise \
    && mkdir -p /app/data \
    && chown -R hashemwise:hashemwise /app
USER hashemwise

# Matches DB_PATH in .env.example and the compose mount below.
VOLUME ["/app/data"]

CMD ["python", "-m", "src.main"]
