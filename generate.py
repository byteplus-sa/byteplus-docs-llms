#!/usr/bin/env python3
"""Generate links-only and full-content LLM files from BytePlus Docs."""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import datetime as dt
import gzip
import hashlib
import http.client
import json
import random
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable


BASE_URL = "https://docs.byteplus.com"
API_BASE_URL = "https://www.byteplus.com"
INDEX_URL = f"{BASE_URL}/en/docs/"
URL_PATTERN = re.compile(
    r"^https://docs\.byteplus\.com/en/docs/[^/?#]+/[^/?#]+$"
)
USER_AGENT = "BytePlus-Docs-LLM-Corpus/1.0 (+local research archive)"


@dataclasses.dataclass(frozen=True)
class Library:
    category: str
    category_order: int
    title: str
    library_order: int
    code: str
    landing_url: str


@dataclasses.dataclass(frozen=True)
class Document:
    category: str
    category_order: int
    library_title: str
    library_order: int
    library_code: str
    section_id: str
    section_order: int
    code: str
    title: str
    url: str
    index: int
    parent_code: str


@dataclasses.dataclass(frozen=True)
class ExtractedDocument:
    document: Document
    updated_time: str
    markdown: str
    content_sha256: str
    content_type: str
    was_empty: bool


class RouterDataParser(HTMLParser):
    """Collect script bodies and return BytePlus's server-rendered route JSON."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._in_script = False
        self._parts: list[str] = []
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "script":
            self._in_script = True
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._in_script:
            self.scripts.append("".join(self._parts))
            self._in_script = False
            self._parts = []


def parse_router_data(html: str, url: str) -> dict[str, Any]:
    parser = RouterDataParser()
    parser.feed(html)
    marker = "window._ROUTER_DATA = "
    for script in parser.scripts:
        if marker not in script:
            continue
        payload = script.split(marker, 1)[1].strip()
        if payload.endswith(";"):
            payload = payload[:-1]
        try:
            value = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid _ROUTER_DATA JSON at {url}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"Unexpected _ROUTER_DATA type at {url}")
        return value
    raise ValueError(f"No window._ROUTER_DATA found at {url}")


def loader_values(router_data: dict[str, Any]) -> Iterable[dict[str, Any]]:
    loader_data = router_data.get("loaderData")
    if not isinstance(loader_data, dict):
        return []
    return (value for value in loader_data.values() if isinstance(value, dict))


class Fetcher:
    def __init__(
        self,
        cache_dir: Path,
        retries: int,
        timeout: float,
        refresh: bool,
    ) -> None:
        self.page_cache = cache_dir / "pages"
        self.api_cache = cache_dir / "api"
        self.page_cache.mkdir(parents=True, exist_ok=True)
        self.api_cache.mkdir(parents=True, exist_ok=True)
        self.retries = retries
        self.timeout = timeout
        self.refresh = refresh
        self.ssl_context = self._ssl_context()

    @staticmethod
    def _ssl_context() -> ssl.SSLContext:
        """Use Python's trust store, with the standard macOS bundle as fallback."""
        default_paths = ssl.get_default_verify_paths()
        if default_paths.cafile or default_paths.capath:
            return ssl.create_default_context()
        macos_bundle = Path("/etc/ssl/cert.pem")
        if macos_bundle.exists():
            return ssl.create_default_context(cafile=str(macos_bundle))
        return ssl.create_default_context()

    @staticmethod
    def _key(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def _path(self, url: str) -> Path:
        return self.page_cache / f"{self._key(url)}.html.gz"

    def fetch(self, url: str) -> str:
        path = self._path(url)
        if path.exists() and not self.refresh:
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                cached = handle.read()
            if "window._ROUTER_DATA = " in cached:
                return cached
            path.unlink()

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            request = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
            )
            try:
                with urllib.request.urlopen(
                    request, timeout=self.timeout, context=self.ssl_context
                ) as response:
                    status = getattr(response, "status", 200)
                    if status != 200:
                        raise RuntimeError(f"HTTP {status}")
                    charset = response.headers.get_content_charset() or "utf-8"
                    html = response.read().decode(charset, errors="replace")
                if "window._ROUTER_DATA = " not in html:
                    raise RuntimeError("Response omitted server-rendered route data")
                temporary = path.with_suffix(path.suffix + ".tmp")
                with gzip.open(temporary, "wt", encoding="utf-8") as handle:
                    handle.write(html)
                temporary.replace(path)
                return html
            except (
                OSError,
                RuntimeError,
                urllib.error.URLError,
                http.client.HTTPException,
            ) as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                delay = min(20.0, (2**attempt) + random.random())
                time.sleep(delay)
        raise RuntimeError(f"Failed to fetch {url}: {last_error}")

    def fetch_json(self, url: str) -> dict[str, Any]:
        path = self.api_cache / f"{self._key(url)}.json.gz"
        if path.exists() and not self.refresh:
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                value = json.load(handle)
            if isinstance(value, dict):
                return value

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                    "x-use-bff-version": "1",
                },
            )
            try:
                with urllib.request.urlopen(
                    request, timeout=self.timeout, context=self.ssl_context
                ) as response:
                    value = json.loads(response.read().decode("utf-8"))
                if not isinstance(value, dict):
                    raise RuntimeError("JSON endpoint returned a non-object value")
                temporary = path.with_suffix(path.suffix + ".tmp")
                with gzip.open(temporary, "wt", encoding="utf-8") as handle:
                    json.dump(value, handle, ensure_ascii=False)
                temporary.replace(path)
                return value
            except (
                OSError,
                RuntimeError,
                ValueError,
                urllib.error.URLError,
                http.client.HTTPException,
            ) as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                time.sleep(min(20.0, (2**attempt) + random.random()))
        raise RuntimeError(f"Failed to fetch JSON {url}: {last_error}")

    def has_json_cache(self, url: str) -> bool:
        return (self.api_cache / f"{self._key(url)}.json.gz").exists()


