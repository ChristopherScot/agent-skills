#!/usr/bin/env python3
"""Extract an EPUB to greppable text + a figure index, in spine (reading) order.

Usage: epub-extract.py <book.epub> <slug>
Writes ~/.claude/books/<slug>.txt and ~/.claude/books/<slug>-figures/{*.png,figures.md}
"""
import os, re, shutil, subprocess, sys, tempfile, zipfile
import xml.etree.ElementTree as ET

OPF = '{http://www.idpf.org/2007/opf}'
CONTAINER = '{urn:oasis:names:tc:opendocument:xmlns:container}'


def spine_files(root):
    """Content documents in reading order, per the OPF manifest + spine."""
    container = ET.parse(os.path.join(root, 'META-INF', 'container.xml'))
    rel = container.find(f'.//{CONTAINER}rootfile').get('full-path')
    opf_dir = os.path.dirname(os.path.join(root, rel))
    opf = ET.parse(os.path.join(root, rel)).getroot()
    hrefs = {i.get('id'): i.get('href') for i in opf.iter(f'{OPF}item')}
    out = []
    for ref in opf.iter(f'{OPF}itemref'):
        href = hrefs.get(ref.get('idref'))
        if href:
            out.append(os.path.normpath(os.path.join(opf_dir, href)))
    return out


def to_text(path):
    """macOS textutil beats tag-stripping: no CSS leakage, no hard wrapping."""
    r = subprocess.run(['textutil', '-convert', 'txt', '-stdout', path],
                       capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout
    html = open(path, encoding='utf-8', errors='replace').read()
    html = re.sub(r'<(script|style)\b.*?</\1>', '', html, flags=re.S | re.I)
    return re.sub(r'<[^>]*>', '', html)


def figures(files, outdir):
    """Pair each <img> with its caption. Handles two common EPUB layouts:
    O'Reilly (caption inside the figure block) and Pearson (caption in a
    sibling <p class="fig-caption"> right after a <div class="image">)."""
    BLOCK = re.compile(
        r'<(?:figure\b|div[^>]*class="[^"]*(?:figure|image)[^"]*")[^>]*>.*?</(?:figure|div)>'
        r'(?:\s*<(?:p|div)[^>]*class="[^"]*(?:fig-?caption|caption)[^"]*"[^>]*>.*?</(?:p|div)>)?',
        re.S | re.I)
    # Figure numbering varies: "8-1" (O'Reilly) or "8.1" (Pearson). Match the
    # whole number, then strip only a trailing caption separator.
    # Figure numbering varies: "8-1" (O'Reilly) or "8.1" (Pearson). Some books
    # (Evans) label a figure with no caption at all, so the separator is optional.
    LABEL = re.compile(r'((?:Figure|Table)\s+\d+(?:[.-]\d+)*)\.?\s*')
    rows = []
    for f in files:
        try:
            html = open(f, encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        for block in BLOCK.findall(html):
            src = re.search(r'<img[^>]*src="([^"]+)"', block, re.I)
            if not src:
                continue
            text = re.sub(r'<[^>]*>', ' ', block)
            text = re.sub(r'\s+', ' ', text).strip()
            label = LABEL.match(text)
            rows.append({
                'src': os.path.normpath(os.path.join(os.path.dirname(f), src.group(1))),
                'num': label.group(1) if label else '',
                'cap': text[len(label.group(1)):].lstrip('. ') if label else text,
            })
    os.makedirs(outdir, exist_ok=True)
    seen, kept = set(), []
    for r in rows:
        name = os.path.basename(r['src'])
        if name in seen or not os.path.exists(r['src']):
            continue
        if os.path.getsize(r['src']) < 15_000:   # decorative/fragment
            continue
        shutil.copy2(r['src'], os.path.join(outdir, name))
        seen.add(name)
        kept.append((name, r['num'], r['cap'][:160]))
    return kept


def main():
    epub, slug = sys.argv[1], sys.argv[2]
    books = os.path.expanduser('~/.claude/books')
    os.makedirs(books, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(epub) as z:
            z.extractall(tmp)
        files = spine_files(tmp)
        txt = os.path.join(books, f'{slug}.txt')
        with open(txt, 'w', encoding='utf-8') as out:
            for f in files:
                if os.path.exists(f):
                    out.write(f'\n\n[FILE: {os.path.basename(f)}]\n\n')
                    out.write(to_text(f))
        figdir = os.path.join(books, f'{slug}-figures')
        kept = figures(files, figdir)
        with open(os.path.join(figdir, 'figures.md'), 'w', encoding='utf-8') as idx:
            idx.write(f'# {slug} — extracted figures\n\n')
            idx.write('Captions are read from each figure block, so they are exact.\n\n')
            idx.write('| File | Figure | Caption |\n|---|---|---|\n')
            for name, num, cap in kept:
                idx.write(f'| {name} | {num} | {cap} |\n')
    print(f'{txt}: {os.path.getsize(txt):,} bytes, {len(files)} spine files')
    print(f'{figdir}: {len(kept)} figures')


if __name__ == '__main__':
    main()
