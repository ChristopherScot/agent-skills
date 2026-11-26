import { execFileSync } from 'node:child_process'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { parseArgs } from 'node:util'

import { validateModel } from './validate.mjs'

const { values: options, positionals } = parseArgs({
  allowPositionals: true,
  options: {
    title: { type: 'string', default: 'Diagram Map' },
    footer: { type: 'string', default: '' },
    standalone: { type: 'boolean', default: false },
    embed: { type: 'boolean', default: false },
    name: { type: 'string', default: '' },
    template: { type: 'string', default: join(dirname(fileURLToPath(import.meta.url)), 'template.html') },
  },
})
const [sourcePath, outputDir] = positionals
if (sourcePath == null || outputDir == null) {
  console.error('usage: node build.mjs <model.dot> <output-dir> [--title "Page Name"] [--footer "text"] [--standalone | --embed [--name id]]')
  process.exit(2)
}

const SKILL_DIR = dirname(fileURLToPath(import.meta.url))
const VALIDATOR_PATH = join(SKILL_DIR, 'validate.mjs')
const EDITOR_DIR = join(SKILL_DIR, 'vendor', 'editor')
const EDITOR_EXPORTS = ['applyEdit', 'createDotCanvas', 'createDotDocument', 'createStyleBar', 'describe', 'impliedEdit', 'newNodeId', 'renderMarkdown']
const VIZ_VERSION = '3.31.0'
const VIZ_CDN_SCRIPT = `<script src="https://cdn.jsdelivr.net/npm/@viz-js/viz@${VIZ_VERSION}/dist/viz-global.js"></script>`
const VIZ_VENDORED_PATH = join(SKILL_DIR, 'vendor', `viz-global-${VIZ_VERSION}.js`)
const STANDALONE_SHELL = {
  before:
    '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n<style>[hidden] { display: none !important; } body { margin: 0; }</style>\n</head>\n<body>\n',
  after: '\n</body>\n</html>\n',
}

function splitGraphs(text) {
  const header = /(?:strict\s+)?(?:di)?graph\s+("(?:[^"\\]|\\.)*"|[A-Za-z_]\w*)\s*\{/g
  const graphs = []
  let match = header.exec(text)
  while (match != null) {
    let depth = 0
    let position = match.index + match[0].length - 1
    let inString = false
    for (; position < text.length; position += 1) {
      const character = text[position]
      if (inString) {
        if (character === '\\') position += 1
        else if (character === '"') inString = false
        continue
      }
      if (character === '"') inString = true
      else if (character === '{') depth += 1
      else if (character === '}') {
        depth -= 1
        if (depth === 0) break
      }
    }
    graphs.push(text.slice(match.index, position + 1))
    header.lastIndex = position + 1
    match = header.exec(text)
  }
  return graphs
}

function editorBundle() {
  const IMPORT = /^import \{([^}]*)\} from '\.\/([\w-]+)\.js'\n/gm
  const EXPORT = /^export (?:async )?(?:function|const|class|let) ([A-Za-z_$][\w$]*)/gm
  const variable = name => `__${name.replace(/-/g, '_')}`
  const bindings = list => list.split(',').map(part => part.trim()).filter(Boolean).map(part => part.replace(/\s+as\s+/, ': ')).join(', ')
  const out = []
  const seen = new Set()
  const owner = new Map()
  const add = name => {
    if (seen.has(name)) return
    seen.add(name)
    const text = readFileSync(join(EDITOR_DIR, `${name}.js`), 'utf8')
    for (const [, , dependency] of text.matchAll(IMPORT)) add(dependency)
    const exported = [...text.matchAll(EXPORT)].map(match => match[1])
    for (const name2 of exported) if (!owner.has(name2)) owner.set(name2, name)
    const body = text.replace(IMPORT, (_, list, dependency) => `const { ${bindings(list)} } = ${variable(dependency)}\n`).replace(/^export /gm, '')
    out.push(`const ${variable(name)} = (() => {\n${body}\nreturn { ${exported.join(', ')} }\n})()`)
  }
  for (const name of ['dot-text', 'dot-document', 'dot-views', 'dot-canvas', 'dot-style-bar', 'markdown']) add(name)
  const picks = EDITOR_EXPORTS.map(name => `${name}: ${variable(owner.get(name))}.${name}`)
  return `const Editor = (() => {\n${out.join('\n')}\nreturn { ${picks.join(', ')} }\n})()`
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
}

function scriptJson(value) {
  return JSON.stringify(value).replace(/</g, '\\u003c')
}

function layoutWithGraphviz(dot) {
  try {
    return JSON.parse(execFileSync('dot', ['-Tjson0'], { input: dot }).toString())
  } catch (error) {
    if (error.code === 'ENOENT') {
      console.error('Graphviz (dot) is not installed or not on PATH. Run scripts/check-deps.sh for the install command.')
      process.exit(2)
    }
    throw error
  }
}

