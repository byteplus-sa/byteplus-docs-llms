# BytePlus Docs LLM Corpus Generator

This tool builds a dated English-language snapshot of the published documentation linked from the official [BytePlus Docs catalog](https://docs.byteplus.com/en/docs/).

It reads BytePlus's server-rendered `window._ROUTER_DATA`, uses the portal's original Markdown (`Content` for native Markdown pages and `MDContent` for editor-backed pages), and excludes structural or unpublished navigation nodes.

If a public page returns the portal's client-only shell, the generator falls back to the same public `www.byteplus.com/api/doc/getDocDetail` endpoint used by the BytePlus frontend.

## Generate

From the vault root:

```bash
python3 generate.py \
  --output-dir . \
  --cache-dir cache \
  --workers 16 \
  --retries 4
```

The command creates:

- `llms.txt`: an exhaustive, specification-aligned Markdown link index grouped by
  official BytePlus category and product library. Every entry uses the official
  document title and canonical URL.
- `llms-full.txt`: one source-attributed detailed Markdown section per URL.
- `cache/manifest.json`: crawl metadata and hashes.
- `cache/pages/`: gzip-compressed response cache for resumable runs.

The final output files are replaced atomically only after all required pages are extracted and validated. Failed requests are written to `cache/failures.json`, and the command exits non-zero.

## Useful Modes

```bash
# Fast extraction test
python3 generate.py --limit 10

# Discover and write links only
python3 generate.py --links-only

# Refetch instead of using the cache
python3 generate.py --refresh

# Revalidate existing outputs against the manifest
python3 generate.py --validate-only

# Refresh the catalog, reuse unchanged full-text bodies, and fetch new/cached pages
python3 generate.py --incremental-from llms-full.txt
```

## Scope And Caveats

- Includes published English documentation nodes where `Type == 0` and `Status == 2` across every product library and second-navigation section.
- Excludes other locales, structural folders, unpublished nodes, generic marketing pages, footer legal links, and external API Explorer/SDK pages.
- Preserves BytePlus Markdown extensions such as tabs, cards, inline HTML, code fences, and tables.
- Some official pages may intentionally contain no body. These are retained with an explicit empty-page marker and counted in the final report.
- BytePlus does not currently expose a usable documentation sitemap at the conventional path, so the live product catalog and embedded navigation graph are the completeness boundary.
- A complete snapshot can be large. Keep the cache for efficient refreshes, or remove it when disk space matters.
- `--incremental-from` reconciles an existing validated full-text snapshot with
  the current catalog. It reuses unchanged bodies, refreshes responses already
  present in the API cache, fetches new pages, and removes pages no longer in the
  published catalog. Use `--refresh` without incremental mode when every body
  must be refetched regardless of the API's crawl rate.
- The exhaustive `llms.txt` intentionally preserves every discovered page. For a
  hosted deployment, consider adding a compact root index and per-product shards
  while retaining this file as the complete link manifest.

See [`PLAN_BYTEPLUS_DOCS_LLMS.md`](PLAN_BYTEPLUS_DOCS_LLMS.md) for the researched source contract, architecture, and validation rules.
