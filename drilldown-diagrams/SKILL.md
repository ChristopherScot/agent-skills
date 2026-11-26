---
name: drilldown-diagrams
description: Build click-through, editable Graphviz diagrams where boxes open more detailed diagrams (overview → entity graph → state machine) and people can rename boxes and edit descriptions in the page, delivered as a self-contained HTML file, an embeddable fragment, or (in Claude) a claude.ai artifact. Use when asked for interactive, zoomable, drill-down, nested, click-to-expand or editable diagrams of architecture, domains, data models or state machines, or to update or read back one made earlier.
compatibility: Requires Node 18+ and Graphviz (dot) to build. The finished page needs neither and runs in any modern browser. Checking a build also needs npm, Playwright and Chromium. The claude.ai artifact output needs Claude's Artifact tool; every other output works with any agent.
---

# Drill-down diagrams

One plain Graphviz DOT file holds every view. Each `digraph` is one view; a box opens another view through the standard Graphviz `URL="#view-id"` attribute. The page draws every view in the browser with Graphviz (`@viz-js/viz`: loaded from jsDelivr, or embedded in a standalone file) and adds breadcrumbs, a zoom transition from the clicked box, `Esc` to go up a level, light and dark themes, and an **Edit** mode. In edit mode the current view becomes point-and-click: drag from a node to connect it (from its left dot for an arrow pointing back), or into empty space for a new connected node; double-click or select-and-type to rename; Tab (Shift+Tab: pointing back) adds a connected node that inherits the source's class and shape; the ✥ grip moves a node or group into or out of a group, or beside another node in the same row; **Add node** adds one, **Create group** draws a dashed group around whatever you drag over (a tap makes an empty one), and **Turn into view** makes the selected group its own view, leaving a node that opens it (arrows coming into the group are kept in the new view as ghosts); Delete removes the selection; the edit bar's Color, Shape, Line and Arrow pickers restyle it (Color offers the legend's classes, custom ones included); **Details…** or right-click opens the label and description editor; **Undo** and **Redo** (⌘/Ctrl+Z) step through changes. Every change is checked against `validate.mjs` and Graphviz before it lands, and renaming a node on the canvas renames its ghost copies in other views and the view it opens. Click the title, caption or notes to edit them, or open **Edit DOT**: a syntax-highlighted side panel holding the current view's `digraph` (it follows navigation; a **Whole file** switch shows all of `model.dot`), which redraws as you type. Errors show with line numbers and keep the last good drawing; leaving a view with an error is blocked; a second `digraph` typed into the panel becomes a new view. Renaming the view's `digraph` name in **This view** mode also repoints every `parent="…"` and `URL="#…"` in other views (computed from a snapshot taken when the view loaded, so typing through a colliding name never strands references); **Whole file** mode leaves references to you and flags any that break. Then Save. The DOT is the single source of truth: edits rewrite only the changed attribute in place, so diffs stay small and readable.

Files next to this one: `build.mjs` (checks the model and writes the output), `validate.mjs` (the model rules, shared by the build and the page so both reject the same mistakes), `template.html` (the page), `vendor/editor/` (the point-and-click editing code, copied from `lib/` in github.com/ChristopherScot/diagrams at the commit named in `vendor/editor/SOURCE`; change it there and copy it back, and `build.mjs` bundles it into the page), `vendor/viz-global-3.31.0.js` (the Graphviz browser build embedded in standalone files), `example.dot` (a 7-view domain map), `scripts/check-deps.sh` (checks the tools below). To upgrade Graphviz, download the new `viz-global.js` into `vendor/` and bump `VIZ_VERSION` in `build.mjs`. All paths in this file are relative to this skill's directory.

## Requirements

| Needed for | Tool | Notes |
|---|---|---|
| building | Node 18+ | runs `build.mjs` |
| building | Graphviz (`dot`) | the build lays out every view to check it; not installed by default |
| checking a build | npm, `@playwright/test`, Chromium | only for `check.mjs` |
| viewing | a modern browser | the page needs nothing else |

**Check before building:**

```bash
sh scripts/check-deps.sh build      # or: check, all
```

It prints each tool as `ok` or `MISSING` with the install command for this machine, and exits non-zero if a required one is missing. If anything is missing, **show the user the install command and ask before running it** — never install silently. If they decline, stop and say what could not be done.

## Whole map

A **Whole map** button (hidden while editing, and when no view has children) opens `#whole-map`: every view under the current top-level view drawn as one generated diagram, never saved. Depth buttons (**Top level**, 1, 2, … **All levels**) set how many levels open; a **+** badge on a box opens just that branch in place, a **−** badge on a group closes it, and **Reset** returns to the chosen depth; drag to pan, pinch or ⌘/Ctrl + scroll to zoom, **Fit** to see it all. Generation rules, so models read well in it:

- Expansion follows drill links: a view's children in the map are its declared children (`parent`) plus every view its solid (non-`ghost`) boxes link to. Each view is drawn once, claimed by the shallowest box that reaches it (breadth-first), so links back up or sideways never duplicate or loop.
- An opened view is a dashed group that replaces the box that opened it, inside the same dashed area that box sat in; arrows to it end at the group's border (Graphviz `compound=true`).
- A box pointing at another view (a `ghost`, or any linked box) merges into the box with the same id in that view, when that view is drawn and defines it. Otherwise it attaches to that view's group.
- Boxes that merely share an id in different views stay separate (a lifecycle status and an event can both be `reserved`). So when a detail view shows something defined elsewhere, such as `User`, draw it as `class="ghost"` with a `URL` to its home view: then the map merges it instead of drawing a second copy.
- Each box links to its home view; boxes whose child view is not opened at the current depth keep their drill outline.

## Model conventions

```dot
digraph enrollment {
  title="Enrollment"                 // page heading and breadcrumb text
  parent="system"                    // view id one level up; omit for a top-level view
  caption="One or two sentences under the diagram saying how to read it. **Markdown** works."
  notes="Optional longer text shown below the diagram; Markdown, \n for a new line."
  legend="blue: Catalog, amber: People, billing: Billing #c2410c"   // class labels and colors; any view may set it, all merge
  rankdir=BT

  enrollment [label="Enrollment" class="amber" URL="#enrollment-lifecycle" tooltip="Open the lifecycle" description="Shown when someone points at the box."]
  section [label="Section" class="ghost" URL="#scheduling" tooltip="Open Scheduling"]
  subgraph cluster_people { label="PEOPLE"; style=dashed; URL="#people"; description="..." ... }

  enrollment -> section [label="seat in"]
}
```

- **View id** = the graph name: lowercase letters, digits, hyphens (not `whole-map`, which the map uses); quote it when it has a hyphen (`digraph "enrollment-lifecycle"`). It is the page's `#hash`, so views are linkable.
- **Drill links**: `URL="#other-view"` on a node or cluster. Linked nodes get a thick outline and a corner badge; linked clusters get a dotted-underline label.
- **Classes, labels and colors are the model's to choose.** Each `class` on a box is declared once in a `legend` entry, `name: Label #color`, written on any view (entries merge; separate them with `;` instead of `,` when labels contain commas). The page only supplies defaults:
  - Built-in classes `blue green amber violet rose slate` have theme-tuned colors and default to their own name as a label; a legend entry relabels them, and adding a color recolors them.
  - Any other class name (lowercase letters, digits, hyphens) works once its legend entry gives a color, e.g. `billing: Billing & payments #c2410c`. One hex color is enough: the page derives the box fill and outline for light and dark themes from it.
  - `ghost` is the dashed "defined in another view" style. Its label defaults to "Lives in another view" and its outline to gray; `ghost: Defined elsewhere #8761cf` changes either. Give ghosts a `URL` to their home view.
  - Use one class per domain area, consistent across views. Undeclared classes fail the build and the in-page checks.
- **Caption and notes** render as Markdown (bold, italics, code, lists, headings, quotes, links); HTML is shown as text. A link like `[Scheduling](#scheduling)` opens that view inside the same widget, and other links open in a new tab. In edit mode they are edited as plain text.
- **Descriptions**: `description="..."` on nodes and clusters (Graphviz ignores it; the page shows it on hover and edits it).
- The same node id with the same label in several views is treated as the same thing: the **Details…** editor offers to rename it everywhere at once. Renaming on the canvas itself follows ghosts instead: it renames every `class="ghost"` copy whose `URL` points at the box's home view, and the view the box opens.
- A box and the view it opens are linked by name when the box label's first line equals the view's `title`. Renaming either renames the other (the view's title is also its breadcrumb text), so keep that first line equal to the title when you want them to stay in sync.
- **Line style carries meaning** through plain DOT (`style=dashed`, `style=dotted`); say what each style means in the caption.
- **Rows**: `subgraph row_N { rank=same; … }` (written with `newrank=true` on the view) is how the editor lines nodes up side by side. It is layout only: the nodes in a row are not grouped or related, and a row does not change which group a node belongs to.
- Layout defaults (rounded filled boxes, Helvetica, spacing) come from the page; anything set in the DOT wins.
- Write one statement per line. The in-page editor finds a box by its declaration line (`id [ ... ]`), and adds one if the box only appears in edges.

## Build

```bash
node build.mjs model.dot out/ --title "Page Name" [--footer "text"] \
  [--standalone | --embed [--name <id>]]
```

Run it with this skill's directory as the working directory, or give `build.mjs` its full path; `model.dot` and `out/` are wherever the user's diagram lives.

**Pick the output by where you are running:**

- **In Claude, with the Artifact tool available:** the claude.ai artifact (no flag). Viewers can edit and save in place.
- **Anywhere else:** `--standalone`. It works offline in any browser, and Save downloads an updated file. Use this whenever you are unsure.
- **Inside a larger page:** `--embed`. Editing only saves inside a claude.ai artifact; anywhere else the widget is read-only apart from Copy DOT.

Outside Claude, hand the user the path to `index.html`, and keep the `.dot` file you built it from beside it as the readable source. If your host can publish an HTML page to a link, publish the standalone file, and tell the user that edits made on the published page download a new file rather than updating the shared copy. To update a standalone diagram later, start from the newest file the user has (a downloaded copy may be newer than yours) and take the model from its `<script type="text/vnd.graphviz" id="model-source">` block.

The three modes are the same page; they differ only in what the page is wrapped in and where it reads its model from. `--standalone` and `--embed` cannot be combined.

The build fails, listing every problem, when a link or `parent` names a missing view, an id is invalid or reserved by claude.ai, or a `class` is not a known hue. Fix and rebuild; never publish a failed build.

## Outputs

**claude.ai artifact** (default; Claude only): `out/index.html` (the page, no model inside) and `out/model.dot` (the model). Saving in the page publishes a new `model.dot` only, so the page stays fixed and the model is a plain file anyone can read.

- New artifact: run the Artifact tool's `quickstart` with `intent: "other"` first (its rules require it; the template already meets the page contract), then publish `file_path: out/index.html`, `files: {"model.dot": {"from": "out/model.dot", "contentType": "text/plain"}}`, `capabilities: {"artifact": {}}`, `icon: "diagram"`, and a one-sentence `description`.
- Viewers with edit access see the Edit button and can save; others get a read-only page. "Save and finish" (the edit toggle while changes are pending) saves; unsaved edits are also kept in the viewer's browser and offered back after a refresh, as long as nobody saved a newer model in between.
- Every save, by a viewer or by Claude, is a new artifact version. To roll the model back, copy an older version's file with an Artifact publish `files: {"model.dot": {"artifact": "<url>", "path": "model.dot", "ver": "<version id>"}}`. A save that loses a race with another person's save is dropped and the page reloads to theirs.
- **Reading or updating an existing one**: people may have edited it, so always start from the live model: Artifact `read` with `path: "model.dot"`, save it locally, edit or rebuild from that file, then publish both files to the same `url`. Never rebuild from an older local copy, which would erase their edits.

**Standalone HTML** (`--standalone`): one complete `out/index.html` (about 1.5 MB) with the model and the Graphviz library embedded, so it works fully offline; only the web fonts need a network, and system fonts stand in without one. Save downloads an updated copy of the whole file, which replaces the old one. To read its model, take the `<script type="text/vnd.graphviz" id="model-source">` block from the file.

**Embeddable fragment** (`--embed [--name <id>]`): `out/<id>.html` (a bare fragment — no doctype, no `<head>`) and `out/<id>.dot`. Paste the fragment into any larger page, with prose or other widgets around it, and ship the `.dot` beside it. `<id>` defaults to the first view's id; pass `--name` to choose it. Use this when a diagram belongs *inside* a document rather than being the whole page.

- **Several on one page**: build each with its own `--name`, concatenate the fragments, and put every `.dot` next to the host page. Each widget claims its own root, reads its own model, scopes its own palette, and keeps its own position, so clicking into a sub-view in one leaves the others alone.
- An embed's colors, fonts and dark mode belong to the widget: the build scopes the page-level `:root` and `body` styles to `.drilldown[data-dd-name="<id>"]`, so a widget carries its own palette, inherits nothing from the host page, and never restyles it.
- Embeds run with `data-dd-routing="none"`: they never touch `location.hash`, so the host page keeps its own anchors and two widgets cannot fight over one hash. The cost is that an embedded widget's current view is not linkable or bookmarkable.
- Saving still publishes `<id>.dot`, so editing works inside a host claude.ai artifact as long as that artifact carries the `artifact` capability and the `.dot` is one of its published files. In any other host page, Save says saving is not available and Copy DOT is the way to keep changes.

**Markdown is not an output.** Markdown viewers strip scripts and inline SVG links, so neither drill-down nor editing can work there. Link to the artifact or HTML file from a `.md` instead.

## Widget attributes

The build sets these on the widget's root `<div class="drilldown" data-dd-root>`; they are the only knobs a host page needs, and hand-editing them is supported.

| Attribute | Default | Meaning |
|---|---|---|
| `data-dd-name` | `dd` | Instance id. Must be unique on the page: it scopes the widget's palette and tells it which `<script data-dd-data=…>` blocks are its own. |
| `data-dd-model` | `model.dot` | Where the model comes from — the id of an inline `<script type="text/vnd.graphviz">` if one matches, otherwise a path to `fetch`. Also the path a save publishes to, so it must end in `.dot`. |
| `data-dd-routing` | `hash` | `hash` keeps the current view in `location.hash`; `none` keeps it in memory. Use `none` for anything embedded. |

Inside the widget, elements are addressed by `data-dd="…"` rather than `id`, so two copies on a page don't collide. The few real `id`s that remain are the ones ARIA has to point at.

## Checking the result

`check.mjs` next to this file drives a built page and asserts seven things: an SVG renders, the expected number of widgets is present, drill boxes exist, clicking one opens the view it targets, Edit toggles, the whole map renders its clusters, and the console is clean. It serves the directory over HTTP so the model loads either way, and works on all three modes.

Playwright is resolved from the directory you run it in, not from this skill, so run it from a directory that has `@playwright/test`. If none exists, ask the user before setting one up (it downloads Chromium, about 150 MB):

```bash
mkdir -p ~/.cache/drilldown-check && cd ~/.cache/drilldown-check
npm init -y && npm i -D @playwright/test && npx playwright install chromium
```

Then, from that directory, with `<skill>` standing for this skill's directory:

```bash
node <skill>/check.mjs /path/to/out/
node <skill>/check.mjs /path/to/host/ --instances=2
```

Chromium may refuse to start inside an agent's sandbox. If it does, ask the user to allow running the check outside the sandbox rather than skipping it.

Run it after any change to `template.html` — a single-instance page will pass while two on one page quietly collide, which is what `--instances` catches.

Before publishing, also take one rendered look yourself if you can open a browser: click a drill box, toggle Edit, rename a box and confirm it redraws. If you cannot, say that only `check.mjs` verified it. Saving to claude.ai can only be exercised from the live artifact; say so when handing it over.

## Not built yet

Editing on the whole map. Keep the DOT highlighter hand-rolled (no editor library), so standalone files stay self-contained and work offline.
