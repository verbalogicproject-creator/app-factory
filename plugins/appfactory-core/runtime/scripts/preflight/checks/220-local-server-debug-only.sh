#!/usr/bin/env bash
# A server an app opens on the phone is reachable by every other app on the phone.
. "$(dirname "${BASH_SOURCE[0]}")/../lib.sh"

meta() {
    ID="220-local-server-debug-only"
    TITLE="local servers are gated to debug builds"
    CATCHES="The web-shell's command server (Ktor on 127.0.0.1) started in RELEASE builds,
unauthenticated. Binding 127.0.0.1 keeps other DEVICES out, not other APPS: loopback
is shared by everything installed on the phone. Any app a user installed could POST
/__sag/command to drive the page, or read /__sag/dom. Found by reading
ShellForegroundService, not by an incident.

A file in a shipped source set (src/main, src/release, flavours -- anything except
test, androidTest and debug) that opens a listening socket must reference
BuildConfig.DEBUG in code, or carry the marker 'appfactory: release-server-ok' with a
reason when a release build deliberately keeps it.

Forms searched (listening sockets reachable from Kotlin/Java on Android):
  embeddedServer(            Ktor
  ServerSocket(              java.net, incl. SSLServerSocket via factory below
  createServerSocket(        javax.net.ServerSocketFactory
  ServerSocketChannel.open(  java.nio
  AsynchronousServerSocketChannel.open(
  LocalServerSocket(         android.net abstract-namespace socket, also app-reachable
  NanoHTTPD                  subclass or constructor
  ServerBootstrap(           Netty

CANNOT SEE: a server started inside a dependency (AAR/JAR), started via reflection,
or a DEBUG reference that does not actually guard the start (the check reads the
file, not control flow). Comments are stripped before matching, so a DEBUG mention
in a comment does not count."
    SCOPE="any"
}
meta
ROOT="$(af_root "${1:-}")"

FORMS='embeddedServer\(|\bServerSocket\(|createServerSocket\(|ServerSocketChannel\.open\(|AsynchronousServerSocketChannel\.open\(|LocalServerSocket\(|\bNanoHTTPD\b|ServerBootstrap\('

found=0
ok=1
for d in "$ROOT"/app/src/*/java "$ROOT"/app/src/*/kotlin; do
    [ -d "$d" ] || continue
    set_name="$(basename "$(dirname "$d")")"
    case "$set_name" in test|androidTest|debug|test*|androidTest*) continue ;; esac
    while IFS= read -r -d '' f; do
        # Strip /* */ and // comments so prose cannot satisfy or trigger the check.
        code="$(perl -0777 -pe 's{/\*.*?\*/}{}gs; s{//[^\n]*}{}g' "$f" 2>/dev/null)"
        printf '%s' "$code" | grep -qE "$FORMS" || continue
        found=1
        if grep -q 'appfactory: release-server-ok' "$f"; then
            note "${f#$ROOT/}: release server allowed by marker"
            continue
        fi
        if ! printf '%s' "$code" | grep -qE 'BuildConfig\.DEBUG'; then
            fail "${f#$ROOT/} opens a listening socket with no BuildConfig.DEBUG gate -- in a release build every app on the phone can reach it over 127.0.0.1"
            ok=0
        fi
    done < <(find "$d" -type f \( -name '*.kt' -o -name '*.java' \) -print0)
done

if [ "$ok" -eq 1 ]; then
    [ "$found" -eq 1 ] && pass "$TITLE" || pass "$TITLE (no local server)"
fi
af_exit
