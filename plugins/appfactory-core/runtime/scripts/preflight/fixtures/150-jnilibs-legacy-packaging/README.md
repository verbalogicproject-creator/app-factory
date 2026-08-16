# 150-jnilibs-legacy-packaging

**Incident:** an app that ships `.so` files under `app/src/*/jniLibs/` (or fetches
them via a Gradle task) loaded on device, ran, and had **no CPU backend to run
on**. AGP defaults `packaging.jniLibs.useLegacyPackaging` to `false` when
`minSdk >= 23`, which means the `.so` files are mapped directly from the APK
rather than extracted into the app's native-library directory. `dlopen`ing them
still works — but anything that scans a filesystem path to load backends by
directory (llama.cpp's `ggml_backend_load_all_from_path`, several NNAPI/GPU
runtimes) finds nothing.

The engine loads and the app runs. That is what makes this dangerous: launch
succeeds, and the failure is a silent absence of capability.

**The rule:** if an app has `jniLibs/` contents *or* declares `ndkVersion` or an
`externalNativeBuild` block, `packaging { jniLibs { useLegacyPackaging = true } }`
is required. Not preferred — required.

Localmind hit this in the embedded-provider work (see the pipeline handoff §6).
This check exists so the next app that embeds a native runtime does not.
