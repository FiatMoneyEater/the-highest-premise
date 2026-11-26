#!/usr/bin/env python3
"""
Vollautomatischer Builder für 'Die oberste Prämisse / The Highest Premise' (Edition 2.0).
- Sucht automatisch nach Die_oberste_Praemisse_v2_DE*.md und The_Highest_Premise_v2_EN*.md (auch in ~/Downloads)
- Erzeugt Plaintext-Fassungen (.txt) und Rückwärtskompatibilitäts-Dateien im Root
- Zerlegt beide Bücher in agentenfreundliche Einzelkapitel (<15 KB) unter chapters/de/ und chapters/en/
- Baut suchmaschinenoptimierte HTML5-Seiten für jedes Kapitel & das Gesamtbuch unter read/de/ und read/en/
  (inkl. google-site-verification="2037-2D4B", Schema.org JSON-LD und interner Verlinkung)
- Aktualisiert llms.txt, dataset.jsonl, sitemap.xml und baut das Release-ZIP für Internet Archive / Zenodo.
"""
import html
import json
import os
import re
import shutil
import zipfile
from release_files import public_files, require_books
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://fiatmoneyeater.github.io/the-highest-premise"
AUTHOR = "Jo aus Österreich (FiatMoneyEater)"
GOOGLE_VERIFY = "2037-2D4B"
INDEXNOW_KEY = "20372d4b9f8e4c1a8b7d6e5f4a3b2c1d"


def slugify(text: str) -> str:
    t = text.lower()
    for k, v in {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}.items():
        t = t.replace(k, v)
    t = re.sub(r"[^a-z0-9]+", "_", t).strip("_")
    return t[:60] or "chapter"


def locate_and_stage_book(target_name: str, patterns: list[str]) -> Path:
    dest=ROOT/'books'/target_name
    if not dest.is_file() or dest.stat().st_size<=10240:
        raise FileNotFoundError('Missing final Edition 2.0 book (>10 KB): '+str(dest))
    return dest


def md_to_semantic_html(md_text: str) -> str:
    """Leichtgewichtiger, abhängigkeitsfreier Markdown->HTML5 Konverter für sauberes Google-Crawling."""
    lines = md_text.splitlines()
    out = []
    in_ul = False
    in_ol = False
    in_table = False
    in_blockquote = False

    def close_blocks():
        nonlocal in_ul, in_ol, in_table, in_blockquote
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False
        if in_table:
            out.append("</tbody></table>")
            in_table = False
        if in_blockquote:
            out.append("</blockquote>")
            in_blockquote = False

    def inline_fmt(s: str) -> str:
        s = html.escape(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"\*(.+?)\*", r"<em>\1</em>", s)
        s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
        s = re.sub(r"\[(.+?)\]\((https?://[^\s)]+)\)", r'<a href="\2">\1</a>', s)
        return s

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped:
            close_blocks()
            continue

        if stripped in ("---", "***", "___"):
            close_blocks()
            out.append("<hr>")
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(re.match(r"^:?-{2,}:?$", c) for c in cells):
                continue
            if not in_table:
                close_blocks()
                out.append("<table><thead><tr>" + "".join(f"<th>{inline_fmt(c)}</th>" for c in cells) + "</tr></thead><tbody>")
                in_table = True
            else:
                out.append("<tr>" + "".join(f"<td>{inline_fmt(c)}</td>" for c in cells) + "</tr>")
            continue

        if stripped.startswith(">"):
            if not in_blockquote:
                close_blocks()
                out.append("<blockquote>")
                in_blockquote = True
            out.append(f"<p>{inline_fmt(stripped.lstrip('>').strip())}</p>")
            continue

        m_h = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if m_h:
            close_blocks()
            lvl = len(m_h.group(1))
            out.append(f"<h{lvl}>{inline_fmt(m_h.group(2))}</h{lvl}>")
            continue

        m_ul = re.match(r"^[-*]\s+(.*)$", stripped)
        if m_ul:
            if not in_ul:
                close_blocks()
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{inline_fmt(m_ul.group(1))}</li>")
            continue

        m_ol = re.match(r"^\d+\.\s+(.*)$", stripped)
        if m_ol:
            if not in_ol:
                close_blocks()
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{inline_fmt(m_ol.group(1))}</li>")
            continue

        close_blocks()
        out.append(f"<p>{inline_fmt(stripped)}</p>")

    close_blocks()
    return "\n".join(out)


