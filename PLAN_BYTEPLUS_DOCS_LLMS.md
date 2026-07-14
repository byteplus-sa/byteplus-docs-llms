# BytePlus Docs LLM Corpus Plan

## Objective

Generate two reproducible English-language artifacts from the official BytePlus documentation portal:

- `llms.txt`: an exhaustive llms.txt-compatible Markdown link index grouped by
  official BytePlus category and product library.
- `llms-full.txt`: the detailed Markdown source for every URL in `llms.txt`, delimited by document metadata and source URL.

The official scope is the product catalog exposed at <https://docs.byteplus.com/en/docs/>. The portal currently exposes 14 product categories and its product libraries through server-rendered route data. Generic website pages, other locales, unpublished navigation nodes, legal footer pages, and external marketing/API Explorer pages are outside this corpus.

## Research Findings And Source Contract

BytePlus does not expose a usable documentation sitemap at `/sitemap.xml`; that route returns the site's application/404 shell. The reliable source is the JSON assigned to `window._ROUTER_DATA` in each server-rendered page.

The landing page route data has this shape:

```text
loaderData["(lang)/docs/page"].categoryList[]
  title: category name
  items[]:
    title: product/library name
    href: /docs/<LibraryCode>
```

A library or document page exposes:

```text
loaderData["(lang)/docs/(libcode)/(doccode$)/page"]
  curLib.LibraryCode
  curDoc:
    DocumentCode
    Title
    MDContent
    UpdatedTime
  docListMap[SecondNavID][DocumentCode].value:
    DocumentCode
    Title
    Type
    Status
    Index
    ParentCode
```

Published content pages are selected with `Type == 0` and `Status == 2`. Structural navigation nodes (`Type == 1`) and non-published nodes (for example `Status == 5`) are excluded. All second-navigation maps are traversed so API reference, resources, and other library sections are not lost.

## Files And Code Structure

```text
generate.py          # discovery, fetch, parse, checkpoint, render, validation CLI
README.md            # usage, source contract, scope, and validation instructions
cache/               # ignored response/checkpoint cache, created at runtime
llms.txt             # generated canonical links only
llms-full.txt        # generated detailed Markdown corpus
```

No dependency file is needed. `generate.py` will use Python's standard library (`urllib.request`, `html.parser`, `json`, `concurrent.futures`, `hashlib`, `pathlib`, `argparse`) so the generator remains portable and no package installation is required.

## Generator Design

### CLI

```text
python3 generate.py \
  --output-dir . \
  --cache-dir cache \
  --workers 16 \
  --retries 4
```

Optional flags:

- `--refresh`: ignore cached responses and refetch.
- `--links-only`: stop after discovery and write only `llms.txt`.
- `--validate-only`: validate existing outputs against the cached manifest.
- `--incremental-from PATH`: reconcile the current catalog against an existing
  `llms-full.txt`, reusing unchanged bodies while refreshing cached and newly
  published documents.
- `--limit N`: development-only bounded run for extraction tests.

### Data Models

Use immutable dataclasses:

```python
@dataclass(frozen=True)
class Library:
    category: str
    title: str
    code: str
    landing_url: str

@dataclass(frozen=True)
class Document:
    library_code: str
    section_id: str
    code: str
    title: str
    url: str
    index: int
    parent_code: str

@dataclass(frozen=True)
class ExtractedDocument:
    document: Document
    updated_time: str
    markdown: str
    content_sha256: str
```

### Discovery

1. Fetch `/en/docs/` and parse its `_ROUTER_DATA` assignment with a dedicated `HTMLParser` script collector.
2. Convert every landing `href` from `/docs/<code>` to `https://docs.byteplus.com/en/docs/<code>` and deduplicate by case-sensitive library code.
3. Fetch one landing/document page per library.
4. Read every entry in `docListMap`; keep only leaf content nodes where `Type == 0`, `Status == 2`, and `DocumentCode` is non-empty.
5. Construct `https://docs.byteplus.com/en/docs/<LibraryCode>/<DocumentCode>`.
6. Deduplicate by canonical URL. Sort by landing category order, library order, section order, document `Index`, then URL for deterministic output.

### Fetching And Resumability