def discover_libraries(fetcher: Fetcher) -> list[Library]:
    router = parse_router_data(fetcher.fetch(INDEX_URL), INDEX_URL)
    landing = next(
        (value for value in loader_values(router) if isinstance(value.get("categoryList"), list)),
        None,
    )
    if landing is None:
        raise ValueError("BytePlus landing route has no categoryList")

    libraries: list[Library] = []
    seen: set[str] = set()
    for category_order, category in enumerate(landing["categoryList"]):
        if not isinstance(category, dict):
            continue
        category_title = str(category.get("title") or "Uncategorized").strip()
        for library_order, item in enumerate(category.get("items") or []):
            if not isinstance(item, dict):
                continue
            href = str(item.get("href") or "").strip()
            match = re.fullmatch(r"/docs/([^/?#]+)", href)
            if not match:
                raise ValueError(f"Unexpected BytePlus library href: {href!r}")
            code = match.group(1)
            if code in seen:
                continue
            seen.add(code)
            libraries.append(
                Library(
                    category=category_title,
                    category_order=category_order,
                    title=str(item.get("title") or code).strip(),
                    library_order=library_order,
                    code=code,
                    landing_url=f"{BASE_URL}/en/docs/{code}",
                )
            )
    if not libraries:
        raise ValueError("No BytePlus documentation libraries discovered")
    return libraries


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def discover_library_documents(fetcher: Fetcher, library: Library) -> list[Document]:
    router = parse_router_data(fetcher.fetch(library.landing_url), library.landing_url)
    source = next(
        (
            value
            for value in loader_values(router)
            if isinstance(value.get("curLib"), dict)
            and isinstance(value.get("docListMap"), dict)
        ),
        None,
    )
    if source is None:
        raise ValueError(f"No docListMap found for library {library.code}")

    actual_code = str(source["curLib"].get("LibraryCode") or "")
    if actual_code and actual_code != library.code:
        raise ValueError(
            f"Library mismatch at {library.landing_url}: {actual_code!r} != {library.code!r}"
        )

    sections = source["docListMap"]
    section_order_by_id: dict[str, int] = {}
    for order, section in enumerate(source["curLib"].get("SecondNav") or []):
        if isinstance(section, dict) and section.get("ID") is not None:
            section_order_by_id[str(section["ID"])] = order

    documents: list[Document] = []
    seen: set[str] = set()
    for fallback_order, (section_id, nodes) in enumerate(sections.items()):
        if not isinstance(nodes, dict):
            continue
        section_order = section_order_by_id.get(str(section_id), fallback_order)
        for node in nodes.values():
            if not isinstance(node, dict) or not isinstance(node.get("value"), dict):
                continue
            value = node["value"]
            if _as_int(value.get("Type"), -1) != 0 or _as_int(value.get("Status"), -1) != 2:
                continue
            code = str(value.get("DocumentCode") or "").strip()
            if not code or code in seen:
                continue
            seen.add(code)
            url = f"{BASE_URL}/en/docs/{library.code}/{urllib.parse.quote(code, safe='-_~.') }"
            documents.append(
                Document(
                    category=library.category,
                    category_order=library.category_order,
                    library_title=library.title,
                    library_order=library.library_order,
                    library_code=library.code,
                    section_id=str(section_id),
                    section_order=section_order,
                    code=code,
                    title=str(value.get("Title") or value.get("EnTitle") or code).strip(),
                    url=url,
                    index=_as_int(value.get("Index")),
                    parent_code=str(value.get("ParentCode") or ""),
                )
            )
    return documents


