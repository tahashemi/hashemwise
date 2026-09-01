#!/usr/bin/env bash
#
# Hashemwise one-line installer for Debian and Ubuntu servers.
#
#   curl -fsSL https://raw.githubusercontent.com/tahashemi/hashemwise/main/install.sh | sudo bash
#
# Non-interactive (for automation):
#
#   curl -fsSL .../install.sh | sudo BOT_TOKEN=... SUPER_ADMIN_ID=... bash
#
# Safe to re-run: it updates the code and restarts, keeping the existing
# ledger and .env untouched.
#
# Install or roll back to a specific release:
#
#   curl -fsSL .../install.sh | sudo VERSION=v1.0.0 bash

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/tahashemi/hashemwise.git}"
INSTALL_DIR="${INSTALL_DIR:-/opt/hashemwise}"
BRANCH="${BRANCH:-main}"

# A git tag such as v1.1.0; empty means track the branch. Captured under a
# different name because this script sources /etc/os-release further down, and
# Debian sets VERSION="12 (bookworm)" in there - which would otherwise silently
# replace whatever the caller asked for.
RELEASE_TAG="${VERSION:-}"

# Must match READY_MARKER in src/main.py.
READY_MARKER="startup complete:"

BOLD=$'\033[1m'; RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; OFF=$'\033[0m'

say()  { printf '%s==>%s %s\n' "$BOLD" "$OFF" "$*"; }
ok()   { printf '%s  ok%s %s\n' "$GREEN" "$OFF" "$*"; }
warn() { printf '%s  !!%s %s\n' "$YELLOW" "$OFF" "$*"; }
die()  { printf '%s  xx%s %s\n' "$RED" "$OFF" "$*" >&2; exit 1; }

# When this script is piped into bash, stdin is the script itself, so prompts
# have to read the terminal directly.
if [ -e /dev/tty ] && [ -r /dev/tty ]; then TTY=/dev/tty; else TTY=""; fi

ask() {
    local prompt="$1" varname="$2" value=""
    [ -n "$TTY" ] || die "no terminal available; pass $varname=... as an environment variable instead"
    while [ -z "$value" ]; do
        printf '%s' "$prompt" > "$TTY"
        read -r value < "$TTY" || die "input cancelled"
    done
    printf '%s' "$value"
}

# ---------------------------------------------------------------- checks

[ "$(id -u)" -eq 0 ] || die "run this as root (prefix the command with sudo)"

# Never depend on the directory this was invoked from: piped into bash it may
# be anywhere, including somewhere that has since been deleted, which makes
# git and apt fail with an unhelpful getcwd error.
cd /

# apt has no terminal to prompt on when this is piped into bash.
export DEBIAN_FRONTEND=noninteractive

if [ -r /etc/os-release ]; then . /etc/os-release; else die "cannot identify this OS"; fi
case "${ID:-}${ID_LIKE:-}" in
    *debian*|*ubuntu*) ok "detected ${PRETTY_NAME:-$ID}" ;;
    *) die "this installer supports Debian and Ubuntu; found ${PRETTY_NAME:-$ID}" ;;
esac

case "$(uname -m)" in
    x86_64|aarch64|arm64) ok "architecture $(uname -m)" ;;
    *) die "unsupported architecture $(uname -m)" ;;
esac

# ---------------------------------------------------------------- docker

install_docker() {
    say "Installing Docker from Docker's official repository"
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl git >/dev/null

    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL "https://download.docker.com/linux/${ID}/gpg" -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc

    local codename
    codename="${VERSION_CODENAME:-${UBUNTU_CODENAME:-}}"
    [ -n "$codename" ] || die "cannot determine the distribution codename"

    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID} ${codename} stable" \
        > /etc/apt/sources.list.d/docker.list

    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin >/dev/null
    systemctl enable --now docker >/dev/null 2>&1 || true
}

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    ok "Docker already present ($(docker --version | cut -d, -f1))"
else
    install_docker
    ok "Docker installed ($(docker --version | cut -d, -f1))"
fi

if ! command -v git >/dev/null 2>&1; then
    say "Installing git"
    apt-get update -qq && apt-get install -y -qq git >/dev/null
fi

# ---------------------------------------------------------------- source

# A full clone, not --depth 1: rolling back to a tag needs the history to
# actually be present.
if [ -d "$INSTALL_DIR/.git" ]; then
    say "Updating $INSTALL_DIR"
    # Installs made by an earlier version of this script are shallow, and a
    # shallow checkout cannot reach an older tag. Deepen it once.
    if [ "$(git -C "$INSTALL_DIR" rev-parse --is-shallow-repository 2>/dev/null)" = "true" ]; then
        git -C "$INSTALL_DIR" fetch --quiet --unshallow || true
    fi
    git -C "$INSTALL_DIR" fetch --quiet --tags --force origin