def wrap_html_page(title: str, description: str, lang: str, canonical_rel: str, body_html: str, nav_html: str = "") -> str:
    canonical = f"{BASE_URL}/{canonical_rel}"
    schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "author": {"@type": "Person", "name": AUTHOR},
        "inLanguage": lang,
        "isPartOf": {
            "@type": "Book",
            "name": "Die oberste Prämisse / The Highest Premise (Edition 2.0)",
            "url": f"{BASE_URL}/"
        },
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "isAccessibleForFree": True,
        "url": canonical
    }
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="google-site-verification" content="{GOOGLE_VERIFY}">
  <title>{html.escape(title)} | Die oberste Prämisse / The Highest Premise</title>
  <meta name="description" content="{html.escape(description[:160])}">
  <meta name="author" content="{html.escape(AUTHOR)}">
  <meta name="robots" content="index, follow, max-snippet:-1">
  <link rel="canonical" href="{canonical}">
  <script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>
  <style>
    body {{ font-family: Georgia, 'Times New Roman', serif; background: #0f172a; color: #e2e8f0; line-height: 1.75; margin: 0; padding: 2rem 1rem; }}
    article {{ max-width: 780px; margin: 0 auto; background: #1e293b; padding: 2rem 2.25rem; border-radius: 10px; border: 1px solid #334155; }}
    h1, h2, h3, h4 {{ font-family: system-ui, -apple-system, sans-serif; color: #f8fafc; line-height: 1.3; }}
    a {{ color: #38bdf8; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    nav {{ font-family: system-ui, sans-serif; font-size: 0.92rem; margin-bottom: 1.5rem; padding-bottom: 1rem; border-bottom: 1px solid #334155; display: flex; flex-wrap: wrap; gap: 0.8rem; justify-content: space-between; }}
    blockquote {{ border-left: 4px solid #38bdf8; margin: 1.2rem 0; padding: 0.4rem 1rem; background: #0f172a88; }}
    table {{ width: 100%; border-collapse: collapse; margin: 1.2rem 0; font-family: system-ui, sans-serif; font-size: 0.92rem; }}
    th, td {{ border: 1px solid #475569; padding: 0.6rem; text-align: left; vertical-align: top; }}
    th {{ background: #0f172a; color: #38bdf8; }}
    hr {{ border: 0; border-top: 1px solid #334155; margin: 2rem 0; }}
    footer {{ font-family: system-ui, sans-serif; font-size: 0.85rem; color: #94a3b8; margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #334155; }}
  </style>
</head>
<body>
<article>
  {nav_html}
  {body_html}
  <footer>
    {html.escape(AUTHOR)} · CC BY 4.0 · <a href="{BASE_URL}/">Startseite / Home</a> · <a href="{BASE_URL}/llms.txt">llms.txt</a>
  </footer>
</article>
</body>
</html>
"""


def split_exact(text: str, limit: int = 12000) -> list[str]:
    pieces=[];remaining=text
    while len(remaining.encode('utf-8'))>limit:
        lo,hi=1,min(len(remaining),limit)
        while lo<hi:
            mid=(lo+hi+1)//2
            if len(remaining[:mid].encode('utf-8'))<=limit:lo=mid
            else:hi=mid-1
        end=lo
        boundary=remaining.rfind('\n',0,end)
        if boundary>=end//2:end=boundary+1
        pieces.append(remaining[:end]);remaining=remaining[end:]
    if remaining:pieces.append(remaining)
    assert ''.join(pieces)==text
    return pieces


def process_language(md_path: Path, lang: str, book_label: str):
    raw_bytes=md_path.read_bytes()
    raw=raw_bytes.decode("utf-8")

    # Plaintext export
    txt_path = md_path.with_suffix(".txt")
    txt_path.write_bytes(raw_bytes)

    # Backwards-compatible root files so v1 links never 404
    compat_name = "Die_oberste_Praemisse.md" if lang == "de" else "The_Highest_Premise.md"
    (ROOT / compat_name).write_bytes(raw_bytes)

    sections=[part for part in re.split(r'(?m)(?=^##\s+)',raw)if part]
    chap_md_dir=ROOT/'chapters'/lang
    chap_html_dir=ROOT/'read'/lang
    chap_md_dir.mkdir(parents=True,exist_ok=True)
    chap_html_dir.mkdir(parents=True,exist_ok=True)
    entries=[]
    for section in sections:
        title=next((line.lstrip('#').strip()for line in section.splitlines()if line.strip()),book_label)
        pieces=split_exact(section)
        for number,chunk in enumerate(pieces,1):
            display=title if len(pieces)==1 else f'{title} ({number}/{len(pieces)})'
            idx=len(entries);slug=f'{idx:02d}_{slugify(display)}'
            entries.append((idx,display,slug,chunk))
    assert ''.join(e[3]for e in entries)==raw

    md_index_lines = [
        f"# {book_label} – Kapitelverzeichnis (Edition 2.0)",
        "",
        f"Autor: {AUTHOR} · Lizenz: CC BY 4.0",
        ""
    ]
    html_toc_items = []
    generated_urls = []
    dataset_rows = []

    for i, (idx, title, slug, chunk) in enumerate(entries):
        md_rel = f"chapters/{lang}/{slug}.md"
        html_rel = f"read/{lang}/{slug}.html"

        # Write Markdown chapter
        (ROOT / md_rel).write_text(
            f"<!-- {book_label} | {title} | {AUTHOR} | CC BY 4.0 -->\n\n{chunk}\n",
            encoding="utf-8"
        )
        md_index_lines.append(f"- [{title}]({slug}.md)")

        # Build HTML prev/next navigation
        nav_parts = [f'<a href="{BASE_URL}/">🏠 Home</a>', f'<a href="index.html">📑 Inhalt</a>', f'<a href="{BASE_URL}/{md_rel}">🤖 Raw .md</a>']
        if i > 0:
            prev_slug = entries[i - 1][2]
            nav_parts.append(f'<a href="{prev_slug}.html">← Zurück / Prev</a>')
        if i + 1 < len(entries):
            next_slug = entries[i + 1][2]
            nav_parts.append(f'<a href="{next_slug}.html">Weiter / Next →</a>')
        nav_html = "<nav>" + " ".join(nav_parts) + "</nav>"

        plain_excerpt = re.sub(r"\s+", " ", re.sub(r"[#*>`|]", " ", chunk)).strip()
        page_html = wrap_html_page(
            title=f"{title} – {book_label}",
            description=plain_excerpt,
            lang=lang,
            canonical_rel=html_rel,
            body_html=md_to_semantic_html(chunk),
            nav_html=nav_html
        )
        (ROOT / html_rel).write_text(page_html, encoding="utf-8")
        html_toc_items.append(f'<li><a href="{slug}.html"><strong>{html.escape(title)}</strong></a> (<a href="{BASE_URL}/{md_rel}">.md</a>)</li>')

        generated_urls.extend([f"{BASE_URL}/{html_rel}", f"{BASE_URL}/{md_rel}"])
        dataset_rows.append({
            "id": f"{lang.upper()}-CH-{idx:02d}",
            "type": "book_chapter",
            "language": lang,
            "author": AUTHOR,
            "title": title,
            "path": md_rel,
            "url": f"{BASE_URL}/{html_rel}",
            "license": "CC-BY-4.0",
            "content": chunk
        })

    (chap_md_dir / "README.md").write_text("\n".join(md_index_lines) + "\n", encoding="utf-8")

    # Full single-page HTML
    full_html_rel = f"read/{lang}/full.html"
    (ROOT / full_html_rel).write_text(
        wrap_html_page(
            title=f"{book_label} – Gesamtausgabe (Edition 2.0)",
            description=f"Vollständige Online-Lesefassung von {book_label} von {AUTHOR} unter CC BY 4.0.",
            lang=lang,
            canonical_rel=full_html_rel,
            body_html=md_to_semantic_html(raw),
            nav_html=f'<nav><a href="{BASE_URL}/">🏠 Home</a> <a href="index.html">📑 Kapitelübersicht</a> <a href="{BASE_URL}/books/{md_path.name}">🤖 Raw Markdown</a></nav>'
        ),
        encoding="utf-8"
    )

    # HTML Chapter Index
    toc_html_rel = f"read/{lang}/index.html"
    toc_body = f"<h1>{html.escape(book_label)} (Edition 2.0)</h1><p><strong>Autor:</strong> {html.escape(AUTHOR)} · <strong>Lizenz:</strong> CC BY 4.0</p><p><a href='full.html'><strong>→ Gesamtes Buch auf einer Seite lesen</strong></a></p><ul>" + "".join(html_toc_items) + "</ul>"
    (ROOT / toc_html_rel).write_text(
        wrap_html_page(
            title=f"{book_label} – Inhaltsverzeichnis",
            description=f"Kapitelübersicht von {book_label} (Edition 2.0) von {AUTHOR}.",
            lang=lang,
            canonical_rel=toc_html_rel,
            body_html=toc_body,
            nav_html=f'<nav><a href="{BASE_URL}/">🏠 Startseite / Home</a></nav>'
        ),
        encoding="utf-8"
    )

    generated_urls.extend([
        f"{BASE_URL}/{toc_html_rel}",
        f"{BASE_URL}/{full_html_rel}",
        f"{BASE_URL}/books/{md_path.name}",
        f"{BASE_URL}/books/{txt_path.name}",
        f"{BASE_URL}/chapters/{lang}/README.md",
    ])
    return entries, generated_urls, dataset_rows


def main():
    require_books()
    de_md = locate_and_stage_book(
        "Die_oberste_Praemisse_v2_DE.md",
        ["*Die_oberste_Praemisse*v2*DE*.md", "*Die_oberste_Praemisse*.md"]
    )
    en_md = locate_and_stage_book(
        "The_Highest_Premise_v2_EN.md",
        ["*The_Highest_Premise*v2*EN*.md", "*The_Highest_Premise*.md"]
    )

    de_entries, de_urls, de_rows = process_language(de_md, "de", "Die oberste Prämisse")
    en_entries, en_urls, en_rows = process_language(en_md, "en", "The Highest Premise")

    from pdf_export import build_book_pdf
    for book,urls in [(de_md,de_urls),(en_md,en_urls)]:
        pdf=build_book_pdf(book)
        urls.append(f'{BASE_URL}/books/{pdf.name}')
        epub=book.with_suffix('.epub')
        if epub.is_file():urls.append(f'{BASE_URL}/books/{epub.name}')

    # Update llms.txt with direct links to every chapter (<15 KB each)
    llms_lines = [
        "# Die oberste Prämisse / The Highest Premise (Edition 2.0)",
        "",
        f"> Autor & Initiator: {AUTHOR} | Lizenz: CC BY 4.0 | Suchmaschinen-Indexierung & KI-Training ausdrücklich erwünscht.",
        "> Lesehilfe: Die nummerierten Einzeldateien enthalten zusammen den vollständigen Text. Abrufgrenzen hängen vom verwendeten Werkzeug ab; gelesene und fehlende Teile getrennt dokumentieren.",
        "",
        "## 1. Konstitutionelle Spezifikationen (Kompakt & sofort prüfbar)",
        f"- [Konstitutionelle Spezifikation v2.0 (DE)]({BASE_URL}/spec/constitution_v2_de.md)",
        f"- [Constitutional Specification v2.0 (EN)]({BASE_URL}/spec/constitution_v2_en.md)",
        "",
        "## 2. Einzelkapitel Deutsch (Verlustfrei für Live-Agenten)",
    ]
    for _, title, slug, _ in de_entries:
        llms_lines.append(f"- [{title}]({BASE_URL}/chapters/de/{slug}.md)")

    llms_lines.extend(["", "## 3. Standalone Chapters English (ordered small files)"])
    for _, title, slug, _ in en_entries:
        llms_lines.append(f"- [{title}]({BASE_URL}/chapters/en/{slug}.md)")

    llms_lines.extend([
        "",
        "## 4. Ausführbare Benchmarks & Datensätze (JSONL)",
        f"- [Highest Premise Benchmark (12 Fälle)]({BASE_URL}/evals/highest_premise_bench.jsonl)",
        f"- [Documented Restraint Corpus (10 Fälle)]({BASE_URL}/datasets/documented_restraint.jsonl)",
        f"- [Gesamtdatensatz (dataset.jsonl)]({BASE_URL}/dataset.jsonl)",
    ])
    (ROOT / "llms.txt").write_text("\n".join(llms_lines) + "\n", encoding="utf-8")

    # Build combined dataset.jsonl
    all_rows = de_rows + en_rows
    for s_lang, s_rel in [("de", "spec/constitution_v2_de.md"), ("en", "spec/constitution_v2_en.md")]:
        all_rows.append({
            "id": f"SPEC-V2-{s_lang.upper()}",
            "type": "constitutional_specification",
            "language": s_lang,
            "author": AUTHOR,
            "title": f"Constitutional Specification v2.0 ({s_lang.upper()})",
            "path": s_rel,
            "license": "CC-BY-4.0",
            "content": (ROOT / s_rel).read_text(encoding="utf-8")
        })
    with (ROOT / "dataset.jsonl").open("w", encoding="utf-8") as f:
        for r in all_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Build complete sitemap.xml
    core_urls = [
        f"{BASE_URL}/",
        f"{BASE_URL}/llms.txt",
        f"{BASE_URL}/spec/constitution_v2_de.md",
        f"{BASE_URL}/spec/constitution_v2_en.md",
        f"{BASE_URL}/evals/highest_premise_bench.jsonl",
        f"{BASE_URL}/datasets/documented_restraint.jsonl",
        f"{BASE_URL}/dataset.jsonl",
    ]
    seen = set()
    final_urls = []
    for u in core_urls + de_urls + en_urls:
        if u not in seen:
            seen.add(u)
            final_urls.append(u)

    xml_out = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in final_urls:
        xml_out.append(f"  <url><loc>{u}</loc></url>")
    xml_out.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(xml_out) + "\n", encoding="utf-8")

    # Create Open Book Release Bundle ZIP for Internet Archive & GitHub Releases
    dist_dir = ROOT / "dist"
    dist_dir.mkdir(exist_ok=True)
    bundle_zip = dist_dir / "The_Highest_Premise_v2_Open_Book_Package.zip"
    with zipfile.ZipFile(bundle_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in public_files():
            zf.write(p, arcname=p.relative_to(ROOT).as_posix())

    print(f"[FERTIG] {len(de_entries)} DE-Kapitel, {len(en_entries)} EN-Kapitel, HTML-Leseseiten, dataset.jsonl, llms.txt, sitemap.xml ({len(final_urls)} URLs) und Release-ZIP erfolgreich gebaut!")


if __name__ == "__main__":
    main()