def normalize_markdown(markdown: str) -> str:
    markdown = markdown.replace("\r\n", "\n").replace("\r", "\n")
    markdown = re.sub(r"(?m)[ \t]+$", "", markdown)
    markdown = re.sub(r"\n{4,}", "\n\n\n", markdown)
    markdown = markdown.replace("](//docs.byteplus.com/", "](https://docs.byteplus.com/")
    return markdown.strip()


def document_api_url(document: Document) -> str:
    query = urllib.parse.urlencode(
        {
            "LibraryCode": document.library_code,
            "DocumentCode": document.code,
            "type": "online",
            "TimeBefore": "",
        }
    )
    return f"{API_BASE_URL}/api/doc/getDocDetail?{query}"


def extract_document(fetcher: Fetcher, document: Document) -> ExtractedDocument:
    api_url = document_api_url(document)
    source: dict[str, Any] = {}
    cur_doc: dict[str, Any] | None = None
    try:
        payload = fetcher.fetch_json(api_url)
        result = payload.get("Result")
        metadata = payload.get("ResponseMetadata")
        if isinstance(result, dict) and not (
            isinstance(metadata, dict) and metadata.get("Error")
        ):
            cur_doc = result
    except RuntimeError:
        pass

    if cur_doc is None:
        router = parse_router_data(fetcher.fetch(document.url), document.url)
        source = next(
            (
                value
                for value in loader_values(router)
                if isinstance(value.get("curDoc"), dict)
            ),
            {},
        )
        route_doc = source.get("curDoc")
        if not isinstance(route_doc, dict):
            raise ValueError(f"No document content returned for {document.url}")
        cur_doc = route_doc
    returned_code = str(cur_doc.get("DocumentCode") or "")
    returned_library = str(cur_doc.get("LibraryCode") or source.get("curLibCode") or "")
    if returned_code != document.code or returned_library != document.library_code:
        raise ValueError(
            f"Route mismatch at {document.url}: {returned_library}/{returned_code}"
        )

    content_type = str(cur_doc.get("ContentType") or "").lower()
    field = "Content" if content_type == "md" else "MDContent"
    if field not in cur_doc or cur_doc[field] is None:
        raise ValueError(f"Missing {field} at {document.url}")
    markdown = normalize_markdown(str(cur_doc[field]))
    was_empty = not markdown
    if was_empty:
        markdown = "_(This BytePlus documentation page contains no body content.)_"
    return ExtractedDocument(
        document=document,
        updated_time=str(cur_doc.get("UpdatedTime") or ""),
        markdown=markdown,
        content_sha256=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        content_type=content_type,
        was_empty=was_empty,
    )


def document_sort_key(document: Document) -> tuple[Any, ...]:
    return (
        document.category_order,
        document.library_order,
        document.section_order,
        document.index,
        document.url,
    )


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def manifest_payload(
    libraries: list[Library], documents: list[Document], extracted: list[ExtractedDocument]
) -> dict[str, Any]:
    extracted_by_url = {item.document.url: item for item in extracted}
    return {
        "source": INDEX_URL,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "library_count": len(libraries),
        "document_count": len(documents),
        "extracted_count": len(extracted),
        "empty_body_count": sum(item.was_empty for item in extracted),
        "libraries": [dataclasses.asdict(item) for item in libraries],
        "documents": [
            {
                **dataclasses.asdict(item),
                "updated_time": extracted_by_url[item.url].updated_time
                if item.url in extracted_by_url
                else "",
                "content_type": extracted_by_url[item.url].content_type
                if item.url in extracted_by_url
                else "",
                "content_sha256": extracted_by_url[item.url].content_sha256
                if item.url in extracted_by_url
                else "",
            }
            for item in documents
        ],
    }


