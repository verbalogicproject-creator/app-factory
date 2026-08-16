# Adopt, don't derive

**Rule:** anything with a canonical upstream — a version lattice, a CMake flag
set, a JNI package name, a ProGuard rule set, a font-issuer certificate — is
**copied wholesale from a real project that already compiles**, not reasoned out
from first principles.

## Why

Individually correct choices assemble into combinations nobody has ever built.
Every element passes review; the *set* fails on CI.

The incident on 2026-08-15: an AGP 8.3 → compileSdk 36 bump was assembled by
querying Maven metadata artifact by artifact and taking the newest of each. Each
version was defensible. The combination:

- Hilt requires AGP 9 for its Kotlin 2 support — bumping AGP alone was
  incomplete.
- `kotlinOptions { jvmTarget = "17" }` was removed in AGP 9 — the block
  compiled, silently did nothing, and the Kotlin compiler defaulted to 1.8.
- KSP 2.3.20 was paired with Kotlin 2.3.21 by newest-first thinking; KSP is
  built against a specific Kotlin version, and the mismatch fails at annotation
  processing.

Three CI round trips to discover the incompatibilities one at a time. The bump
took a working day. It could have taken twenty minutes.

Adopting the whole `gradle/libs.versions.toml` from `android/nowinandroid` —
Google-maintained, actively built, uses the same Compose+Hilt+KSP+Room set —
was the fix. It bought a slightly-older Compose BOM than newest-available, and
that was the right trade: newest is not the same as right.

## Corollary

**The binding constraint is usually the oldest component you are forced to
keep, not the newest one you want.** Choosing AGP 8 to "stay safe" created the
Hilt problem; moving to AGP 9 dissolved it. Look for what forces upgrades, not
what allows them.

## Same rule, other layers

- **CMake flag sets for llama.cpp.** `LLAMA_STANDALONE` defaults to true only
  when llama.cpp is the top-level project, and five other flags default off it.
  Configuring from llama.cpp's root builds a unified binary and dies on a
  missing `build-info.h`. Point cmake at
  `examples/llama.android/lib/src/main/cpp` — that is upstream's own build
  path, and it works because upstream tests it.
- **JNI package names.** `libai-chat.so`'s JNI symbols are
  `Java_com_arm_aichat_internal_InferenceEngineImpl_*`. The Kotlin bindings
  must live in `com.arm.aichat.*`. Renaming into a project-local package
  breaks the symbol contract silently — `dlopen` succeeds, method dispatch
  fails on the first call.
- **Font-issuer certificates.** A certificate hash reasoned out from a font's
  package name matches nothing. The certificate is published; fetch it.

## Where the rule already lives

- Rule S6 in the appfactory conformance corpus: *config with a published
  authority is fetched, not generated.*
- `runtime/versions/2026-08.toml` and `2026-08-api36.toml` are adopted
  lattices, not derived ones.
- Preflight check 020 refuses builds that reference files that were reasoned
  should exist but do not.

## Where the rule is not enforced by a check

Some cases are structural rather than pattern-shaped, and no static check can
catch them. This document is where those cases live so a future session can
apply the rule without re-deriving it.
