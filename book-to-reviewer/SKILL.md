---
name: book-to-reviewer
description: Turn a book (PDF, EPUB, text, or a set of URLs) into a code-reviewer agent that reviews diffs strictly through that book's lens. Extracts the source text and diagrams, distills a charter from them, and writes the reviewer as a custom agent for the host you are running in. Use when asked to make a book reviewer, add a reviewer to a review panel, or turn a book into a review agent.
compatibility: Requires python3. PDF sources also need poppler (pdftotext, pdfimages). EPUB text is cleanest on macOS (textutil); elsewhere a built-in fallback is used. Works best in an agent that supports custom subagents; otherwise the reviewer is written as a skill.
---

# Build a book-lens reviewer

Produces one agent that reviews diffs **strictly through one book's lens**.
`references/charter-template.md` is the shape every reviewer follows; read it
before writing one.

Three artifacts per reviewer:

| Path | What |
|---|---|
| `<books>/<slug>.txt` | full source text, greppable |
| `<books>/<slug>-figures/` | extracted diagrams + `figures.md` index |
| the host's custom-agent file (step 5) | the agent |

`<books>` is the books directory: `~/.agents/books` by default. If the user
already keeps extracted books somewhere else, use that instead. Wherever a path
ends up in the charter, write it resolved and absolute, not as `<books>`.

All script paths below are relative to this skill's directory.

## Requirements

| Needed for | Tool | Notes |
|---|---|---|
| everything | `python3` | extraction and quote verification; standard library only |
| PDF sources | `pdftotext`, `pdfimages` | both ship in poppler |
| EPUB sources (optional) | `textutil` | macOS built-in; without it the script strips HTML itself |
| web corpus | a way to fetch URLs | the host's web-fetch tool, or `curl` |

**Check before doing any other work**, once you know the source type from
step 1:

```bash
sh scripts/check-deps.sh <epub|pdf|text|web>
```

It prints each tool as `ok` or `MISSING` with the install command for this
machine, and exits non-zero if a required one is missing. If anything is
missing, **show the user the install command and ask before running it** —
never install silently, and never work around a missing tool by reading the
book some other way. If they decline, stop and say what could not be done.

## 1. Ask for the book

**Always ask first — never assume which book, and never invent its content.**
Ask in one message:

- **Which book** — title and author.
- **Where is it?** A file path (PDF/EPUB/txt), or a set of URLs for a
  web corpus (an author whose position lives in essays or docs rather than
  one book), or "I don't have a copy."
- **What does it review?** Language/domain (Go, web, SQL, any) — this sets the
  agent's `description` and its scope fence.
- **Slug**, if they want something other than the obvious one.

If they have no copy: say plainly that a reviewer built without the text will
cite things that aren't in the book, and offer the web-corpus path instead
(a curated set of URLs the user picks, fetched and saved). Do not proceed from
memory of a book.

## 2. Extract the text

Target `<books>/<slug>.txt`. Keep structural markers — chapter and
section numbers are what makes the file greppable later.

**EPUB — use `scripts/epub-extract.py`.** It does text and figures in one pass:

```bash
python3 -I scripts/epub-extract.py "<input>.epub" <slug> --books-dir <books>
```

It reads the OPF manifest and emits chapters in **spine (reading) order**, not
`find | sort` order, so front matter and appendices land where they belong. On
macOS, text conversion goes through `textutil`, which gives the cleanest
result: no CSS leaking into the text, and **no hard line wrapping** — so later
greps match full sentences. Without `textutil` the script strips the HTML
itself and says so on stderr; the text is usable, but spot-check a chapter for
stray markup before distilling. Figures come from the archive's own image
files, paired with the caption in the same `<figure>` block, which makes the
index exact rather than inferred.

