# 160-kotlin-dsl-java-shadow

**Incident:** `java.net.URI(...)` fully-qualified inside a `.gradle.kts` script
failed to compile with `Unresolved reference: 'net'`. In a Kotlin DSL script, the
bare identifier `java` resolves to the **Java plugin extension**, not to the
`java.*` package, so any `java.<subpackage>.<Class>` reference reads the extension
first and never reaches the package. Fully-qualified names are a normal Kotlin
idiom, and this file is Kotlin — so the failure surprises.

The fix is to import the class and use its short name. The pattern is documented
in the top-level `README.md`'s handoff notes and now enforced.

The check restricts itself to the small set of `java.*` subpackages that come up
in build scripts (`net`, `util`, `io`, `nio`, `time`, `security`, `math`) and
looks for uses NOT preceded by `.` — so `sourceSets.getByName("main").java.srcDirs`
is not a false positive.
