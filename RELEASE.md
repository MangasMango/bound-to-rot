# Releasing Bound To Rot

> **The one rule: nothing is ever *published* automatically.** Automation
> takes a release all the way to a **draft**; a human reviews the draft and
> hits **Publish**. Everything else (version bump, tagging, building,
> attaching zips) is automated.

## The automated flow (one label, one click)

1. **Label the PR.** When the PR that should ship is ready, add the
   **`release`** label before merging into `main`:
   - `release` → patch bump (`0.2.1 → 0.2.2`), the default,
   - `release` + `release:minor` → minor bump (`0.2.1 → 0.3.0`).
2. **Merge the PR.** The *Release kick-off* workflow (`.github/workflows/
   release-auto.yml`) then:
   - bumps `pyproject.toml` and commits it to `main`
     (`chore(release): vX.Y.Z`, passes the conventional-commit CI gate),
   - pushes the `vX.Y.Z` tag,
   - refuses to run if the tag already exists (loud failure, no silent skip).
3. **Tag push triggers** the *Release (drafts)* workflow
   (`.github/workflows/release.yml`):
   - runs the test suite on both build runners (Linux + Windows),
   - builds the PyInstaller one-file executables and zips them
     (`dist/BoundToRot-<version>-<os>-<arch>.zip`),
   - attaches the zips to a **draft** GitHub Release with auto-generated
     notes (changelog assembled from merged PRs).
4. **You publish.** Open the Releases tab, review the draft's notes and
   assets, edit the title/blurb if you like, hit **Publish**.

That's it: one label, one merge, one click.

## Guardrails baked in

- **Tag/version lockstep:** the build job re-checks that the tag matches
  `pyproject.toml`'s version and fails the build otherwise.
- **No silent re-tags:** an existing tag aborts the kick-off workflow.
- **Draft-only:** every path ends at a draft; publishing is always a
  human action (owner ruling 2026-11: nothing publishes automatically).
- **CI gates first:** the build runners run the full test suite before
  producing artifacts; a red build can never reach the draft.

## The manual fallback (dry-runs and emergencies)

The old manual path still works and is the right tool for testing a build
without touching a release:

- **Actions → Release (drafts) → Run workflow**
  - `tag`: must match the current `pyproject.toml` version,
  - `confirm`: **empty** = dry-run (builds the matrix, uploads artifacts,
    creates nothing), **`milestone`** = proceeds to the draft.
- Useful when you want to verify the Windows build before merging the PR
  that ships it.

## Creating the labels (one-time setup)

The automation keys off two labels; create them once if missing:

```bash
gh label create release --repo MangasMango/bound-to-rot \
  --description "Merge ships this PR: patch-bump + draft release"
gh label create release:minor --repo MangasMango/bound-to-rot \
  --description "Merge ships this PR with a minor version bump"
```

`release:minor` is always used *together with* `release`.

## Files involved

| File | Role |
|---|---|
| `.github/workflows/release-auto.yml` | version bump + tag on labelled merge |
| `.github/workflows/release.yml` | build matrix + draft release (tag push or manual dispatch) |
| `scripts/build_release.py` | PyInstaller build + zip naming (`dist/BoundToRot-<version>-<os>-<arch>.zip`) |
| `pyproject.toml` | the version of record; the workflow bumps it, never edit it by hand anymore |
