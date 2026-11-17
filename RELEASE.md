# Releasing Bound To Rot

> **The one rule: nothing is ever *published* automatically.** Automation
> takes a release all the way to a **draft**; a human reviews the draft and
> hits **Publish**. Everything else (version bump, tagging, building,
> attaching zips) is automated.

## The automated flow (one label, two merges, one click)

Branch protection requires PRs for `main`, so the version bump itself
travels as a PR. The kick-off workflow (`.github/workflows/release-auto.yml`)
runs two legs:

1. **Label the PR.** When the PR that should ship is ready, add the
   **`release`** label before merging into `main`:
   - `release` → patch bump (`0.2.1 → 0.2.2`), the default,
   - `release` + `release:minor` → minor bump (`0.2.1 → 0.3.0`).
2. **Merge it.** The kick-off opens a **release PR**
   (`chore(release): vX.Y.Z`, branch `release/vX.Y.Z`) with just the
   version bump, labelled `release`. It never pushes to `main` directly -
   branch protection forbids it and the bot cannot bypass.
3. **Merge the release PR** (one click). Merging it (authored by
   `github-actions[bot]`, title `chore(release): vX.Y.Z`) makes the
   kick-off push the `vX.Y.Z` tag; the version is re-verified against
   `pyproject.toml` first.
4. **Tag push triggers** the *Release (drafts)* workflow
   (`.github/workflows/release.yml`):
   - runs the test suite on both build runners (Linux + Windows),
   - builds the PyInstaller one-file executables and zips them
     (`dist/BoundToRot-<version>-<os>-<arch>.zip`),
   - attaches the zips to a **draft** GitHub Release with auto-generated
     notes (changelog assembled from merged PRs).
5. **You publish.** Open the Releases tab, review the draft's notes and
   assets, edit the title/blurb if you like, hit **Publish**.

That's it: one label, two merges, one click.

## Cleanup after a failed kick-off (the v0.2.2 incident)

The first live run happened before the pipeline was branch-protection aware
and produced a tag pointing at a broken tree (empty `pyproject.toml`). If a
bad tag ever ships, clean it before retrying:

```bash
git push origin :refs/tags/vX.Y.Z      # delete the remote tag
git tag -d vX.Y.Z                      # delete the local tag
```

A deleted tag re-arms the pipeline; the next labelled merge (or re-merge of
the release PR) re-runs it.

## Guardrails baked in

- **Tag/version lockstep:** the build job re-checks that the tag matches
  `pyproject.toml`'s version and fails the build otherwise.
- **No silent re-tags:** an existing tag aborts the kick-off workflow.
- **Bot-authored release PRs never re-bump:** the bump leg only runs for
  human-authored PRs, so merging the release PR tags without a double bump.
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