- Send a descriptive `User-Agent` and `Accept: text/html`.
- Use bounded concurrency (`--workers`, default 16), a 45-second timeout, exponential retry delays with jitter, and retries for 429/5xx/network failures.
- Cache each successful HTML response under `cache/pages/<sha256(url)>.html` and write a JSON manifest atomically after discovery and after each extraction batch.
- Never silently omit failures. Exhausted URLs are recorded in `cache/failures.json`; the command exits non-zero and does not replace final outputs until all required documents succeed.
- Write generated files to temporary siblings and replace the destination atomically only after validation.

### Content Extraction

For every discovered URL:

1. Parse `_ROUTER_DATA` and select the document-page loader object.
2. Verify `curDoc.DocumentCode` and `curLib.LibraryCode` match the requested URL.
3. Query the public `getDocDetail` endpoint first to obtain the authoritative
   document record without downloading redundant page chrome. Fall back to the
   server-rendered route's `curDoc` only when the API is unavailable. Use
   `Content` for native Markdown records and `MDContent` for editor-backed
   records; fall back to an explicit empty-content marker only when the selected
   field is present but empty.
4. Normalize line endings to LF, trim trailing whitespace, collapse more than three consecutive blank lines, and preserve BytePlus Markdown extensions such as `<Tabs>`, `<Tab>`, tables, fenced code, and inline HTML.
5. Resolve only protocol-relative source URLs (`//docs.byteplus.com/...`) to `https://`; do not rewrite code samples or external links.

Each `llms-full.txt` entry will use an unambiguous boundary:

```markdown
# <Document Title>

Source: https://docs.byteplus.com/en/docs/<LibraryCode>/<DocumentCode>
Library: <Library Title>
Last updated: <ISO timestamp>

<original MDContent>

---
```

The corpus begins with `# BytePlus Documentation` and a generation timestamp/scope note. The boundary is intentionally outside the source body so the detailed documentation remains attributable and separable.

### Output Contracts

`llms.txt` preserves every canonical documentation link while adding the
structure required by the llms.txt proposal:

```markdown
# BytePlus Documentation

> Exhaustive index of published English-language BytePlus documentation.

## <Category> — <Library>

- [<Official document title>](https://docs.byteplus.com/en/docs/<LibraryCode>/<DocumentCode>)
```

The index contains no descriptions or non-document links. H2 headings are
unique and flat so reference parsers can treat every product library as a file
list section.

`llms-full.txt` contains exactly one delimited detailed section per `llms.txt` URL and no rendered navigation/footer content.

## Validation

The generator must fail if any invariant is violated:

- Every Markdown link target is a unique HTTPS URL matching
  `^https://docs\.byteplus\.com/en/docs/[^/]+/[^/]+$`.
- URL count equals the manifest's published-document count.
- Every links file URL appears exactly once as a `Source:` line in `llms-full.txt`, with no extra source entries.
- Requested and returned `LibraryCode`/`DocumentCode` values match.
- Every extracted page has a title and an `MDContent` field; empty bodies are counted and reported separately.
- Failed fetch count is zero before publishing final outputs.
- Ordering is deterministic across two render passes from the same cache.
- Spot checks cover at least ModelArk, a media product, a database product, a networking product, and a page containing code/tables/tabs.

After generation, report library count, published document count, empty-body count, failure count, output byte sizes, and SHA-256 hashes. Run `git diff --check` and inspect `git status --short` without staging or committing.

## Known Risks And Decisions

- The corpus is a point-in-time snapshot; rerunning the generator is required as BytePlus publishes or updates pages.
- The public detail API may throttle full-corpus refreshes. Incremental mode
  preserves the last validated body for unchanged catalog entries and reports
  that behavior explicitly; use a non-incremental refresh when body-level
  freshness for every page is mandatory.
- `llms-full.txt` may be very large. A single file is retained because the user explicitly requested it; the cache and manifest make regeneration and later sharding possible without changing the output contract.
- Some BytePlus pages may intentionally have empty Markdown bodies or content-title mismatches. Preserve the official `MDContent` and report anomalies instead of inventing documentation.
- The portal's internal JSON shape is not a documented public API. Parser errors are explicit so a future schema change fails visibly rather than producing a partial corpus.
- No commit will be created because the user did not request one and the worktree contains unrelated changes.
