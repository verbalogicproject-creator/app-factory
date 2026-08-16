# 170-shrinkresources-kotlin-form

Kotlin DSL boolean properties take the `is`-prefixed form: `isShrinkResources = true`.
The Groovy DSL form `shrinkResources = true` written into a `*.gradle.kts` file
compiles as an unresolved reference — the build fails on CI, which is exactly the
2-second-versus-2-minute trap preflight exists to prevent.

**The incident:** listed in the top-level `README.md` failure table ("`shrinkResources`
instead of `isShrinkResources` — Groovy spelling in a Kotlin DSL") but never turned
into a check until now. The template already sets it correctly and even carries a
comment about it (`runtime/templates/gradle/app.build.gradle.kts:116`), but a
future edit or a hand-written module could reintroduce it silently — an appfactory
lesson is only a lesson while it is enforced.

**Case sensitivity is exact, not accidental.** `isShrinkResources` contains the
substring `ShrinkResources` (capital S), not `shrinkResources` (lowercase s), so a
case-sensitive word-boundary match distinguishes the two without a lookbehind.