else
    say "Cloning into $INSTALL_DIR"
    [ -e "$INSTALL_DIR" ] && die "$INSTALL_DIR exists but is not a git checkout; move it aside first"
    git clone --quiet "$REPO_URL" "$INSTALL_DIR"
fi

if [ -n "$RELEASE_TAG" ]; then
    git -C "$INSTALL_DIR" rev-parse --verify --quiet "refs/tags/$RELEASE_TAG" >/dev/null \
        || die "no such release: $RELEASE_TAG"
    git -C "$INSTALL_DIR" checkout --quiet --force "$RELEASE_TAG"
else
    git -C "$INSTALL_DIR" checkout --quiet --force -B "$BRANCH" "origin/$BRANCH"
fi
ok "on $(git -C "$INSTALL_DIR" describe --tags --always) ($(git -C "$INSTALL_DIR" rev-parse --short HEAD))"

cd "$INSTALL_DIR"

# ---------------------------------------------------------------- config

valid_token()  { printf '%s' "$1" | grep -Eq '^[0-9]+:[A-Za-z0-9_-]{30,}$'; }
valid_admin()  { printf '%s' "$1" | grep -Eq '^[0-9]+$'; }

if [ -f .env ] && [ -z "${BOT_TOKEN:-}" ] && [ -z "${SUPER_ADMIN_ID:-}" ]; then
    ok "keeping the existing .env"
else
    if [ -z "${BOT_TOKEN:-}" ]; then
        printf '\n  Create a bot with @BotFather and paste its token.\n' > "${TTY:-/dev/stdout}"
        BOT_TOKEN="$(ask '  BOT_TOKEN: ' BOT_TOKEN)"
    fi
    valid_token "$BOT_TOKEN" || die "that does not look like a Telegram bot token (digits:secret)"

    if [ -z "${SUPER_ADMIN_ID:-}" ]; then
        printf '\n  Get your numeric Telegram id from @userinfobot.\n' > "${TTY:-/dev/stdout}"
        SUPER_ADMIN_ID="$(ask '  SUPER_ADMIN_ID: ' SUPER_ADMIN_ID)"
    fi
    valid_admin "$SUPER_ADMIN_ID" || die "SUPER_ADMIN_ID must be a positive number (a user id, not a chat id)"

    # Written before the file has any content in it, so the secret is never
    # briefly world-readable.
    install -m 600 /dev/null .env
    cat > .env <<EOF
BOT_TOKEN=${BOT_TOKEN}
SUPER_ADMIN_ID=${SUPER_ADMIN_ID}
DB_PATH=/app/data/ledger.db
TELEGRAM_PROXY=${TELEGRAM_PROXY:-}
LOG_LEVEL=${LOG_LEVEL:-INFO}
EOF
    ok "wrote .env (permissions 600)"
fi

# The container runs as the unprivileged user created in the Dockerfile, so
# the bind-mounted ledger directory has to belong to that uid. Created here as
# root it would be root-owned and the bot could not create ledger.db at all.
mkdir -p data
chown -R 10001:10001 data

# ---------------------------------------------------------------- run

say "Building and starting"
docker compose up -d --build

# Waiting for "running" is not enough: the container restarts on failure, so a
# bad token produces a crash loop that is momentarily "running" every few
# seconds and would be reported as success. Wait for the line the bot only
# logs after Telegram has actually accepted the token, and treat any restart
# as a failure.
say "Waiting for Telegram to accept the token"
started=""
for _ in $(seq 1 30); do
    if docker compose logs --no-color 2>/dev/null | grep -q "$READY_MARKER"; then
        started="yes"; break
    fi
    if [ "$(docker inspect hashemwise-bot --format '{{.RestartCount}}' 2>/dev/null || echo 0)" -gt 0 ]; then
        break
    fi
    sleep 2
done

if [ -n "$started" ]; then
    ok "Hashemwise $(git describe --tags --always) is running as $(docker compose logs --no-color 2>/dev/null | grep -o 'as @[A-Za-z0-9_]*' | tail -1 | cut -d@ -f2)"
    printf '\n%sNext:%s\n' "$BOLD" "$OFF"
    printf '  1. Add the bot to your Telegram group.\n'
    printf '  2. You will get a private message with an Authorize button - press it.\n'
    printf '  3. Run /setup in the group, then /help to see everything it does.\n\n'
    printf 'Logs:    docker compose -f %s/docker-compose.yml logs -f\n' "$INSTALL_DIR"
    printf 'Update:  re-run this same command\n'
    printf 'Stop:    docker compose -f %s/docker-compose.yml down\n\n' "$INSTALL_DIR"
else
    warn "the bot did not start. Recent logs:"
    docker compose logs --no-color --tail=25
    docker compose down >/dev/null 2>&1 || true
    printf '
'
    die "startup failed - an incorrect BOT_TOKEN is by far the most common cause.
     Fix it in ${INSTALL_DIR}/.env and re-run this command.
     If the log shows connection timeouts instead, set TELEGRAM_PROXY in that file."
fi
