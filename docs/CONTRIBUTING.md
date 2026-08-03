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

## AI, LLMs, and agentic coding

AI-assisted contributions are fine — as long as you have invested a
reasonable amount of time and effort, actually **read the code**, and
understand what it does and why. We are still doing software engineering,
even if it is agentic engineering, and AI agents are not (yet) a substitute
for actually designing and engineering your software to do what you want.

## License

By contributing, you agree that your contributions are licensed under the
project's [MIT license](../LICENSE).
