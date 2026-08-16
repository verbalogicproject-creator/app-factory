# Embedding a native runtime

A survival guide for the next appfactory app that ships native code (llama.cpp,
whisper.cpp, an NNAPI runtime, a game engine). Every rule here was paid for
once in the Localmind embedded-engine work (2026-08-15). Frozen now while the
memory is fresh; adopt, don't re-derive.

## The four rules

### 1. `packaging { jniLibs { useLegacyPackaging = true } }` is required, not preferred

AGP defaults it to **false** when `minSdk >= 23`, which maps `.so` files
directly from the APK instead of extracting them into the app's native-library
directory. `dlopen` still works. Anything that scans a filesystem path to load
backends by directory (llama.cpp's `ggml_backend_load_all_from_path`, several
NNAPI/GPU runtimes) finds nothing. The app launches, the engine loads, and the
failure is a silent absence of capability.

Enforced by preflight check **150-jnilibs-legacy-packaging**.

### 2. Build from upstream's example path, not from the project root

llama.cpp's `LLAMA_BUILD_APP` and four sibling flags default to
`LLAMA_STANDALONE`, which is true only when llama.cpp is the top-level project.
Configuring cmake at llama.cpp's root therefore builds the unified binary and
dies on a missing `build-info.h`.

Point cmake at `llama.cpp/examples/llama.android/lib/src/main/cpp` — that is
upstream's own build path, and it works because upstream tests it. The general
rule is `references/adopt-dont-derive.md`; this is one application.

Corollary: **no `-march` flag.** Enable `GGML_BACKEND_DL` +
`GGML_CPU_ALL_VARIANTS` and let the runtime choose an ISA-appropriate backend.
Baking an ISA into the .so SIGILLs on older phones.

### 3. Vendor upstream's Kotlin bindings unmodified, package intact

JNI symbols are `Java_<mangled-package>_<Class>_<method>`. If upstream's
bindings live in `com.arm.aichat.internal.InferenceEngineImpl`, the compiled
`.so` exports `Java_com_arm_aichat_internal_InferenceEngineImpl_*`. Renaming
the Kotlin into a project-local package breaks the symbol contract silently —
`dlopen` succeeds, method dispatch fails on the first native call.

The rule: **package the bindings under the vendor's package, mark the
directory `VENDORED.md`, do not edit.** See
`localmind/app/src/main/java/com/arm/aichat/VENDORED.md` for the pattern.

### 4. Fetch the native libs from a Release, SHA-256 verified, never committed and never built in-tree

19 MB per ABI per pin bump, forever, is not what a Git repo is for. A Gradle
task fetches `<name>-<pin>.zip` from a GitHub Release, verifies against a
committed `SHA256SUMS.txt`, and extracts to the jniLibs directory. **Fail
closed on digest mismatch** — the bytes load as native code into the app
process; a wrong digest is a supply-chain fault, not a warning.

Build the natives in a separate workflow keyed on the pin, not in the app's
Gradle build. In-tree the ABIs build sequentially and add ~7.5 minutes to a
3-minute inner loop, every push. Out-of-tree they build in parallel, once per
pin bump.

## Two additional constraints that surface late

**The JNI layer's minSdk floor is not the engine's.** Upstream's `logging.h`
calls `__android_log_is_loggable`, introduced in Android 11. The engine
libraries themselves build fine at 28. Gate the *feature* at runtime on
`SDK_INT >= 30` and keep the app's `minSdk` at 28 — a library compiled against
30 is inert on 28 as long as it is never `dlopen`'d.

**A native inference engine is stateful; HTTP providers are not.** llama.cpp's
`sendUserPrompt(message)` takes ONE message and keeps the conversation in a KV
cache. HTTP providers are handed the whole transcript every turn. Switching
providers mid-conversation therefore silently drops history. **Bind the model
per conversation, not per app session** — this is a schema decision, made once,
that keeps the "reasoning model then coding model" workflow intact at
conversation granularity.

## What is not in this document

- Model download UX, first-run flows, resumable transfer — these are product
  decisions, not embedding decisions
- Any CPU vs GPU vs NPU benchmarking — that is measurement, not a rule

## Related

- `references/adopt-dont-derive.md` — the general rule; this doc is one
  application per layer
- Preflight check **150-jnilibs-legacy-packaging** — enforces rule 1
- Localmind repo `app/src/main/java/com/arm/aichat/VENDORED.md` — the reference
  implementation of rule 3
