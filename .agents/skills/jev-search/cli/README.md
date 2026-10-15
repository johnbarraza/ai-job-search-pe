# jev-search-cli

Reads Peruvian job boards that a plain fetch cannot (Talento Perú, Laborum, Empleos Perú,
Prácticas.pe, a university bolsa) by driving Chrome with
[jev-browse](https://github.com/0x7067/jev-browse), vendored as a git submodule at
`vendor/jev-browse`.

**Dependencies:** none of its own (plain `bun`). At run time it needs the submodule checked
out, Node 22+, Chrome, and model API keys. See `../SKILL.md` for setup, costs, and the
safety rules (robots.txt gate, stop at any CAPTCHA, read-only goals).

```bash
git submodule update --init vendor/jev-browse    # once, from the repo root
bun run src/cli.ts sites
bun run src/cli.ts search --site talentoperu -q "economista" -l "Lima" --format table
```

## Tests

```bash
bun test --timeout 30000
```

All tests run offline: flag validation exits before any network call, and the search path
is exercised end to end with a fake runner standing in for `node`, `tools/robots_check.py`
and jev-browse.
