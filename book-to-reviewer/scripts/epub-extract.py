#!/usr/bin/env python3
"""Extract an EPUB to greppable text + a figure index, in spine (reading) order.

Writes <books-dir>/<slug>.txt and <books-dir>/<slug>-figures/{images,figures.md}.
Standard library only. Uses macOS `textutil` when it is installed; otherwise
strips the HTML itself.

Every image a page shows leaves a marker in the text where it appeared:
[FIGURE: <file>] for a numbered figure or table, [IMAGE: <file> | <alt>] for
any other image. Unnumbered images are often equations or tables, so they are
copied out and indexed too.
"""
import argparse, html, os, re, shutil, subprocess, sys, tempfile, zipfile
from typing import NoReturn
import xml.etree.ElementTree as ET

OPF = '{http://www.idpf.org/2007/opf}'
CONTAINER = '{urn:oasis:names:tc:opendocument:xmlns:container}'
DEFAULT_BOOKS_DIR = '~/.agents/books'
IMAGE_SUFFIXES = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp')
BLOCK_END = re.compile(
    r'<br\s*/?>|</(?:p|div|h[1-6]|li|tr|blockquote|figcaption|section|title)>', re.I)
FIGURE_BLOCK = re.compile(
    r'<(?:figure\b|div[^>]*class="[^"]*(?:figure|image)[^"]*")[^>]*>.*?</(?:figure|div)>'
    r'(?:\s*<(?:p|div)[^>]*class="[^"]*(?:fig-?caption|caption)[^"]*"[^>]*>.*?</(?:p|div)>)?',
    re.S | re.I)
IMG_TAG = re.compile(r'<img\b[^>]*>', re.I)
IMG_SRC = re.compile(r'\bsrc\s*=\s*["\']([^"\']+)["\']', re.I)
IMG_ALT = re.compile(r'\balt\s*=\s*["\']([^"\']*)["\']', re.I)
# Figure numbering varies: "8-1" (O'Reilly) or "8.1" (Pearson). Some books
# (Evans) label a figure with no caption at all, so the separator is optional.
FIGURE_LABEL = re.compile(r'((?:Figure|Table)\s+\d+(?:[.-]\d+)*)\.?\s*')


def spine_files(root):
    """Content documents in reading order, per the OPF manifest + spine."""
    container = ET.parse(os.path.join(root, 'META-INF', 'container.xml'))
    rootfile = container.find(f'.//{CONTAINER}rootfile')
    rel = rootfile.get('full-path') if rootfile is not None else None
    if rel is None:
        raise ValueError('META-INF/container.xml names no package file')
    opf_dir = os.path.dirname(os.path.join(root, rel))
    opf = ET.parse(os.path.join(root, rel)).getroot()
    hrefs = {i.get('id'): i.get('href') for i in opf.iter(f'{OPF}item')}
    out = []
    for ref in opf.iter(f'{OPF}itemref'):
        href = hrefs.get(ref.get('idref'))
        if href:
            out.append(os.path.normpath(os.path.join(opf_dir, href)))
    return out


def one_line(text):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', ' ', text))).strip()


class ImageCatalog:
    """Gives every image a unique output name and remembers how it was used."""

    def __init__(self):
        self.output_names = {}
        self.figures = []
        self.inline_images = []

    def output_name(self, source_path):
        if source_path not in self.output_names:
            name = os.path.basename(source_path)
            taken = set(self.output_names.values())
            if name in taken:
                parent = os.path.basename(os.path.dirname(source_path))
                name = f'{parent}-{name}'
            while name in taken:
                name = f'_{name}'
            self.output_names[source_path] = name
        return self.output_names[source_path]

    def add_figure(self, source_path, number, caption):
        name = self.output_name(source_path)
        if all(figure['name'] != name for figure in self.figures):
            self.figures.append({'name': name, 'source': source_path,
                                 'number': number, 'caption': caption})
        return name

    def add_inline_image(self, source_path, alt_text, page):
        name = self.output_name(source_path)
        if all(image['name'] != name for image in self.inline_images):
            self.inline_images.append({'name': name, 'source': source_path,
                                       'alt': alt_text, 'page': page})
        return name


