---
name: book-reviewer
description: Build a new book-lens code-reviewer agent from a book (PDF, EPUB, text, or a set of URLs). Extracts the source to ~/.claude/books/, pulls out the diagrams, distills a charter, and writes ~/.claude/agents/<slug>-reviewer.md. Use when asked to make a book reviewer, add a reviewer to the panel, or turn a book into a review agent.
user_invocable: true
---

# Build a book-lens reviewer

Produces one agent that reviews diffs **strictly through one book's lens**. The
existing panel (`pragmatic-programmer-reviewer`,
`philosophy-of-software-design-reviewer`, `100-go-mistakes-reviewer`,
`go-idioms-reviewer`, `htmx-carson-reviewer`) is the reference; read one before
writing a new one.

Three artifacts per reviewer:

| Path | What |
|---|---|
| `~/.claude/books/<slug>.txt` | full source text, greppable |
| `~/.claude/books/<slug>-figures/` | extracted diagrams + `figures.md` index |
| `~/.claude/agents/<slug>-reviewer.md` | the agent |

## 1. Ask for the book

**Always ask first — never assume which book, and never invent its content.**
Ask in one message:

- **Which book** — title and author.
- **Where is it?** A file path (PDF/EPUB/txt), or a set of URLs for a
  web corpus (the `htmx-carson` case), or "I don't have a copy."
- **What does it review?** Language/domain (Go, web, SQL, any) — this sets the
  agent's `description` and its scope fence.
- **Slug**, if they want something other than the obvious one.

If they have no copy: say plainly that a reviewer built without the text will
cite things that aren't in the book, and offer the web-corpus path instead
(curated URLs via WebFetch, like `htmx-carson-reviewer`). Do not proceed from
memory of a book.

## 2. Extract the text

Target `~/.claude/books/<slug>.txt`. Keep structural markers — chapter and
section numbers are what makes the file greppable later.

**EPUB — use `scripts/epub-extract.py`.** It does text and figures in one pass:

```bash
python3 -I scripts/epub-extract.py "<input>.epub" <slug>
```

It reads the OPF manifest and emits chapters in **spine (reading) order**, not
`find | sort` order, so front matter and appendices land where they belong. Text
conversion goes through macOS `textutil`, which beats tag-stripping twice over:
no CSS leaking into the text, and **no hard line wrapping** — so later greps
match full sentences. Figures come from the archive's own image files, paired
with the caption in the same `<figure>` block, which makes the index exact
rather than inferred.

**PDF:**

```bash
pdftotext -layout "<input>.pdf" ~/.claude/books/<slug>.txt
```

Note that `pdftotext` hard-wraps mid-sentence and splits hyphenated words with
`‐` (U+2010, not ASCII `-`). This matters downstream — see the grep-hygiene
note in step 5.

**Multi-document web corpus:** one WebFetch per URL, concatenated under
`[SOURCE: <name>]` headers (see `go-official-corpus.txt` for the shape).

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
"edition hazard" note naming two or three concrete renumberings. Future readers
of the charter — including you — will otherwise cite from memory and be wrong.
If the user has the other edition on disk, replace the file rather than keeping
both; two texts under confusable names is how the wrong one gets grepped.

## 3. Extract the diagrams

Books argue with pictures — Ousterhout's module-depth diagrams, DDIA's fencing
token and dual-write figures. Pull them so the agent can point at them.

**EPUB:** `epub-extract.py` does this in step 2 — but **check its figure count
against the archive before trusting it.** The script pairs images with captions
by markup structure, so a book that stores images in a flat `images/` directory
with no `<figure>` wrapper yields almost nothing:

```bash
unzip -l "<input>.epub" | grep -cE '\.(png|jpg|jpeg|gif|svg)$'
```

If that count is far above what the script reported, copy them out by hand,
delete the noise (`find -size -8k -delete`, then the cover, author photos,
logos, rules), and write `figures.md` yourself. Pragmatic Programmer reported 2
figures and actually had 21, including the one diagram that states the book's
definition of orthogonality better than its prose does. A silent "2 figures"
looks like a sparse book, not a bug.

**PDF:**

```bash
mkdir -p ~/.claude/books/<slug>-figures
pdfimages -png -p "<input>.pdf" ~/.claude/books/<slug>-figures/fig
find ~/.claude/books/<slug>-figures -name '*.png' -size -15k -delete
```

