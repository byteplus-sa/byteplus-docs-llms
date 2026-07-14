# BytePlus Docs for LLMs

A machine-readable index of the official English [BytePlus documentation](https://docs.byteplus.com/en/docs/) and a standalone agent skill for finding and using the right documentation pages.

## Contents

- [`llms.txt`](./llms.txt): BytePlus documentation titles grouped by product, with canonical links.
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

All indexed links point to the official BytePlus documentation at [`docs.byteplus.com`](https://docs.byteplus.com/en/docs/).