def image_source(tag, page_path):
    src = IMG_SRC.search(tag)
    if src is None:
        return None
    return os.path.normpath(os.path.join(os.path.dirname(page_path), html.unescape(src.group(1))))


def mark_images(markup, page_path, catalog):
    """Records figures and inline images, and replaces each <img> with a text
    marker so the converted text says where every picture was."""
    figure_sources = set()
    for block in FIGURE_BLOCK.findall(markup):
        tag = IMG_TAG.search(block)
        if tag is None:
            continue
        source_path = image_source(tag.group(0), page_path)
        if source_path is None:
            continue
        text = one_line(block)
        label = FIGURE_LABEL.match(text)
        if label is None:
            continue
        caption = text[len(label.group(1)):].lstrip('. ')
        catalog.add_figure(source_path, label.group(1), caption)
        figure_sources.add(source_path)

    def replace(match):
        tag = match.group(0)
        source_path = image_source(tag, page_path)
        if source_path is None:
            return ''
        if source_path in figure_sources:
            return f' [FIGURE: {catalog.output_name(source_path)}] '
        alt = IMG_ALT.search(tag)
        alt_text = one_line(alt.group(1)) if alt else ''
        name = catalog.add_inline_image(source_path, alt_text, os.path.basename(page_path))
        marker_alt = f' | {html.escape(alt_text)}' if alt_text else ''
        return f' [IMAGE: {name}{marker_alt}] '

    return IMG_TAG.sub(replace, markup)


