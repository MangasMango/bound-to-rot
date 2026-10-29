# Contributing

## Basic Guidelines

### Always test your changes.
Do not submit something without at least running the game to see if it works.
If you are changing gameplay behaviour, play the thing you changed: a fix that
crashes on launch or breaks a wave is worse than no fix at all.

Before opening a PR, make sure the same checks CI runs are green:

```
python -m compileall .
python -m pytest tests/ -q
```

If you are adding a feature, add or extend tests in `tests/` to cover it.

### Do not make large changes before discussing them first.
If you are interested in adding a large mechanic/feature or changing large
amounts of code, first contact me via [Discord](https://discord.com/invite/s2rgHuctdc).
For most changes, this should not be necessary. I just want to know if you're
doing something big, so I can offer advice and/or make sure you're not wasting
your time on it.

### Use Conventional Commits with issue references.
Commit messages must follow the [Conventional Commits](https://www.conventionalcommits.org/)
format, with a reference to the issue the commit resolves where one exists:

```
type: #N short summary
```

For example: `fix: #21 keyboard only works if the user has set EN language`.

Allowed types:

| Type | Use it for |
|---|---|
| `fix` | Bug fixes |
| `feat` | New features and mechanics |
| `chore` | Maintenance, dependency updates, non-code work |
| `docs` | Documentation |
| `refactor` | Code changes that don't fix or add anything |
| `test` | Test-only changes |
| `perf` | Performance improvements |
| `ci` | Workflow/CI changes |
| `build` | Packaging, spec files, interpreter/tooling setup |

Rules:

- One commit per issue where practical. If a commit touches several issues,
  split it or list them: `fix: #4, #3 ...`.
- A scope is optional but welcome when it narrows the intent:
  `fix(input): #21 ...`.
- If there is no associated issue, omit the reference: `chore: bump deps`.
- Keep it going forward: legacy commits predate the convention and are exempt
  from the CI check, which only validates new commits.
- Close issues via the PR body (`Closes #N`), not the commit message; PR
  titles use the same `type: #N summary` format.

CI rejects commits that don't start with a valid type and colon.

### Do not make formatting or "cleanup" PRs.
Yes, there are occurrences of trailing spaces, extra newlines, empty indents,
and other tiny errors. No, I don't want to merge, view, or get notified by your
1-line PR fixing it. If you're implementing a PR with modification of *actual
code*, feel free to fix formatting in the general vicinity of your changes, but
please don't waste everyone's time with pointless changes.

I **especially** do not want to see PRs that apply any kind of automated
analysis to the source code to "optimize" anything - my IDE can do that already.
If the PR doesn't actually change anything useful, I'm not going to review or
merge it.

## AI-assisted contributions

AI coding assistants are allowed, but **not without human oversight**.
Every AI-assisted change must be reviewed, understood and owned by a human
before it is submitted. Do not commit output you cannot explain or verify; you
are responsible for what you push.

In practice, this means:

- ✔️ Use AI to draft, review, explain or refactor code, then read it, run it,
  and make sure it actually does what you think it does.
- ✔️ Use AI to research APIs, libraries and error messages.
- ❌ Do not paste generated code straight into a PR without understanding every
  line of it.
- ❌ Do not submit changes you cannot explain if asked "why does this work?"
- ❌ Do not submit AI-generated assets; see
  [THIRD_PARTY_ASSETS.md](THIRD_PARTY_ASSETS.md) for the rules.

If a change came out of a long AI session, say so in the PR description:
context helps review, it doesn't hurt you.

## Style Guidelines

### Follow the formatting of the code you're touching.
- 4 spaces indentation, never tabs.
- `snake_case` for functions, methods and variables; `SCREAMING_CASE` for
  module-level constants.
- Single quotes are the default; double quotes appear in existing strings with
  apostrophes or embedded quotes. Match the file you're in.
- Keep lines around 100 columns; the codebase leans long, don't make it worse.
- Two blank lines between top-level definitions, one between methods.

### Prefer small, direct code.
- Don't create a method/function unless it's used more than once or a block is
  very large. Unnecessary indirection only creates confusion.
- The codebase is built on plain `dict`s and module-level functions. Don't
  introduce classes with getters/setters when a dict or a function does the job.
- Avoid new dependencies. The game runs on a deliberately small stack
  (`raylib`, `numpy`, `pillow`); discuss before adding to it.

### Mind the frame budget.
The simulation is fixed-timestep and the renderer runs every frame. Avoid
allocating in hot paths: reuse lists/dicts, clear instead of recreating, and
keep per-frame work out of anything that runs for every tile, enemy or light.
If you need a scratch buffer, make it module-level and clear it on use.

### Document the non-obvious.
- Module docstrings explain *what the module is for* and any rules the owner
  set (see `systems/flasks.py` for an example).
- Type hints on function signatures where they help: `def level_for_depth(depth: int) -> int:`.
- If a design decision is recorded in `.ai/` ADRs or a comment nearby, don't
  delete it; future readers need it.

## Other Notes

- The in-game dev console (`` ` ``, then `help`) is the fastest way to
  reproduce and verify changes: `god`, `give`, `descend`, `perk` and friends
  exist for exactly this.
- Keep your own agent notes, prompts and plans in `.ai/`; it is gitignored, so
  each contributor's notes stay local.
- An IDE is recommended but not required. PyCharm or VS Code with the Python
  extension both work fine for this codebase.
