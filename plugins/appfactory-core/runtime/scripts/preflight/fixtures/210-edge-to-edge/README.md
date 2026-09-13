# 210-edge-to-edge

**ANTICIPATED, not an observed incident.** Starting at targetSdk 35, Android enforces
edge-to-edge display and removes the app's ability to opt back into the old
system-bar-reserved layout; at targetSdk 36 there is no opt-out left at all. A
Compose `Activity` that calls `setContent { ... }` without first calling
`enableEdgeToEdge()` (`androidx.activity`) still compiles and still launches — its
content is simply drawn *under* the status bar and navigation bar instead of around
them. There is no crash and no lint error; it is a rendering bug that reads correctly
in a rushed glance and wrong the moment someone looks at the top of the screen.

This check has no incident behind it because the platform change has not shipped
against this corpus yet. It is added ahead of the enforcement date because "the app
compiles and runs" already stopped being sufficient evidence for check 140's targetSdk
floor, for the same reason: a submission requirement that is silent until the worst
possible moment.

**The rule:** once `targetSdk >= 35`, any Kotlin file under `app/src/main` that calls
`setContent {` must be matched by some Kotlin file under `app/src/main` calling
`enableEdgeToEdge(` — outside of a comment. `windowOptOutEdgeToEdgeEnforcement` is
read as a deliberate, temporary opt-out (valid through targetSdk 35, removed at 36)
and reported as a note, not a failure.

**Comments are stripped before matching**, the same way check 150 strips them: a
`// TODO: call enableEdgeToEdge()` is a plan, not code, and `fixtures/bug-comment-only/`
exists to prove a naive grep does not mistake one for the other.