def strip_html(markup):
    """Fallback converter: unwraps prose so greps match full sentences, and
    leaves <pre> blocks (code listings) with their line breaks intact."""
    markup = re.sub(r'<(script|style)\b.*?</\1>', '', markup, flags=re.S | re.I)
    pieces = []
    for piece in re.split(r'(<pre\b.*?</pre>)', markup, flags=re.S | re.I):
        if piece.lower().startswith('<pre'):
            pieces.append('\n\n' + piece + '\n\n')
        else:
            pieces.append(BLOCK_END.sub('\n\n', re.sub(r'\s+', ' ', piece)))
    text = html.unescape(re.sub(r'<[^>]*>', '', ''.join(pieces)))
    text = re.sub(r'[ \t]+\n', '\n', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip() + '\n'


def to_text(markup, page_path, use_textutil):
    """macOS textutil beats tag-stripping: no CSS leakage, no hard wrapping."""
    if use_textutil:
        marked_page = page_path + '.marked.xhtml'
        with open(marked_page, 'w', encoding='utf-8') as out:
            out.write(markup)
        result = subprocess.run(['textutil', '-convert', 'txt', '-stdout', marked_page],
                                capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
    return strip_html(markup)


def table_cell(text):
    return text.replace('|', '\\|')


def write_index(path, slug, catalog, copied):
    with open(path, 'w', encoding='utf-8') as index:
        index.write(f'# {slug} — extracted figures\n\n')
        index.write('Every image labelled as a numbered figure or table, with its '
                    'full caption. Nothing is filtered by size. The text marks where '
                    'each one appears with [FIGURE: <file>].\n\n')
        index.write('| File | Figure | Caption |\n|---|---|---|\n')
        for figure in catalog.figures:
            if figure['name'] in copied:
                index.write(f"| {figure['name']} | {figure['number']} | "
                            f"{table_cell(figure['caption'])} |\n")
        index.write('\n## Inline images\n\n')
        index.write('Images with no figure number: often equations, tables, photos '
                    'or icons. The text marks each one with [IMAGE: <file> | <alt>]; '
                    'open the file to see what it holds.\n\n')
        index.write('| File | Alt text | Page |\n|---|---|---|\n')
        for image in catalog.inline_images:
            if image['name'] in copied:
                index.write(f"| {image['name']} | {table_cell(image['alt'])} | "
                            f"{image['page']} |\n")


def copy_images(catalog, figure_dir):
    os.makedirs(figure_dir, exist_ok=True)
    copied = set()
    for entry in catalog.figures + catalog.inline_images:
        if entry['name'] in copied or not os.path.isfile(entry['source']):
            continue
        shutil.copy2(entry['source'], os.path.join(figure_dir, entry['name']))
        copied.add(entry['name'])
    return copied


def archive_image_count(root):
    return sum(1 for _, _, names in os.walk(root)
               for name in names if name.lower().endswith(IMAGE_SUFFIXES))


def parse_args():
    parser = argparse.ArgumentParser(
        description='Extract an EPUB to greppable text plus a figure index, in reading order.',
        epilog='Example: epub-extract.py book.epub pragmatic-programmer --books-dir ~/.agents/books')
    parser.add_argument('epub', help='path to the .epub file')
    parser.add_argument('slug', help='short name for the output files, e.g. pragmatic-programmer')
    parser.add_argument('--books-dir', default=DEFAULT_BOOKS_DIR,
                        help=f'directory to write into (default: {DEFAULT_BOOKS_DIR})')
    return parser.parse_args()


def fail(message) -> NoReturn:
    print(f'Error: {message}', file=sys.stderr)
    sys.exit(1)


def main():
    args = parse_args()
    if not os.path.isfile(args.epub):
        fail(f'no such file: {args.epub}')
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', args.slug):
        fail(f'slug must be lowercase letters, digits and hyphens, got: {args.slug}')
    use_textutil = shutil.which('textutil') is not None
    if not use_textutil:
        print('Note: textutil not found (macOS only); stripping HTML with the built-in '
              'fallback. Spot-check a chapter for stray markup.', file=sys.stderr)
    books = os.path.abspath(os.path.expanduser(args.books_dir))
    os.makedirs(books, exist_ok=True)
    catalog = ImageCatalog()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            with zipfile.ZipFile(args.epub) as archive:
                archive.extractall(tmp)
            pages = spine_files(tmp)
        except (zipfile.BadZipFile, ET.ParseError, OSError, ValueError) as error:
            fail(f'{args.epub} is not a readable EPUB ({error}). DRM-protected '
                 'files cannot be extracted.')
        in_archive = archive_image_count(tmp)
        text_path = os.path.join(books, f'{args.slug}.txt')
        with open(text_path, 'w', encoding='utf-8') as out:
            for page in pages:
                if not os.path.exists(page):
                    continue
                markup = open(page, encoding='utf-8', errors='replace').read()
                markup = mark_images(markup, page, catalog)
                out.write(f'\n\n[FILE: {os.path.basename(page)}]\n\n')
                out.write(to_text(markup, page, use_textutil))
        figure_dir = os.path.join(books, f'{args.slug}-figures')
        copied = copy_images(catalog, figure_dir)
        write_index(os.path.join(figure_dir, 'figures.md'), args.slug, catalog, copied)
    figures = sum(1 for figure in catalog.figures if figure['name'] in copied)
    inline = sum(1 for image in catalog.inline_images if image['name'] in copied)
    print(f'{text_path}: {os.path.getsize(text_path):,} bytes, {len(pages)} spine files')
    print(f'{figure_dir}: {figures} figures, {inline} inline images')
    print(f'images in the archive: {in_archive}; not shown on any page: '
          f'{max(in_archive - figures - inline, 0)} (usually the cover)')
    if inline:
        print(f'Note: {inline} inline images may hold equations or tables that are '
              'missing from the text. Open them; see figures.md.', file=sys.stderr)
    if in_archive > 0 and figures < (figures + inline) / 4:
        print('Warning: few images carry a figure number. This book probably does '
              'not mark up its figures the way the script expects; its figures are '
              'likely in the inline list.', file=sys.stderr)


if __name__ == '__main__':
    main()
