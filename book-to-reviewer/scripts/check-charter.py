#!/usr/bin/env python3
"""Check a finished reviewer against references/charter-template.md.

The required sections and their order come from the template's own headings,
so the template stays the one place that defines them. Checks:

- the frontmatter is present, `name` matches the file (or, for a SKILL.md, its
  directory), `description` is present, and no unquoted value contains ': ',
  which strict YAML parsers reject;
- every required section is present, in the template's order (extra sections
  are allowed anywhere);
- no template placeholder such as <slug> or <books> was left in.

Exit codes: 0 passes, 1 problems found, 2 bad arguments.
"""
import argparse, os, re, sys

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        '..', 'references', 'charter-template.md')
LEFTOVER_PLACEHOLDERS = re.compile(
    r'<(?:slug|books|Title|Author|lang|Concept name|Optional\.[^>]*)>')


def template_sections(template_text):
    """Returns [(heading pattern, required)] from the fenced charter block."""
    body = template_text.split('```markdown', 1)[1]
    lines = body.splitlines()
    sections = []
    for index, line in enumerate(lines):
        heading = re.match(r'## (.+)$', line)
        if heading is None:
            continue
        following = next((later.strip() for later in lines[index + 1:] if later.strip()), '')
        optional = following.startswith('<Optional.')
        sections.append((heading.group(1).strip(), not optional))
    return sections


def heading_regex(template_heading):
    """A <A | B> placeholder stands for the book's own word, so it matches any
    words: '<Chapter | Tip | Mistake> Index' matches '## Pattern Index'."""
    pattern = ''
    for piece in re.split(r'(<[^>]+>)', template_heading):
        if piece.startswith('<') and '|' in piece:
            pattern += r'.+?'
        else:
            pattern += re.escape(piece)
    return re.compile(r'^' + pattern + r'\s*$', re.I)


def charter_headings(lines):
    in_fence = False
    for number, line in enumerate(lines, 1):
        if line.lstrip().startswith('```'):
            in_fence = not in_fence
            continue
        if not in_fence:
            heading = re.match(r'## (.+)$', line)
            if heading:
                yield number, heading.group(1).strip()


def check_frontmatter(path, lines, problems, notes):
    if not lines or lines[0].strip() != '---':
        notes.append('no YAML frontmatter; skipped frontmatter checks '
                     '(fine for hosts whose agent format is not markdown)')
        return
    try:
        end = lines.index('---', 1)
    except ValueError:
        problems.append('frontmatter is never closed with ---')
        return
    fields = {}
    for number, line in enumerate(lines[1:end], 2):
        field = re.match(r'([A-Za-z_-]+):\s*(.*)$', line)
        if field is None:
            continue
        key, value = field.group(1), field.group(2)
        fields[key] = value
        if value and value[0] not in '"\'|>' and ': ' in value:
            problems.append(f"line {number}: unquoted '{key}' value contains ': ', "
                            'which strict YAML rejects; wrap the value in quotes')
    expected = os.path.splitext(os.path.basename(path))[0]
    if expected == 'SKILL':
        expected = os.path.basename(os.path.dirname(os.path.abspath(path)))
    name = fields.get('name', '').strip('"\'')
    if not name:
        problems.append('frontmatter has no name')
    elif name != expected:
        problems.append(f"name '{name}' does not match the file name '{expected}'")
    if not fields.get('description', '').strip('"\' '):
        problems.append('frontmatter has no description')


def check_sections(lines, template_text, problems):
    found = list(charter_headings(lines))
    last_position = -1
    last_heading = None
    for template_heading, required in template_sections(template_text):
        matcher = heading_regex(template_heading)
        positions = [position for position, (_, text) in enumerate(found) if matcher.match(text)]
        if not positions:
            if required:
                problems.append(f'missing required section: ## {template_heading}')
            continue
        position = positions[0]
        line_number, text = found[position]
        if position < last_position:
            problems.append(f"line {line_number}: '## {text}' should come after "
                            f"'## {last_heading}', as in the template")
        else:
            last_position, last_heading = position, text


def check_placeholders(lines, problems):
    in_fence = False
    for number, line in enumerate(lines, 1):
        if line.lstrip().startswith('```'):
            in_fence = not in_fence
            continue
        leftover = LEFTOVER_PLACEHOLDERS.search(line)
        if leftover and not in_fence:
            problems.append(f'line {number}: template placeholder left in: {leftover.group(0)}')


def main():
    parser = argparse.ArgumentParser(
        description='Check a reviewer file against the charter template.',
        epilog='Example: check-charter.py ~/.claude/agents/latency-reviewer.md')
    parser.add_argument('charter', help='the reviewer file to check')
    parser.add_argument('--template', default=TEMPLATE, help='the charter template (default: the bundled one)')
    args = parser.parse_args()
    try:
        lines = open(args.charter, encoding='utf-8').read().splitlines()
        template_text = open(args.template, encoding='utf-8').read()
    except OSError as error:
        print(f'Error: {error}', file=sys.stderr)
        sys.exit(2)

    problems, notes = [], []
    check_frontmatter(args.charter, lines, problems, notes)
    check_sections(lines, template_text, problems)
    check_placeholders(lines, problems)

    for note in notes:
        print(f'note     {note}')
    for problem in problems:
        print(f'PROBLEM  {problem}')
    print('passes' if not problems else f'{len(problems)} problems')
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
