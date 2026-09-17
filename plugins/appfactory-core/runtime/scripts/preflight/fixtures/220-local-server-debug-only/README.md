# 220-local-server-debug-only

Loopback is shared by every app on an Android phone. Binding `127.0.0.1` keeps other
*devices* out, not other *apps*. The web-shell template started its unauthenticated
command server in release builds, so any installed app could drive the page.

- `bug/` — Ktor `embeddedServer` in `src/main`, no gate.
- `bug-debug-in-comment/` — `BuildConfig.DEBUG` appears only in a comment; must still fail.
- `bug-flavour/` — `java.net.ServerSocket` in `src/release` (a shipped source set).
- `bug-plain-socket/` — `LocalServerSocket`, the non-TCP form, also reachable by other apps.
- `fixed/` — gated server in `src/main`; an ungated listener in `androidTest` is ignored.
