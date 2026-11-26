#!/usr/bin/env python3
"""Check that every double-quoted passage in a charter appears in the book text.

Matching ignores line wrapping, soft hyphens, Unicode hyphen variants, the
difference between single, double and curly quotes, markdown emphasis and
non-breaking spaces, so a quote copied correctly is never reported
missing because of typography. Quotes are paired within one paragraph only,
and code blocks are skipped.

Exit codes: 0 every quote found, 1 some quotes missing, 2 bad arguments.
"""
import argparse, re, sys

MIN_QUOTE_LENGTH = 12
MIN_FRAGMENT_LENGTH = 8
QUOTE = re.compile(r'["\u201c]([^"\u201c\u201d]+)["\u201d]')
ELLIPSIS = re.compile(r'\s*(?:\.\.\.|\u2026)\s*')
TYPOGRAPHY = str.maketrans({
    '\u00ad': None, '*': None, '`': None,
    '\u2010': '-', '\u2011': '-', '\u2012': '-',
    '\u2018': "'", '\u2019': "'", '\u201a': "'", '\u201b': "'",
    '\u201c': "'", '\u201d': "'", '\u201e': "'", '"': "'",
    '\u00a0': ' ', '\u202f': ' ', '\u2009': ' ',
})


def normalize(text):
    return re.sub(r'\s+', ' ', text.translate(TYPOGRAPHY)).strip()


def paragraphs(charter_lines, skipped_sections):
    """Yields (first line number, paragraph text), skipping code fences and
    any section whose heading contains one of skipped_sections."""
    in_fence = False
    skip_level = None
    current, start = [], 0
    for number, line in enumerate(charter_lines, 1):
        if line.lstrip().startswith('```'):
            in_fence = not in_fence
            if current:
                yield start, ' '.join(current)
                current = []
            continue
        if in_fence:
            continue
        heading = re.match(r'(#+)\s+(.*)', line)
        if heading:
            if current:
                yield start, ' '.join(current)
                current = []
            level = len(heading.group(1))
            if skip_level is not None and level <= skip_level:
                skip_level = None
            title = heading.group(2).lower()
            if skip_level is None and any(name.lower() in title for name in skipped_sections):
                skip_level = level
            continue
        if skip_level is not None:
            continue
        if line.strip():
            if not current:
                start = number
            current.append(re.sub(r'^(?:>\s?)+', '', line.strip()))
        elif current:
            yield start, ' '.join(current)
            current = []
    if current:
        yield start, ' '.join(current)


def fragments(quote):
    pieces = [piece.strip(' .,;:') for piece in ELLIPSIS.split(normalize(quote))]
    return [piece for piece in pieces if len(piece) >= MIN_FRAGMENT_LENGTH]


def main():
    parser = argparse.ArgumentParser(
        description='Report charter quotes that cannot be found in the book text.',
        epilog='Example: verify-quotes.py ~/.claude/agents/x-reviewer.md '
               '~/.agents/books/x.txt --skip-section "Characteristic Objections"')
    parser.add_argument('charter', help='the reviewer file to check')
    parser.add_argument('book', help='the extracted book text')
    parser.add_argument('--skip-section', action='append', default=[], metavar='HEADING',
                        help='skip sections whose heading contains this text; repeatable. '
                             'Use for sections that quote what people say, not the book.')
    args = parser.parse_args()
    try:
        charter_lines = open(args.charter, encoding='utf-8').read().splitlines()
        book = normalize(open(args.book, encoding='utf-8', errors='replace').read())
    except OSError as error:
        print(f'Error: {error}', file=sys.stderr)
        sys.exit(2)

    checked, missing = 0, []
    for line_number, paragraph in paragraphs(charter_lines, args.skip_section):
        for match in QUOTE.finditer(paragraph):
            quote = match.group(1)
            if len(quote) < MIN_QUOTE_LENGTH:
                continue
            pieces = fragments(quote)
            if not pieces:
                continue
            checked += 1
            if any(piece not in book for piece in pieces):
                missing.append((line_number, quote))

    for line_number, quote in missing:
        print(f'MISSING  line {line_number}: "{quote}"')
    print(f'{checked} quotes checked, {len(missing)} missing')
    sys.exit(1 if missing else 0)


if __name__ == '__main__':
    main()