The `-p` flag puts the **page number in the filename** (`fig-<page>-<n>.png`),
which is what makes the index buildable. Do not eyeball 110 images one by one —
match them programmatically: grep the text for `Figure N-N.` caption lines,
note the page each falls on, and join on page number. Spot-check a handful
visually (Read the image) to confirm the join is right, and mark any guess with
`~` so the charter knows not to cite it confidently. Figures that fail to match
are usually decorative; a figure the charter wants to cite but that has no file
should be cited **by number and page only, never by path**.

Write `~/.claude/books/<slug>-figures/figures.md`:

```markdown
| File | Page | Figure | What it shows |
|---|---|---|---|
| fig-012-000.png | 12 | 4.2 | Deep vs shallow modules: interface width over implementation |
```

Keep only figures that carry an argument. Delete screenshots of code — the text
already has those.

### Then actually look at them

**A caption index is not enough.** Captions let you *locate* a figure; they do
not carry its argument. "Figure 2-5. Event-driven architecture" says nothing,
while the diagram's real claim is that a dashed boundary encloses every service
*and one shared database* — which is why that architecture is a single
architecture quantum. A charter written from captions alone will cite figures
for claims they do not make.

So add a figure-reading pass before distillation, fanned out the same way (one
fork per chapter range, reading images with `Read`, which renders them). Each
fork writes, per figure, 1–3 sentences on what the diagram **shows and argues**,
describing the visual encoding wherever it carries meaning: dashed vs solid
boundaries, arrow styles, what sits inside vs outside a boundary, shared vs
separate datastores, and what the figure is contrasting with. Tell them to flag
three things specially:

- **Legend figures** that define a visual vocabulary later figures depend on.
  Miss one and a whole chapter's diagrams become uninterpretable.
- **Sequences** showing progressive change, where the delta between consecutive
  figures is the argument.
- **Figures whose argument contradicts or qualifies what the caption implies.**

Write the result to `~/.claude/books/<slug>-figures/figures.md`, replacing the
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

A long book is worth splitting across parallel readers. **Every reader must be
the same model at the same effort as you** — otherwise chapters come back
distilled at different depths and the charter is silently uneven, with no way to
tell which sections were read carefully.

So fan out with `Agent`, `subagent_type: "fork"` — a fork inherits this
session's full context and always runs on this model; a `model` override is
ignored. Never use `general-purpose` or a named agent type for distillation:
those start fresh on the default subagent model, which is the inconsistency this
rule exists to prevent.

```
Agent(subagent_type: "fork", description: "Distill ch. 4-6",
      prompt: "Read ~/.claude/books/<slug>.txt chapters 4-6 ... return
               Core Principles, Red Flags, and Calibration candidates
               for those chapters only, with section numbers and
               verbatim short quotes for anything you assert.")
```

Spend tokens freely here — distillation quality is the whole product, and a
charter is written once and used for years. Prefer more passes and more readers
over a cheaper single pass: one fork per 2-4 chapters, each returning quotes
with section numbers rather than summaries, so you can verify rather than trust.

**You write the charter.** Forks return raw material; synthesis stays with you,
so the voice and the severity calibration are consistent across the whole file.

## 5. Write the agent

Use `references/charter-template.md`. Frontmatter:

```yaml
---
name: <slug>-reviewer
description: <one sentence: whose lens, what it reviews, when to use it>
tools: Read, Glob, Grep, Bash, Agent
---
```

Add `WebFetch` to `tools` only for a web corpus. The `Agent` tool is in every
existing reviewer and lets it delegate deeper reads.

**Non-negotiable sections** (every existing reviewer has these, and each one
prevents a specific failure):

- **Source of Truth** — the book path, plus: *grep/read before quoting; never
  attribute to the book something you cannot locate in it; quote short phrases,
  never paragraphs.* This is what stops fabricated citations. For a
  PDF-sourced book, add a **grep-hygiene** note: the text is hard-wrapped
  mid-sentence and hyphenates with `‐` (U+2010), so full-sentence greps fail
  even when the sentence is present — grep a distinctive 3–6 word fragment,
  then `sed -n 'N,Mp'` around the hit. Include a chapter→line-number table so
  the agent can seek instead of scanning.
- **What This Book Does NOT Care About** — the scope fence. Without it the agent
  drifts into generic code review and the panel loses its point.
