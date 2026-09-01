#!/usr/bin/env bash

set -euo pipefail

mark_repo='https://github.com/marklikesyou/Mark-Guardiola.git'
mark_target="${MARK_INSTALL_DIR:-$HOME/MarkGuardiola}"
mark_system="$(uname -s)"
mark_arch="$(uname -m)"
case "$mark_system/$mark_arch" in
  Darwin/arm64|Darwin/x86_64|Linux/aarch64|Linux/arm64|Linux/x86_64) ;;
  *) printf 'Unsupported platform: %s/%s. On Windows use scripts/install.ps1.\n' "$mark_system" "$mark_arch" >&2; exit 1 ;;
esac
if [[ "${MARK_INSTALL_DRY_RUN:-0}" == 1 ]]; then
  printf 'Platform: %s/%s\nRepository: %s\nDirectory: %s\n' "$mark_system" "$mark_arch" "$mark_repo" "$mark_target"
  printf '%s\n' 'Plan: verify Git/Docker/Compose; clone or reuse; create private .env; build; migrate; restore trusted bundle or rebuild real sources; check data/models; start production services.'
  exit 0
fi

for mark_command in git docker curl od tr; do
  if ! command -v "$mark_command" >/dev/null 2>&1; then
    printf 'Missing prerequisite: %s. Install Git, Docker Desktop (or Docker Engine with Compose on Linux), and curl, then rerun.\n' "$mark_command" >&2
    exit 1
  fi
done
docker compose version >/dev/null
if ! docker info >/dev/null 2>&1; then
  printf '%s\n' 'Docker is not running or accessible. Start Docker, then rerun this installer.' >&2
  exit 1
fi

if [[ -e "$mark_target" ]]; then
  if [[ ! -d "$mark_target/.git" ]]; then
    printf 'Refusing to change existing non-repository directory: %s\n' "$mark_target" >&2
    exit 1
  fi
  mark_remote="$(git -C "$mark_target" remote get-url origin)"
  case "$mark_remote" in
    https://github.com/marklikesyou/Mark-Guardiola|https://github.com/marklikesyou/Mark-Guardiola.git|git@github.com:marklikesyou/Mark-Guardiola.git) ;;
    *) printf '%s\n' 'Existing checkout has a different origin; select a new MARK_INSTALL_DIR.' >&2; exit 1 ;;
  esac
  if [[ -n "$(git -C "$mark_target" status --porcelain)" ]]; then
    printf '%s\n' 'Existing checkout contains local changes. Preserve or commit them before installation.' >&2
    exit 1
  fi
  printf '%s\n' 'Reusing existing checkout without pulling or changing its branch.'
else
  if ! git clone --depth 1 "$mark_repo" "$mark_target"; then
    printf '%s\n' 'Repository clone failed. For a private repository, configure authenticated Git access and rerun. An empty/unpublished repository cannot be installed yet.' >&2
    exit 1
  fi
fi
mark_target="$(cd "$mark_target" && pwd -P)"
if [[ ! -f "$mark_target/infra/compose.production.yml" ]]; then
  printf '%s\n' 'The checkout does not contain a complete installable release.' >&2
  exit 1
fi

if [[ ! -e "$mark_target/.env" ]]; then
  mark_password="$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')"
  (
    umask 077
    set -o noclobber
    printf '%s\n' \
      'MARK_HTTP_PORT=3000' \
      "POSTGRES_PASSWORD=$mark_password" \
      'MARK_API_FOOTBALL_KEY=' \
      'MARK_FOOTBALL_DATA_ORG_KEY=' \
      'MARK_API_FOOTBALL_DAILY_LIMIT=100' \
      'MARK_DEFAULT_SIMULATIONS=10000' \
      'MARK_LOG_LEVEL=INFO' \
      'MARK_BOOTSTRAP_MODE=auto' \
      '' \
      'MARK_BUNDLE_FILE=' \
      'MARK_BUNDLE_SHA256=' > "$mark_target/.env"
  )
  unset mark_password
fi

if ! awk -F= '/^POSTGRES_PASSWORD=/{if ($2 ~ /^[A-Za-z0-9_-]+$/ && length($2)>=24) valid=1} END {exit !valid}' "$mark_target/.env"; then
  printf '%s\n' 'POSTGRES_PASSWORD in .env must contain at least 24 URL-safe characters (letters, digits, _ or -). Existing configuration was preserved.' >&2
  exit 1
fi
if [[ -n "${POSTGRES_PASSWORD:-}" && ! "$POSTGRES_PASSWORD" =~ ^[A-Za-z0-9_-]{24,}$ ]]; then
  printf '%s\n' 'The POSTGRES_PASSWORD environment override is not URL-safe or is too short.' >&2
  exit 1
fi
mkdir -p "$mark_target/bundles"

mark_compose=(docker compose --env-file "$mark_target/.env" -f "$mark_target/infra/compose.production.yml")
printf '%s\n' 'Building the full application. A first real-source rebuild can take hours and several GB; no sample data is substituted.'
printf '%s\n' 'Optional provider keys: set MARK_API_FOOTBALL_KEY / MARK_FOOTBALL_DATA_ORG_KEY in .env. Trusted offline bundle: set MARK_BUNDLE_FILE=/bundles/filename.zip and MARK_BUNDLE_SHA256, and place it in bundles/.'
"${mark_compose[@]}" build api frontend
"${mark_compose[@]}" up -d --wait --wait-timeout 120 db redis
"${mark_compose[@]}" run --rm migrate
"${mark_compose[@]}" run --rm --no-deps bootstrap
"${mark_compose[@]}" up -d --wait --wait-timeout 180 api worker frontend
"${mark_compose[@]}" exec -T api markguardiola install-status
mark_port="${MARK_HTTP_PORT:-$(awk -F= '/^MARK_HTTP_PORT=/{print $2}' "$mark_target/.env")}"
mark_port="${mark_port:-3000}"
curl --fail --silent --show-error "http://127.0.0.1:$mark_port/ready" >/dev/null
printf '\nMarkGuardiola is ready: http://localhost:%s\nInstallation: %s\n' "$mark_port" "$mark_target"
