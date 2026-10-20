# Contributing

Issues and pull requests are welcome, especially:
- corrections to a rule, with a link to the regulator's document;
- data problems in a specific building;
- new jurisdictions.

## Adding a jurisdiction

A new city needs four pieces. NYC Local Law 97 and Boston BERDO are the next candidates; both publish
building-level data.

1. **A rule file**, `open_bps/rules/<city>_<program>.yaml`. Every value cites the regulator's own document (law,
   regulation or official guidance) with a URL and the date it was checked. Consultant summaries are not sources.
2. **A fetcher**, `open_bps/sources/<city>.py`, that writes a dated raw snapshot with `write_manifest`.
3. **A canonical mapping** in `open_bps/canonical.py`. Every building keeps a `screen_status`; nothing is dropped
   silently.
4. **An engine**, `open_bps/engine/<city>.py`, of pure functions. Its tests reproduce the regulator's own worked
   examples. If the city publishes verdicts, add a validation like DC's and a threshold to the quality gate.

## Development

```bash
uv venv && uv pip install -e ".[dev,app]"
make check      # ruff + pytest (offline)
```

Test fixtures are small samples of the real public data. `scripts/make_fixtures.py` regenerates them from a
full snapshot.
