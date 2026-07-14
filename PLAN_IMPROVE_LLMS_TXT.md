# Plan: Improve BytePlus `llms.txt`

## Outcome

Replace the flat 21,049-line URL dump with a deterministic, specification-aligned Markdown link index while preserving every discovered English BytePlus documentation URL. Keep `llms-full.txt` unchanged.

## Research basis

- The [official llms.txt proposal](https://llmstxt.org/) defines an H1 title, an optional blockquote and prose context, followed by H2 sections containing Markdown link lists. `## Optional` has special skip semantics.
- The [Answer.AI reference implementation](https://github.com/AnswerDotAI/llms-txt) is available in Context7 as `/answerdotai/llms-txt` and parses H2-delimited link lists.
- The official BytePlus documentation corpus is available in Context7 as `/websites/byteplus_en`; the local generator already captures the official category order, library names, document titles, and canonical URLs from [BytePlus Docs](https://docs.byteplus.com/en/docs/).
- Large production sites often federate indexes, but the original requirement explicitly asks for all documentation links in `llms.txt`. This implementation therefore preserves exhaustive coverage and records sharding as future work rather than silently dropping links.

## File format

The generated file will use this grammar:

```markdown
# BytePlus Documentation

> Exhaustive index of published English-language BytePlus documentation.

Source: https://docs.byteplus.com/en/docs/

This index contains every discovered documentation page. Link order follows the official BytePlus catalog and navigation order. Full page content is available in `llms-full.txt`.

## <Category> — <Library>

- [<official document title>](<canonical absolute URL>)
```

H2 names combine category and library so the reference parser receives unique flat sections without unsupported nested headings. Links remain description-free to honor the original “just links” requirement while adding titles and navigational structure.

## Implementation

Update `generate.py`:

1. Change `render_links(documents)` to emit the H1, summary, source/context prose, and one H2 section for each `(category, library_title)` transition.
2. Escape Markdown-sensitive characters in link labels and normalize embedded whitespace in official titles.
3. Keep document ordering driven by `document_sort_key`, which already follows `category_order`, `library_order`, `section_order`, document index, and URL.
4. Replace the URL-per-line validator with a structured parser that checks:
   - exactly one H1 and at least one H2 section;
   - extracted Markdown-link URLs exactly match the discovery manifest in order;
   - every link is unique, absolute HTTPS, and matches the canonical BytePlus URL pattern;
   - section headings are unique;
   - `llms-full.txt` sources still match the same manifest.
5. Regenerate the root `llms.txt` from the existing trusted `llms-full.txt` metadata because the crawl cache is not retained. This local transformation must verify that its URL sequence exactly matches the current URL-only file before replacing it.
6. Keep the generator, plans, and generated artifacts together in the dedicated
   `byteplus-docs-llms` repository.

## Validation

- 21,049 Markdown links and 21,049 unique canonical URLs.
- URL sequence identical to the previous exhaustive index.
- 106 unique library sections.
- H1 first; blockquote immediately after it; no nested headings.
- Every URL exists in `llms-full.txt` in the same order.
- UTF-8, LF line endings, no trailing whitespace.
- Two independent generations are byte-identical.
- Python syntax check for the generator.

## Future improvement

For hosted deployment, add a compact root `llms.txt` plus per-product indexes/shards. That would improve context-window efficiency, but it requires additional artifacts and changes the current exhaustive single-file contract, so it is outside this edit.