def escape_link_label(value: str) -> str:
    """Return a single-line Markdown link label without changing its meaning."""
    value = " ".join(value.split())
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def render_links(documents: list[Document]) -> str:
    """Render the exhaustive corpus as a specification-aligned llms.txt index."""
    parts = [
        "# BytePlus Documentation\n\n",
        "> Exhaustive index of published English-language BytePlus documentation.\n\n",
        f"Source: {INDEX_URL}\n\n",
        "This index contains every discovered documentation page. Link order follows "
        "the official BytePlus catalog and navigation order. Full page content is "
        "available in `llms-full.txt`.\n",
    ]
    previous_section: tuple[str, str] | None = None
    for document in documents:
        section = (document.category, document.library_title)
        if section != previous_section:
            category, library = section
            heading = " — ".join(" ".join(value.split()) for value in (category, library))
            parts.append(f"\n## {heading}\n\n")
            previous_section = section
        parts.append(f"- [{escape_link_label(document.title)}]({document.url})\n")
    return "".join(parts)


def render_full(extracted: list[ExtractedDocument]) -> str:
    generated_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    parts = [
        "# BytePlus Documentation\n\n",
        f"Generated: {generated_at}\n\n",
        f"Source: {INDEX_URL}\n\n",
        "Scope: Published English-language documentation linked from the BytePlus Docs catalog.\n",
    ]
    for item in extracted:
        title = item.document.title.replace("\n", " ").strip()
        parts.extend(
            [
                "\n---\n\n",
                f"# {title}\n\n",
                f"Source: {item.document.url}\n",
                f"Library: {item.document.library_title}\n",
                f"Last updated: {item.updated_time or 'Unknown'}\n\n",
                item.markdown,
                "\n",
            ]
        )
    return "".join(parts)


def load_incremental_snapshot(
    path: Path, documents: list[Document]
) -> dict[str, ExtractedDocument]:
    """Load reusable document bodies from a previously validated llms-full.txt."""
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"(?ms)^# [^\n]+\n\n"
        r"Source: (?P<url>https://docs\.byteplus\.com/en/docs/[^\s]+)\n"
        r"Library: [^\n]*\n"
        r"Last updated: (?P<updated>[^\n]*)\n\n"
        r"(?P<body>.*?)"
        r"(?=\n---\n\n# [^\n]+\n\nSource: "
        r"https://docs\.byteplus\.com/en/docs/|\Z)"
    )
    document_by_url = {document.url: document for document in documents}
    loaded: dict[str, ExtractedDocument] = {}
    for match in pattern.finditer(text):
        url = match.group("url")
        document = document_by_url.get(url)
        if document is None:
            continue
        if url in loaded:
            raise ValueError(f"Duplicate Source entry in incremental snapshot: {url}")
        markdown = normalize_markdown(match.group("body"))
        loaded[url] = ExtractedDocument(
            document=document,
            updated_time=match.group("updated"),
            markdown=markdown,
            content_sha256=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            content_type="snapshot",
            was_empty=markdown
            == "_(This BytePlus documentation page contains no body content.)_",
        )
    if not loaded:
        raise ValueError(f"No reusable documents found in incremental snapshot {path}")
    return loaded