Every picture leaves a marker in the text where it appeared: `[FIGURE: <file>]`
for a numbered figure, `[IMAGE: <file> | <alt>]` for anything else. **Inline
images often hold equations or tables**, so that content is missing from the
text itself; the script copies them out and lists them under "Inline images" in
`figures.md`, and says how many there are. Open each one, and wherever an
equation carries an argument the charter will use, write it out in the
figures.md row (`L = λW`, Little's law) so the reviewer can cite it.

**PDF:**

```bash
pdftotext -layout "<input>.pdf" <books>/<slug>.txt
```

Note that `pdftotext` hard-wraps mid-sentence and splits hyphenated words with
`‐` (U+2010, not ASCII `-`). This matters downstream — see the grep-hygiene
note in step 5.

**Multi-document web corpus:** fetch each URL once and concatenate the results
into the one text file, each under its own `[SOURCE: <name>]` header line so a
citation can name the document it came from.

Then **verify**: `wc -c`, and grep for a chapter heading you expect. A PDF that
yields almost no text is image-only — say so and stop rather than building a
reviewer on an empty file.

### Pin the edition before distilling

**Confirm which edition you extracted, and record it in the charter.** A book
with a second edition is a trap: the structure and numbering shift, and what
you remember about the book is usually the edition you read, not the one on
disk. Check the copyright page (`head -60`, or grep for a Library of Congress
number, a copyright year, the bibliography's latest entry) and grep for a term
that exists in only one edition.

This is not pedantry about citations. Second editions exist because the authors
changed their minds, so the charter's *content* is wrong, not just its numbers:
Pragmatic Programmer's 2nd edition retracts its own first-edition explanation
of DRY ("we did a poor job... a tiny and fairly trivial part"), adds ETC as the
value underneath everything, demotes the Law of Demeter, and renumbers all 100
tips — a charter built on the 1999 text cites Tip 14 for Reversibility while
the book's Tip 14 is ETC.

So: state the edition in the charter's Source of Truth section, with a short
"edition hazard" note naming two or three concrete renumberings. For a book
with only one edition, record that, and point the hazard note at whatever else
a reader is likely to remember instead: the author's blog posts, talks, or an
early-access draft whose chapters were later renamed. Future readers
of the charter — including you — will otherwise cite from memory and be wrong.
If the user has the other edition on disk, replace the file rather than keeping
both; two texts under confusable names is how the wrong one gets grepped.

## 3. Extract the diagrams

Books argue with pictures — Ousterhout's module-depth diagrams, DDIA's fencing
token and dual-write figures. Pull them so the agent can point at them.

**EPUB:** `epub-extract.py` does this in step 2, and prints three numbers:
numbered figures, inline images, and images in the archive that no page shows.
**Read them before trusting the index.** It keeps every image a page shows and
filters nothing by size — small line diagrams are often the ones that matter
most.

The script recognizes a figure by its caption label ("Figure 4.2", "Figure
4-2"). A book that labels figures some other way, or not at all, comes out with
few numbered figures and a long inline list, and the script warns when that
happens. Then the inline list is where the figures are: open them, decide which
are figures, and write their numbers and captions into `figures.md` from the
text around each `[IMAGE: ...]` marker. Pragmatic Programmer's markup made an
older version of the script report 2 figures when the book had 21, including the
one diagram that states its definition of orthogonality better than its prose
does. A silent "2 figures" looks like a sparse book, not a bug.

**PDF:**

```bash
mkdir -p <books>/<slug>-figures
pdfimages -png -p "<input>.pdf" <books>/<slug>-figures/fig
find <books>/<slug>-figures -name '*.png' -size -2k -delete
```

The size filter only clears masks and one-pixel rules. Do not raise it: a
simple line diagram can be under 10 KB. Decide what is decorative by the caption
join below, not by file size.

The `-p` flag puts the **page number in the filename** (`fig-<page>-<n>.png`),
which is what makes the index buildable. Do not eyeball 110 images one by one —
match them programmatically: grep the text for `Figure N-N.` caption lines,
note the page each falls on, and join on page number. Spot-check a handful
visually (open the image file) to confirm the join is right, and mark any guess with
`~` so the charter knows not to cite it confidently. Figures that fail to match
are usually decorative; a figure the charter wants to cite but that has no file
should be cited **by number and page only, never by path**.

Write `<books>/<slug>-figures/figures.md` in the same shape the EPUB script
writes, adding a Page column after File for a PDF:

```markdown
| File | Figure | Caption |
|---|---|---|
| CH04_F02.png | Figure 4.2 | Deep vs shallow modules |
```

The figure-reading pass below adds a "What it shows / argues" column. Keep only
figures that carry an argument. Delete screenshots of code — the text already
has those.

### Then actually look at them

**A caption index is not enough.** Captions let you *locate* a figure; they do
not carry its argument. "Figure 2-5. Event-driven architecture" says nothing,
while the diagram's real claim is that a dashed boundary encloses every service
*and one shared database* — which is why that architecture is a single
architecture quantum. A charter written from captions alone will cite figures
for claims they do not make.

So add a figure-reading pass before distillation, fanned out the same way as
step 4 (one reader per chapter range, each opening the image files so it sees
the picture itself). The same reader can do a range's figures and then its
distillation in one go; seeing the pictures next to the prose helps. This needs a model that can read images; if yours cannot,
tell the user the figure pass was skipped and keep the caption-only index. Each
reader writes, per figure, 1–3 sentences on what the diagram **shows and argues**,
describing the visual encoding wherever it carries meaning: dashed vs solid
boundaries, arrow styles, what sits inside vs outside a boundary, shared vs
separate datastores, and what the figure is contrasting with. Tell them to flag
three things specially:

- **Legend figures** that define a visual vocabulary later figures depend on.
  Miss one and a whole chapter's diagrams become uninterpretable.
- **Sequences** showing progressive change, where the delta between consecutive
  figures is the argument.
- **Figures whose argument contradicts or qualifies what the caption implies.**

Write the result to `<books>/<slug>-figures/figures.md`, replacing the
caption-only index: same table plus a "What it shows / argues" column. Instruct
them to write "unclear from text" rather than guess — a known gap beats a
plausible fabrication.

For a heavily visual book this is not optional. Budget it like distillation.

If a figure is central to a principle, reference it from the charter's Core
Principles section by path, and cite it for what the *diagram* shows.

## 4. Read the book and distill

**This is the work.** Do not generate the charter from what you already know
about the book — derive every section from the extracted text, and spot-check
quotes against it as you go.

Read in passes:
1. **Table of contents** → the Chapter/Tip Index section (complete, not partial —
   it is what makes the agent able to jump to a section later).
2. **Each chapter in full** → Core Principles. Read the chapters, not just
   their openings and summaries: the book's actual reasoning — and the
   qualifications it puts on its own advice — lives in the body, and a charter
   built from summaries reads like a blurb.
3. **The book's own named anti-patterns** → Red Flags / Code Smells.
4. **Where the book argues against a common practice** → Characteristic
   Objections, and What This Book Does NOT Care About.
5. **The book's worked examples** → Calibration Examples, condensed to
   before/after pairs with the book's own verdict.

### Fanning out

A long book is worth splitting across parallel readers, if your host lets you
start subagents. **Every reader must be the same model at the same effort as
you** — otherwise chapters come back distilled at different depths and the
charter is silently uneven, with no way to tell which sections were read
carefully. Many hosts start subagents on a smaller default model, so set the
model explicitly or use whatever mechanism copies your own session.

In Claude Code that mechanism is the `Agent` tool with `subagent_type: "fork"`,
which inherits this session's context and always runs on this model; do not use
`general-purpose` or a named agent type for distillation there. If your host
has no subagents, or cannot guarantee the same model, read the chapters
yourself in sequence — slower, but even.

Give each reader a brief like this:

```
Read <books>/<slug>.txt chapters 4-6. Return Core Principles, Red Flags, and
Calibration candidates for those chapters only, with section numbers and
verbatim short quotes for anything you assert.
```

Spend tokens freely here — distillation quality is the whole product, and a
charter is written once and used for years. Prefer more passes and more readers
over a cheaper single pass: one reader per 2-4 chapters, each returning quotes
with section numbers rather than summaries, so you can verify rather than trust.

**You write the charter.** Readers return raw material; synthesis stays with you,
so the voice and the severity calibration are consistent across the whole file.

## 5. Write the agent

Use `references/charter-template.md` for the body. The body is the same
everywhere; only the wrapper and the location depend on the host you are
running in:

- **The host has custom agents (subagents).** Write the charter as one, in the
  host's own format and its user-level agents directory, named
  `<slug>-reviewer`. If you are not certain of the format, check the host's
  documentation rather than guessing — a file in the wrong place or shape is
  silently ignored. Give the agent read, search and shell access, plus the
  ability to start subagents if the host has it, and web fetch only for a web
  corpus.
- **Claude Code**, as the worked example: `~/.claude/agents/<slug>-reviewer.md`
  with this frontmatter.

  ```yaml
  ---
  name: <slug>-reviewer
  description: <one sentence: whose lens, what it reviews, when to use it>
  tools: Read, Glob, Grep, Bash, Agent
  ---
  ```

- **The host has no custom agents.** Write it as a skill instead:
  `<slug>-reviewer/SKILL.md` in the host's skills directory, with `name` and
  `description` frontmatter and the same body.

Tell the user which of these you chose and the path you wrote.

**The template is the one list of what a reviewer contains**, in a fixed order;
`scripts/check-charter.py` checks a finished reviewer against it (step 8).
Steps 6 and 7 explain why the less obvious sections exist. Three sections need
knowledge the template's placeholders cannot carry:

- **Source of Truth** is what stops fabricated citations. Its grep-hygiene note
  says what this text does to a search: a PDF is hard-wrapped mid-sentence and
  hyphenates with `‐` (U+2010); an EPUB has curly apostrophes, may hide soft
  hyphens (U+00AD) inside words, and puts each paragraph on one very long line.
  Either way, full-sentence greps fail even when the sentence is present — grep
  a distinctive 3–6 word fragment, then read around the hit (`sed -n 'N,Mp'`,
  or `grep -o` with a little context for long lines).
- **What This Book Does NOT Care About** is the scope fence. Without it the
  agent drifts into generic code review and the panel loses its point.
- **Calibration Examples** anchor severity, so it is judged rather than guessed.

## 6. Overlapping lenses are the point

Do **not** carve scope so each reviewer owns a disjoint territory. The panel's
value is several informed perspectives on the same code, so overlap is expected
and disagreement is a signal, not a defect to design away.

What this means concretely when writing a charter:

- **Let the book argue its own position in full**, including where it would
  conflict with another reviewer on the panel. Evans accepts more classes and
  more indirection for model fidelity than Ousterhout tolerates for cognitive
  load; both are right from their own premises, and the user wants to see both.
- **Record the premise, not just the conclusion.** Two reviewers flagging the
  same line for different reasons is a stronger signal than either alone — but
  only if each says *why*. "Rename this" from a cognitive-load argument and
  from a model-fidelity argument are different findings that happen to agree.
- **Where the book would visibly contradict another reviewer, say so in the
  charter** (the Tensions With Other Lenses section) and tell the agent to
  surface the tension rather than hedge toward the other lens. A charter that pre-concedes its disagreements produces a
  reviewer that adds nothing to the panel.
- The **scope fence still matters**, but it fences out concerns the book has no
  position on — not concerns another reviewer also happens to hold.

## 7. Why the rest of the template is there

A first-draft charter tends to fill in principles and red flags and skimp on
these. Each is a slot in the template; this is why it matters.

- **Cite figures.** Point at `<slug>-figures/figures.md` and let findings say
  "see Figure 4.2."
- **Say when the book is wrong, or silent.** *Known Limits*:
  where the book's advice is dated, contested, or doesn't address the codebase's
  situation. A reviewer that can say "the book doesn't cover this" is more useful
  than one that stretches.
- **Confidence on each finding.** Mark whether a finding is the book's explicit
  position or your extension of it. When several reviewers' findings are
  merged into one report, unmarked extrapolation is what makes the merged
  output untrustworthy.
- **No findings is a valid result.** Without saying so (How You Review), the
  agent will manufacture findings to seem useful. **Declined findings** — ones
  another panel reviewer might raise, with the premise for declining — go
  further. On a clean diff that is the whole value of the review.
- **Give it a way to say "this is right, and here is why."** A charter full of
  red flags can only report defects, so on a clean diff it falls silent and the
  review is worthless. Hence the passing calibration example, stated as an
  endorsement, and the Endorsements list in the output. The most common real-world
  diff shape is "someone extracted a helper and it was fine"; a reviewer that
  cannot say so has nothing to offer on most PRs.
- **Gate precedence.** If the charter has both a checklist of smells and a test
  for whether a finding qualifies, How You Review says which wins. Without it the table pulls the agent toward
  pattern-matching on shape — recommending virtualization for a list of
  twenty — and the gate never runs.
- **Establish the base before reviewing.** How You Review starts with it: review
  the PR head branch, not the working tree, and verify any claimed precondition
  against `origin/main` rather than the PR branch. A branch
  cut before a precondition landed looks identical to one whose precondition was
  never met — and that produces a confident, error-severity false positive about
  production breakage. This is the single highest-cost mistake a reviewer makes.

## 8. Verify before handing over

1. **Check the shape** with `scripts/check-charter.py`: frontmatter that
   strict YAML accepts, `name` matching the file, every required section
   present in the template's order, and no `<slug>`-style placeholder left in.

   ```bash
   python3 -I scripts/check-charter.py <agent-file>
   ```

   For a host whose agent format is not markdown with frontmatter, it skips the
   frontmatter checks and still checks the sections.
2. **Verify every quote the charter uses** with `scripts/verify-quotes.py`. A
   raw `grep` of a short fragment is not enough: it passes while the charter's
   longer rendering differs from the book. The script compares whole quotes
   while ignoring what typography does to them — line wrapping, soft hyphens,
   hyphen variants, straight vs curly and single vs double quotes, markdown
   emphasis — and checks each side of a `...` separately.

   ```bash
   python3 -I scripts/verify-quotes.py <agent-file> <books>/<slug>.txt \
     --skip-section "Characteristic Objections"
   ```

   Skip any section that quotes *what people say* rather than the book, or it
   floods the output with false misses. It prints each miss with its line
   number and exits non-zero if there are any.

   A sane run reports a handful of misses. Dozens means something mechanical is
   wrong — usually an unbalanced quote mark pairing your own prose into a
   "quote" — so read three before touching the charter. Then chase every real
   miss: some are a distiller's
   paraphrase presented as a quote, or two separate claims conflated into one
   sentence. Fix those; they are the fabricated citations the Source of Truth
   section exists to prevent, and they surface nowhere else. Finally, reserve
   double quotes for the book's own words — put your own descriptive phrases in
   italics, or the next reader cannot tell a citation from a gloss.
3. Run it once on a real diff and read the output: are citations real, is
   severity sane, did it stay in scope? Prefer a diff that touches the book's
   subject over a trivial one — a reviewer that correctly finds nothing in an
   unrelated diff has only proved its scope fence, not its lens. Ask the test
   run for feedback on the charter itself; applying it to real code surfaces
   ambiguities that writing it does not.
4. Tell the user: the three paths written, roughly what the charter covers, and
   what you verified. Check whether the new agent shows up in the host's agent
   list; some hosts only load new agents after a restart. If it is not there
   yet, exercise it by pointing a general-purpose agent at the charter file.
