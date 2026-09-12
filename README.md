# BytePlus Docs for LLMs

A machine-readable index of the official English [BytePlus documentation](https://docs.byteplus.com/en/docs/) and a standalone agent skill for finding and using the right documentation pages.

## Contents

- [`llms.txt`](./llms.txt): BytePlus documentation titles grouped by product, with canonical links.
- [`llms-full.txt`](./llms-full.txt): Full page content for every indexed page.
- [`docs/`](./docs/): Per-library indexes (`docs/<library-code>/llms.txt` and `llms-full.txt`) plus `docs/index.json`; use these to load only the product you need instead of the 180 MB aggregate file.
- [`.agents/skills/byteplus-docs/`](./.agents/skills/byteplus-docs/): Standalone BytePlus documentation research skill with its own bundled index.

## Use the documentation index

Give `llms.txt` to an LLM or search it directly to discover relevant official documentation pages. The index is designed for discovery: technical claims should be verified against the linked live pages.

```bash
rg -i "context caching" llms.txt
rg -i "video on demand.*java|java sdk" llms.txt
```

## Install the agent skill

Copy the complete skill directory into the skills directory used by your agent:

```bash
cp -R .agents/skills/byteplus-docs ~/.agents/skills/
```

The copied directory is self-contained and includes its own `llms.txt`.

## Search from the command line

The bundled Python helper ranks matching pages by product, title, and URL:

```bash
python3 .agents/skills/byteplus-docs/scripts/search_docs.py \
  "ModelArk context caching" --limit 10

python3 .agents/skills/byteplus-docs/scripts/search_docs.py \
  "upload media" --library "Video on Demand"

python3 .agents/skills/byteplus-docs/scripts/search_docs.py \
  "IAM custom policy" --json
```

Python 3 is the only local runtime requirement. Live documentation access and Context7 are recommended for verifying current API, SDK, quota, region, pricing, and availability details.

## Refreshing the indexes

Run `./refresh.sh` to regenerate everything: it reuses unchanged bodies from the
current snapshot, re-fetches documents whose cached API payload is older than 30
days, writes the per-library files, validates the outputs, and syncs the skill
index copy.

```bash
./refresh.sh          # incremental refresh (recommended)
./refresh.sh --full   # ignore caches and re-extract everything
```

`generate.py` crawls the official docs SPA directly. Content is extracted from
the server-rendered `window._ROUTER_DATA` payload and the `getDocDetail` JSON
API; no headless browser is required. A GitHub Actions workflow
(`.github/workflows/refresh.yml`) runs the same script monthly and commits the
result when anything changed.

Useful `generate.py` flags for ad-hoc work:

```bash
# Reuse unchanged bodies from the current llms-full.txt and re-fetch only
# documents whose cached API payload is older than 30 days
python3 generate.py --incremental-from llms-full.txt --max-age 2592000

# Regenerate only the links index
python3 generate.py --links-only

# Verify committed outputs against the crawl manifest
python3 generate.py --validate-only
```

Note: the docs site returns its SPA HTML shell (HTTP 200) for missing paths such
as `/robots.txt`, `/sitemap.xml`, and `/llms.txt`, so there is no official
`llms.txt` to mirror — this repository is the index.

## Skill structure

```text
.agents/skills/byteplus-docs/
├── SKILL.md
├── llms.txt
├── evals/
│   └── evals.json
└── scripts/
    └── search_docs.py
```

## Source

All indexed links point to the official BytePlus documentation at [`docs.byteplus.com`](https://docs.byteplus.com/en/docs/). The crawl uses a descriptive User-Agent, verifies TLS certificates, and fetches only from `docs.byteplus.com` and the documented `www.byteplus.com/api/doc/getDocDetail` JSON endpoint (the same data the public docs pages render); it does not fetch arbitrary API paths. Note that `www.byteplus.com/robots.txt` disallows `/api/` for crawlers while serving the same documentation content on the public pages; the corpus only reads that public content.