def validate_outputs(
    links_text: str,
    full_text: str | None,
    documents: list[Document],
) -> None:
    if not links_text.startswith("# BytePlus Documentation\n\n> "):
        raise ValueError("llms.txt must start with its H1 and blockquote summary")
    if len(re.findall(r"(?m)^# ", links_text)) != 1:
        raise ValueError("llms.txt must contain exactly one H1")
    headings = re.findall(r"(?m)^## (\S.*)$", links_text)
    if not headings or len(headings) != len(set(headings)):
        raise ValueError("llms.txt must contain unique, non-empty H2 sections")
    urls = re.findall(
        r"(?m)^- \[(?:\\.|[^\]])+\]\((https://docs\.byteplus\.com/en/docs/[^\s)]+)\)$",
        links_text,
    )
    expected = [document.url for document in documents]
    if urls != expected:
        raise ValueError("llms.txt URLs or ordering do not match the discovery manifest")
    if len(urls) != len(set(urls)):
        raise ValueError("llms.txt contains duplicate URLs")
    invalid = [url for url in urls if not URL_PATTERN.fullmatch(url)]
    if invalid:
        raise ValueError(f"llms.txt contains invalid canonical URLs: {invalid[:3]}")
    if full_text is not None:
        sources = re.findall(r"(?m)^Source: (https://docs\.byteplus\.com/en/docs/[^\s]+)$", full_text)
        document_sources = [source for source in sources if URL_PATTERN.fullmatch(source)]
        if document_sources != expected:
            raise ValueError("llms-full.txt Source entries do not exactly match llms.txt")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_documents_from_manifest(path: Path) -> list[Document]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        Document(**{field.name: item[field.name] for field in dataclasses.fields(Document)})
        for item in payload.get("documents", [])
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path.cwd())
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "cache",
    )
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--links-only", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument(
        "--incremental-from",
        type=Path,
        help="Reuse unchanged bodies from an existing llms-full.txt snapshot",
    )
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.workers < 1 or args.retries < 0 or (args.limit is not None and args.limit < 1):
        raise ValueError("workers must be positive; retries non-negative; limit positive")

    output_dir = args.output_dir.resolve()
    cache_dir = args.cache_dir.resolve()
    manifest_path = cache_dir / "manifest.json"
    links_path = output_dir / "llms.txt"
    full_path = output_dir / "llms-full.txt"

    if args.validate_only:
        documents = load_documents_from_manifest(manifest_path)
        links_text = links_path.read_text(encoding="utf-8")
        full_text = full_path.read_text(encoding="utf-8")
        validate_outputs(links_text, full_text, documents)
        print(f"Validated {len(documents)} documents")
        return 0

    fetcher = Fetcher(cache_dir, args.retries, args.timeout, args.refresh)
    libraries = discover_libraries(fetcher)
    print(f"Discovered {len(libraries)} libraries", flush=True)

    discovery_failures: dict[str, str] = {}
    documents: list[Document] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(discover_library_documents, fetcher, library): library
            for library in libraries
        }
        for completed, future in enumerate(concurrent.futures.as_completed(futures), 1):
            library = futures[future]
            try:
                documents.extend(future.result())
            except Exception as exc:  # noqa: BLE001 - collected for complete crawl report
                discovery_failures[library.landing_url] = str(exc)
            if completed % 10 == 0 or completed == len(futures):
                print(f"Inspected {completed}/{len(futures)} libraries", flush=True)

    if discovery_failures:
        write_json_atomic(cache_dir / "failures.json", discovery_failures)
        raise RuntimeError(f"Library discovery failed for {len(discovery_failures)} URLs")

    by_url: dict[str, Document] = {}
    for document in sorted(documents, key=document_sort_key):
        by_url.setdefault(document.url, document)
    documents = list(by_url.values())
    if args.limit is not None:
        documents = documents[: args.limit]
    print(f"Discovered {len(documents)} published documents", flush=True)

    links_text = render_links(documents)
    validate_outputs(links_text, None, documents)
    if args.links_only:
        write_text_atomic(links_path, links_text)
        write_json_atomic(manifest_path, manifest_payload(libraries, documents, []))
        print(f"Wrote {links_path}")
        return 0

    failures: dict[str, str] = {}
    reused: dict[str, ExtractedDocument] = {}
    if args.incremental_from is not None:
        reused = load_incremental_snapshot(args.incremental_from.resolve(), documents)
        print(f"Loaded {len(reused)} reusable document bodies", flush=True)

    documents_to_extract = [
        document
        for document in documents
        if document.url not in reused
        or fetcher.has_json_cache(document_api_url(document))
    ]
    extracted: list[ExtractedDocument] = list(reused.values())
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(extract_document, fetcher, document): document
            for document in documents_to_extract
        }
        total = len(futures)
        for completed, future in enumerate(concurrent.futures.as_completed(futures), 1):
            document = futures[future]
            try:
                extracted.append(future.result())
            except Exception as exc:  # noqa: BLE001 - collected for complete crawl report
                failures[document.url] = str(exc)
            if completed % 25 == 0 or completed == total:
                print(f"Refreshed {completed}/{total} document bodies", flush=True)

    if failures:
        write_json_atomic(cache_dir / "failures.json", failures)
        write_json_atomic(manifest_path, manifest_payload(libraries, documents, extracted))
        raise RuntimeError(f"Document extraction failed for {len(failures)} URLs")

    extracted_by_url = {item.document.url: item for item in extracted}
    extracted = [extracted_by_url[document.url] for document in documents]
    full_text = render_full(extracted)
    validate_outputs(links_text, full_text, documents)
    write_text_atomic(links_path, links_text)
    write_text_atomic(full_path, full_text)
    write_json_atomic(manifest_path, manifest_payload(libraries, documents, extracted))
    failure_path = cache_dir / "failures.json"
    if failure_path.exists():
        failure_path.unlink()

    print(
        json.dumps(
            {
                "libraries": len(libraries),
                "documents": len(documents),
                "empty_bodies": sum(item.was_empty for item in extracted),
                "failures": 0,
                "llms_txt_bytes": links_path.stat().st_size,
                "llms_full_txt_bytes": full_path.stat().st_size,
                "llms_txt_sha256": sha256_file(links_path),
                "llms_full_txt_sha256": sha256_file(full_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
