#!/bin/sh
# Supervisor for the origin container image. Runs under tini (see the Dockerfile).
#
# Starts the Maxey0-SuperSpace origin on 127.0.0.1, waits until it answers
# /health, then starts cloudflared, which dials out to Cloudflare and is the
# only way traffic reaches the origin (the image exposes no port).
# If either process exits, the other is stopped and this script exits
# non-zero, so the host restarts the whole container rather than leaving a tunnel
# that forwards to nothing, or an origin nobody can reach.
#
# It refuses to start at all -- before any process is launched -- when the
# configuration would make an internet-reachable origin admin-open, because
# the failure mode it prevents is invisible from outside: an origin with
# MAXEY0_AUTH_MODE=disabled and MAXEY0_PUBLIC unset answers every caller as
# admin, and the edge forwards `authorization` without checking it.
#
# Privileges: this script starts as root for exactly two reasons -- a state
# volume may be mounted root-owned, so the state directory on it has to be handed
# to the origin's user, and the two workloads run as two different users.
# Neither workload ever runs as root. The origin (user maxey0) cannot read
# cloudflared's environment in /proc, and so cannot read the tunnel token
# that would let whoever holds it attach a rogue connector to the origin
# hostname.
set -eu

ORIGIN_USER=maxey0
TUNNEL_USER=cloudflared
PORT="${MAXEY0_PORT:-8765}"
TUNNEL="${MAXEY0_TUNNEL:-on}"
STATE_DIR="${SCW_HOME:-/data/scw}"
# ~60s: the origin builds its whole MCP surface at import, which is slow on a
# small shared-CPU container.
HEALTH_ATTEMPTS=60
# Shutdown budget, which must fit the host's stop timeout (set it to 40 s or
# more) or the container is killed mid-drain: cloudflared gets TUNNEL_GRACE_S to finish in-flight
# requests and TUNNEL_STOP_S in all before it is killed, then the origin gets
# ORIGIN_STOP_S. 25 + 10 leaves 5 s of slack.
TUNNEL_GRACE_S=20
TUNNEL_STOP_S=25
ORIGIN_STOP_S=10

log() { printf 'entrypoint: %s\n' "$*" >&2; }
refuse() { log "refusing to start: $*"; exit 78; }
lower() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }

# --- Fail-closed configuration checks ---------------------------------------

# The same values maxey0_ss.auth.policy.is_public_deployment() accepts, so the
# check here and the policy in the process can never disagree about "public".
case "$(lower "${MAXEY0_PUBLIC:-}")" in
    1 | true | yes | on) ;;
    *) refuse "MAXEY0_PUBLIC must be 1 in this image (got '${MAXEY0_PUBLIC:-}'). It is the switch that makes the origin fail closed for callers without credentials, and this container exists to be reachable from the internet." ;;
esac

# Only bearer and oidc authenticate a caller. Unset means `disabled`, and a
# public container never runs that way, even though MAXEY0_PUBLIC=1 would cap
# anonymous callers at the public tools.
case "$(lower "${MAXEY0_AUTH_MODE:-}")" in
    bearer | oidc) ;;
    *) refuse "MAXEY0_AUTH_MODE must be bearer or oidc (got '${MAXEY0_AUTH_MODE:-}'). A public origin never runs with authentication disabled." ;;
esac

case "$TUNNEL" in
    on)
        [ -n "${TUNNEL_TOKEN:-}" ] || refuse "TUNNEL_TOKEN is not set. Provide the tunnel token from the host's secret store, or MAXEY0_TUNNEL=off for a local smoke test."
        # The tunnel is the only ingress. A wider bind would put the origin on
        # the host's private network too, reachable around Cloudflare.
        case "${MAXEY0_HOST:-127.0.0.1}" in
            127.0.0.1 | localhost | ::1) ;;
            *) refuse "MAXEY0_HOST must be a loopback address when the tunnel is on (got '${MAXEY0_HOST}')." ;;
        esac
        ;;
    off) log "MAXEY0_TUNNEL=off: starting the origin without a tunnel. Local smoke tests only." ;;
    *) refuse "MAXEY0_TUNNEL must be on or off (got '$TUNNEL')." ;;
esac

if [ "$(lower "${MAXEY0_AUTH_MODE}")" = bearer ] \
    && [ -z "${MAXEY0_MCP_TOKEN_HASHES:-}${MAXEY0_MCP_TOKENS:-}${MAXEY0_MCP_DEFAULT_BEARER_TOKEN:-}" ]; then
    log "warning: no bearer credential is configured, so every call that needs one will get 401."
fi
if [ -n "${MAXEY0_MCP_TOKENS:-}" ] && [ "$TUNNEL" = on ]; then
    log "warning: MAXEY0_MCP_TOKENS holds plaintext bearer tokens; use MAXEY0_MCP_TOKEN_HASHES instead."
fi

# --- Privileges ---------------------------------------------------------------

