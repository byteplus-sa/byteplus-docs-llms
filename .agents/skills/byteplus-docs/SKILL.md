---
name: byteplus-docs
description: Research and answer questions using the official BytePlus documentation index in this repository. Use this skill whenever the user asks about BytePlus products, APIs, SDKs, setup, quotas, regions, architecture, integration, troubleshooting, pricing documentation, or requests official BytePlus documentation links, even when they do not explicitly mention `llms.txt`. Search `llms.txt`, fetch only the relevant live documentation pages, and never load `llms-full.txt`.
compatibility: Requires Python 3. Live claim verification benefits from Context7 or a web-fetching tool.
---

# BytePlus Docs

Use the repository's `llms.txt` as a high-coverage map of official English BytePlus documentation. The index contains titles and canonical URLs, not the evidence needed to answer detailed questions. Discover with the index, then read a small number of relevant live pages.

## Source contract

- Treat `llms.txt` as the required discovery source.
- Do not open, search, summarize, or load `llms-full.txt`. It is intentionally outside this workflow.
- Treat every indexed URL as a candidate, not proof of a technical claim.
- Verify substantive claims against the selected live `docs.byteplus.com` pages.
- Prefer the official BytePlus documentation over blogs, search snippets, or third-party summaries.
- Use Context7 library `/websites/byteplus_en` as corroboration when it is available, especially for API, SDK, and cloud-service questions. The canonical page URL from `llms.txt` remains the citation target.

## Find the index

The bundled search helper finds `llms.txt` by checking, in order:

1. `--index PATH`
2. `BYTEPLUS_LLMS_TXT`
3. the current directory and its parents
4. the skill directory and its parents

In the repository-local installation, no path argument is normally needed.

## Research workflow

1. Identify the product, task, and technical nouns in the request. Preserve exact API operation names, SDK languages, error codes, and feature names.
2. Search the index with two or three focused query variants:

   ```bash
   python3 .agents/skills/byteplus-docs/scripts/search_docs.py "ModelArk context caching" --limit 12
   python3 .agents/skills/byteplus-docs/scripts/search_docs.py "context cache" --library "ModelArk" --limit 12
   ```

3. If the product name is uncertain, list official product-library sections:

   ```bash
   python3 .agents/skills/byteplus-docs/scripts/search_docs.py --list-libraries
   ```

4. Select the smallest useful source set, normally one overview or guide plus one API/SDK reference. Avoid collecting many loosely related pages.
5. Fetch and read those live official pages. For current SDK/API/cloud details, also query Context7 if available. If a page is unavailable, try the next indexed candidate rather than guessing.
6. Answer at the user's level. Put the result first, then implementation details, limitations, and sources as needed.
7. Cite each important factual claim with its canonical `docs.byteplus.com` URL.

Match the requested depth. When the user asks for a concise answer, target one
short explanation, three to six actionable bullets, and two to five sources.
Do not turn a link-finding request into a full tutorial unless the user asks for
one.

## Search helper

The helper parses headings and Markdown links without loading the full index into the model context.

```bash
# Human-readable ranked results
python3 .agents/skills/byteplus-docs/scripts/search_docs.py "VOD upload Java SDK" --limit 10

# Restrict results to a product/library section
python3 .agents/skills/byteplus-docs/scripts/search_docs.py "upload media" --library "Video on Demand"

# Machine-readable output
python3 .agents/skills/byteplus-docs/scripts/search_docs.py "IAM custom policy" --json
```

Search multiple formulations when terminology is ambiguous. Prefer exact feature and operation names over broad terms such as `API`, `guide`, or `overview`.

## Evidence rules

- Clearly distinguish what the index shows (page title, product section, URL) from what the live page states.
- Verify unstable details such as pricing, quotas, region availability, model lists, SDK versions, endpoints, deprecations, and release status at answer time.
- Do not invent a BytePlus feature because a similar Volcengine or third-party feature exists.
- Do not silently substitute Volcengine documentation for BytePlus documentation. If official BytePlus coverage is missing, say so and label any adjacent source separately.
- For procedures, preserve prerequisites, region constraints, authentication requirements, and console-versus-API differences.
- For API answers, capture the operation name, method or SDK call, required parameters, response fields, and documented errors only when the selected source supports them.

## Failure handling

- No matches: remove generic words, try product synonyms, then inspect `--list-libraries`.
- Too many matches: add the product with `--library` and search the exact feature or API operation.
- Live page unavailable: use another indexed page covering the same topic. Do not present the title alone as documentation content.
- Network unavailable: return the most relevant indexed links and state that their contents were not live-verified.
- Conflicting pages: prefer the page with the clearest current/version scope and keep the conflict visible.

## Answer shape

Use only the sections the task needs:

```markdown
[Direct answer]

Implementation notes:
- [Actionable, source-backed detail]

Limitations or open points:
- [Only when relevant]

Sources:
- [Official page title](https://docs.byteplus.com/...)
```

Keep sources close to the claims they support. A short factual question may need only one paragraph and one link.
