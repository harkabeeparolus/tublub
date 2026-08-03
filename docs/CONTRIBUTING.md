# Contributing to tublub

Thanks for your interest! This is a small hobby project, so the process is
informal — but contributions are welcome.

- **Bugs and ideas:** please [open an issue](https://github.com/harkabeeparolus/tublub/issues).
- **Pull requests:** for anything bigger than a small fix, please open an
  issue first so we can discuss it.

## Development setup

The project uses [uv](https://docs.astral.sh/uv/) and
[just](https://just.systems/):

```bash
uv sync         # install dependencies
just run --list # run the CLI from the dev checkout
just check      # lint, typecheck, tests, and workflow audit
```

Please make sure `just check` passes before submitting, and add a note under
`[Unreleased]` in `CHANGELOG.md` for any user-facing changes.

By contributing, you agree that your contributions are licensed under the
project's [MIT license](../LICENSE).