if [ "$(id -u)" = 0 ]; then
    command -v setpriv >/dev/null 2>&1 || refuse "setpriv is missing, and the workloads will not run as root."
    mkdir -p "$STATE_DIR"
    chown "$ORIGIN_USER:$ORIGIN_USER" "$STATE_DIR"
    chmod 0700 "$STATE_DIR"
fi

# run_as USER CMD... -- exec CMD as USER, never as root. Started as a non-root
# user (docker run --user), there is nothing to drop and CMD runs as that user.
run_as() {
    user=$1
    shift
    if [ "$(id -u)" = 0 ]; then
        exec env HOME="/home/$user" setpriv --reuid="$user" --regid="$user" --init-groups --no-new-privs "$@"
    fi
    exec "$@"
}

# --- Start and supervise --------------------------------------------------------

origin_pid=""
tunnel_pid=""
stopping=0

# stop_within PID SECONDS -- TERM, wait up to SECONDS for it to exit, then KILL.
stop_within() {
    [ -n "$1" ] || return 0
    kill -TERM "$1" 2>/dev/null || return 0
    waited=0
    while kill -0 "$1" 2>/dev/null && [ "$waited" -lt "$2" ]; do
        sleep 1
        waited=$((waited + 1))
    done
    kill -KILL "$1" 2>/dev/null || true
    wait "$1" 2>/dev/null || true
}

stop_children() {
    # One after the other, not together. TERMed at the same moment, the origin
    # went away while cloudflared was still draining, so the requests it was
    # finishing got a connection refused instead of an answer. The tunnel
    # stops taking requests and drains first; only then does the origin go.
    stop_within "$tunnel_pid" "$TUNNEL_STOP_S"
    stop_within "$origin_pid" "$ORIGIN_STOP_S"
}

# tunnel_env -- strip this shell's environment down to what cloudflared needs.
# An allowlist, not a denylist: unsetting MAXEY0_* left it every provider API
# key and anything else the Machine was given, readable in /proc by whoever
# gets code running as the cloudflared user. It unsets rather than rebuilding
# with `env -i NAME="$VALUE"` so the tunnel token is never expanded here.
tunnel_env() {
    for name in $(env | sed -n 's/^\([A-Za-z_][A-Za-z0-9_]*\)=.*/\1/p'); do
        case "$name" in
            PATH | HOME | TUNNEL_* | HTTP_PROXY | HTTPS_PROXY | NO_PROXY \
                | http_proxy | https_proxy | no_proxy) ;;
            *) unset "$name" 2>/dev/null || true ;;
        esac
    done
}

# Background jobs of a non-interactive shell ignore SIGINT, so a stop is
# always forwarded as SIGTERM, which both uvicorn and cloudflared handle.
trap 'stopping=1' TERM INT HUP

# The origin never sees the tunnel token.
(run_as "$ORIGIN_USER" env -u TUNNEL_TOKEN python -m maxey0_ss.public_server) &
origin_pid=$!
log "origin started (pid $origin_pid), waiting for http://127.0.0.1:$PORT/health"

attempt=0
until python -c 'import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=2).read()' \
    "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; do
    if ! kill -0 "$origin_pid" 2>/dev/null; then
        status=0
        wait "$origin_pid" || status=$?
        log "origin exited with status $status before it became healthy"
        exit 1
    fi
    if [ "$stopping" = 1 ]; then
        stop_children
        exit 0
    fi
    attempt=$((attempt + 1))
    if [ "$attempt" -ge "$HEALTH_ATTEMPTS" ]; then
        log "origin not healthy after $attempt attempts; stopping"
        stop_children
        exit 1
    fi
    sleep 1
done
log "origin healthy"

if [ "$TUNNEL" = on ]; then
    # cloudflared reads the token from TUNNEL_TOKEN (its documented variable
    # for `--token`), so it never appears on a command line that `ps` shows.
    # It needs none of the origin's configuration, bearer credentials included,
    # and none of anything else: see tunnel_env.
    (
        tunnel_env
        run_as "$TUNNEL_USER" cloudflared tunnel --no-autoupdate \
            --grace-period "${TUNNEL_GRACE_S}s" run
    ) &
    tunnel_pid=$!
    log "cloudflared started (pid $tunnel_pid)"
fi

alive() {
    kill -0 "$origin_pid" 2>/dev/null || return 1
    [ -z "$tunnel_pid" ] || kill -0 "$tunnel_pid" 2>/dev/null
}

while [ "$stopping" = 0 ] && alive; do
    sleep 1
done

if [ "$stopping" = 1 ]; then
    log "stop requested; stopping children"
    stop_children
    exit 0
fi

if kill -0 "$origin_pid" 2>/dev/null; then
    log "cloudflared exited; stopping the origin so the Machine restarts"
else
    log "origin exited; stopping so the Machine restarts"
fi
stop_children
exit 1