const source = readFileSync(sourcePath, 'utf8')
const graphs = splitGraphs(source).map(layoutWithGraphviz)
const views = graphs.map(graph => ({ id: graph.name }))
const problems = validateModel(graphs)
if (problems.length > 0) {
  console.error(problems.join('\n'))
  process.exit(1)
}

if (options.standalone && options.embed) {
  console.error('--standalone and --embed are different outputs; pick one')
  process.exit(2)
}
// An embed is an artifact-mode page (it saves through window.claude), just
// mounted inside someone else's document instead of owning one.
const mode = options.standalone ? 'standalone' : 'artifact'
const instance = (options.name !== '' ? options.name : 'dd').replace(/[^a-z0-9-]/gi, '-').toLowerCase()
const modelFile = options.embed ? `${instance}.dot` : 'model.dot'
const pageTemplate = readFileSync(options.template, 'utf8')
  .replaceAll('{{TITLE}}', () => escapeHtml(options.title))
  .replace('{{FOOTER}}', () => (options.footer !== '' ? `<p class="foot">${escapeHtml(options.footer)}</p>` : ''))
  .replace('{{MODE}}', mode)
  .replace('{{VALIDATOR}}', () => readFileSync(VALIDATOR_PATH, 'utf8').replace(/^export /gm, ''))
  .replace('{{EDITOR}}', () => editorBundle())
  .replace('{{VIZ_SCRIPT}}', () => (options.standalone ? '{{VIZ_SCRIPT}}' : VIZ_CDN_SCRIPT))
  .replace('{{SHELL}}', () => scriptJson(options.standalone ? STANDALONE_SHELL : null))

mkdirSync(outputDir, { recursive: true })
if (options.standalone) {
  const vizSource = readFileSync(VIZ_VENDORED_PATH, 'utf8').replaceAll('</script', '<\\/script')
  const page = pageTemplate
    .replace('{{SOURCE}}', () => source.replaceAll('</', '<\\/'))
    .replace('{{VIZ_SCRIPT}}', () => `<script id="viz-lib">${vizSource}</script>`)
    .replace('{{TEMPLATE}}', () => scriptJson(pageTemplate))
  writeFileSync(join(outputDir, 'index.html'), STANDALONE_SHELL.before + page + STANDALONE_SHELL.after)
} else if (options.embed) {
  // A fragment the host page drops in, plus the model as its own named file.
  // The host supplies the surrounding document, so no shell is written.
  const page = pageTemplate.replace('{{SOURCE}}', '').replace('{{TEMPLATE}}', 'null')
  let body = page
    .replace('<div class="drilldown" data-dd-root data-dd-name="dd">',
      `<div class="drilldown" data-dd-root data-dd-name="${instance}" ` +
      `data-dd-model="${modelFile}" data-dd-routing="none">`)
  // Two embeds on one page would otherwise carry duplicate element ids and a
  // second <meta>. Tag the data blocks so each instance reads its own, and
  // drop the meta: MODE defaults to artifact, which is what an embed is.
  body = body
    .replace(/<meta name="drilldown-mode"[^>]*>\s*/g, '')
    .replace(/<script type="application\/json" id="page-template">/g,
      '<script type="application/json" data-dd-data="page-template">')
    .replace(/<script type="application\/json" id="page-shell">/g,
      '<script type="application/json" data-dd-data="page-shell">')
    .replace(/<script type="text\/vnd.graphviz" id="model-source">/g,
      '<script type="text/vnd.graphviz" data-dd-data="model-source">')
  const scope = `.drilldown[data-dd-name="${instance}"]`
  const scoped = [
    [/^:root \{/m, `${scope} {`],
    [/^  :root:not\(\[data-theme="light"\]\) \{/m, `  :root:not([data-theme="light"]) ${scope} {`],
    [/^:root\[data-theme="dark"\] \{/m, `[data-theme="dark"] ${scope} {`],
    [/^body \{/m, `${scope} {`],
  ]
  for (const [pattern, replacement] of scoped) {
    if (!pattern.test(body)) {
      console.error(`embed: the template no longer has ${pattern}; update the scoping in build.mjs`)
      process.exit(1)
    }
    body = body.replace(pattern, replacement)
  }
  writeFileSync(join(outputDir, `${instance}.html`), body)
  writeFileSync(join(outputDir, modelFile), source)
} else {
  const page = pageTemplate.replace('{{SOURCE}}', '').replace('{{TEMPLATE}}', 'null')
  writeFileSync(join(outputDir, 'index.html'), page)
  writeFileSync(join(outputDir, 'model.dot'), source)
}
console.log(
  `${views.length} views (${views.map(view => view.id).join(', ')}) -> ${outputDir}/ as ` +
    (options.standalone
      ? 'standalone index.html'
      : options.embed
        ? `embeddable ${instance}.html + ${modelFile}`
        : 'artifact index.html + model.dot')
)