- **Calibration Examples** — before/after pairs with the correct verdict, so
  severity is anchored rather than guessed.
- **Output Format** — findings with file, line, severity, and a citation.

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
  charter** and tell the agent to surface the tension rather than hedge toward
  the other lens. A charter that pre-concedes its disagreements produces a
  reviewer that adds nothing to the panel.
- The **scope fence still matters**, but it fences out concerns the book has no
  position on — not concerns another reviewer also happens to hold.

## 7. Improve on the existing panel

The current five are good; these are their gaps. Close them:

- **Cite figures.** None of the existing reviewers reference diagrams. Point at
  `<slug>-figures/figures.md` and let findings say "see Figure 4.2."
- **Say when the book is wrong, or silent.** Add a short *Known Limits* section:
  where the book's advice is dated, contested, or doesn't address the codebase's
  situation. A reviewer that can say "the book doesn't cover this" is more useful
  than one that stretches.
- **Confidence on each finding.** Mark whether a finding is the book's explicit
  position or your extension of it. The panel review in `go-review` merges
  multiple reviewers; unmarked extrapolation is what makes merged output
  untrustworthy.
- **No findings is a valid result.** Say so explicitly in How You Review, or the
  agent will manufacture findings to seem useful. Go further: tell it to record
  **declined findings** — ones another panel reviewer might raise — with the
  premise for declining. On a clean diff that is the whole value of the review.
- **Give it a way to say "this is right, and here is why."** A charter full of
  red flags can only report defects, so on a clean diff it falls silent and the
  review is worthless. Include at least one calibration example where the diff
  *passes* a named test, stated as an endorsement. The most common real-world
  diff shape is "someone extracted a helper and it was fine"; a reviewer that
  cannot say so has nothing to offer on most PRs.
- **State the precedence between your gates and your red-flag table.** If the
  charter has both a checklist of smells and a test for whether a finding
  qualifies, say which wins. Without it the table pulls the agent toward
  pattern-matching on shape — recommending virtualization for a list of
  twenty — and the gate never runs.
- **Establish the base before reviewing.** Every charter needs a line telling the
  agent to review the PR head branch, not the working tree, and to verify any
  claimed precondition against `origin/main` rather than the PR branch. A branch
  cut before a precondition landed looks identical to one whose precondition was
  never met — and that produces a confident, error-severity false positive about
  production breakage. This is the single highest-cost mistake a reviewer makes.

## 8. Verify before handing over

1. `head -5` the agent file — frontmatter parses, `name` matches the filename.
2. **Verify every quote the charter uses, with normalized matching.** Extract
   the quoted strings and test each against the book text with whitespace
   collapsed and `‐`/curly apostrophes folded — a raw `grep` of a short
   fragment passes while the charter's longer rendering spans a line break,
   so the short-fragment check hides exactly the defects you are looking for.

   ```python
   norm = lambda t: re.sub(r'\s+', ' ',
       t.replace('\u2010','-').replace('\u2019',"'"))
   missing = [q for q in re.findall(r'"([^"\n]{12,})"', charter)
              if norm(q).rstrip('.') not in norm(book)]
   ```

   Two mechanical traps make the checker lie, and both read as a wall of
   failures rather than an obvious bug:

   - **Never pair quotes across a flattened file.** Collapsing newlines first
     and then matching `"(.*?)"` makes the regex pair the closing quote of one
     citation with the opening quote of the next, capturing your own prose in
     between and reporting it as missing. Keep `[^"\n]` so a span cannot cross
     a line, and join wrapped lines only inside a single already-extracted
     span.
   - **Fold nested quotation marks.** A citation containing an inner quote
     ("Whenever you find yourself thinking 'but of course that could never
     happen,'...") fails on the inner marks alone. Normalize single curly
     quotes too, or re-check the failures with a plain substring of the
     distinctive middle words before believing them.

   A sane run reports a handful of misses. Dozens means the checker is broken —
   read three of them, and if they contain your own sentences, fix the
   extraction before touching the charter.

   Exclude any section that quotes *paraphrased speech* rather than the book —
   a Characteristic Objections list quoting what developers say will flood the
   output with false misses. Then chase every real miss: some are a distiller's
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
   what you verified. Mention that **a new agent needs a Claude Code restart**
   before it appears in the agent list — until then it can only be exercised by
   pointing a general-purpose agent at the charter file.
