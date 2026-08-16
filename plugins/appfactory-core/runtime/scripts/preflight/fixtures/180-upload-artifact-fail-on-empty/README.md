# 180-upload-artifact-fail-on-empty

**Incident:** an `actions/upload-artifact@v4` step matched no files and went **green**.
The action's `if-no-files-found` input defaults to `warn`, so an empty glob is a
warning, not a failure — the job succeeds, the artifact does not exist, and the
downstream release step (or the human) finds out much later, or never.

That is the same class as the release-signed-with-debug-key trap: **the failure
mode does not look like a failure**. Referenced in the top-level `README.md`
failure table ("`upload-artifact` matched nothing and went green"), and now
enforced here.

The evasion variant `bug-explicit-warn/` sets `if-no-files-found: warn` explicitly.
That is worse than the default in one way — it looks *deliberate* — so the check
requires the literal value `error`, not merely the presence of the key.
