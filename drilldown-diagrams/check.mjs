// Verifies a built drill-down page still works. Run after changing the template.
//   node check.mjs <dir-with-index.html> [--instances=N]
// Serves the directory over HTTP so the model loads, then drives the page.
//
// Needs @playwright/test, which this skill does not vendor. ESM resolves bare
// imports from the SCRIPT's directory, not the cwd, so this file cannot import
// it directly -- it resolves playwright from the working directory instead.
// Run it from any dir where `npm i -D @playwright/test` and
// `npx playwright install chromium` have been run.
import { createServer } from 'http'
import { readFile } from 'fs/promises'
import { createRequire } from 'module'
import { extname, join, resolve } from 'path'

// Resolve from the cwd so the skill copy works without vendoring playwright.
const requireFromCwd = createRequire(join(process.cwd(), 'noop.js'))
let chromium
try {
  ;({ chromium } = requireFromCwd('@playwright/test'))
} catch {
  console.error(
    'check.mjs needs @playwright/test, resolved from the current directory.\n' +
    `Tried from: ${process.cwd()}\n` +
    'Run it from a directory that has it, or set one up once:\n' +
    '  mkdir -p ~/.cache/drilldown-check && cd ~/.cache/drilldown-check\n' +
    '  npm init -y && npm i -D @playwright/test && npx playwright install chromium')
  process.exit(2)
}

const dir = resolve(process.argv[2] ?? 'baseline')
const want = Number((process.argv.find(a => a.startsWith('--instances=')) ?? '').split('=')[1] ?? 1)

const TYPES = { '.html': 'text/html', '.dot': 'text/plain', '.js': 'text/javascript', '.css': 'text/css' }
const server = createServer(async (req, res) => {
  const path = (req.url ?? '/').split('?')[0]
  try {
    const file = path === '/' ? 'index.html' : path
    const body = await readFile(join(dir, file))
    // charset matters: without it Chromium treats text/html as a download.
    const type = TYPES[extname(file)] ?? 'text/plain'
    res.writeHead(200, { 'content-type': type + '; charset=utf-8' })
    res.end(body)
  } catch {
    res.writeHead(404).end('not found')
  }
})
await new Promise(ok => server.listen(0, ok))
const base = `http://localhost:${server.address().port}/`

const results = []
const record = (name, pass, detail = '') => {
  results.push({ name, pass, detail })
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`)
}

const browser = await chromium.launch()
const page = await browser.newPage()
const errors = []
// Graphviz emits pathplan warnings on dense layouts (the whole map triggers
// them on the stock example). They are present in the unmodified template, so
// treating them as failures would hide real regressions behind known noise.
const BENIGN = /pathplan|triangulation failed|cannot find triangle path/i
page.on('console', m => { if (m.type() === 'error' && !BENIGN.test(m.text())) errors.push(m.text()) })
page.on('pageerror', e => { if (!BENIGN.test(e.message)) errors.push(e.message) })

try {
  await page.goto(base, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1500)

  // 1. The model loaded and something rendered.
  const svgCount = await page.locator('svg').count()
  record('renders SVG', svgCount > 0, `${svgCount} svg element(s)`)

  // 2. Expected number of widget instances.
  const stages = await page.locator('.stage, .dd-stage').count()
  record(`has ${want} stage(s)`, stages >= want, `found ${stages}`)

  // 3. Drill links are present and clickable.
  const drills = await page.locator('g.node.drill, .dd-stage g.node.drill').count()
  record('drill boxes present', drills > 0, `${drills} box(es)`)

  // 4. Clicking a drill box opens the view it targets.
  //
  // Do NOT compare svg.first().innerHTML(): the standalone template keeps one
  // <section> per view and toggles visibility, so "the first svg" is not the
  // one on screen. Assert on the target the box declares instead.
  let navigated = false
  let navDetail = 'no drill box to click'
  if (drills > 0) {
    const box = page.locator('g.node.drill, .dd-stage g.node.drill').first()
    const target = await box.evaluate(el => el.dataset.target ?? '')
    await box.locator('a').first().click({ force: true })
    await page.waitForTimeout(1200)
    // Assert on the view the widget now SHOWS, not on location.hash: an embed
    // runs with data-dd-routing="none" and deliberately never writes the hash,
    // so a hash comparison fails on a widget that navigated correctly.
    const state = await page.evaluate(() => {
      const root = document.querySelector('[data-dd-root]') ?? document.body
      const shown = Array.from(root.querySelectorAll('section'))
        .filter(section => !section.hidden)
        .map(section => section.dataset.view ?? section.id ?? '')
      return { shown, hash: location.hash.slice(1) }
    })
    navigated = target !== '' && state.shown.includes(target)
    navDetail = `target=${target} shown=[${state.shown.join(',')}] hash=${state.hash}`
  }
  record('drill navigation', navigated, navDetail)

  // 5. Edit mode opens and marks the widget, so later phases cannot silently
  //    break editing while navigation still looks fine.
  const editBtn = page.locator('[data-dd="edit-toggle"], #edit-toggle').first()
  let editOk = false
  let editDetail = 'no edit button (expected read-only build)'
  if (await editBtn.count() > 0 && await editBtn.isVisible()) {
    await editBtn.click()
    await page.waitForTimeout(600)
    editOk = await page.evaluate(() =>
      document.querySelector('.drilldown')?.classList.contains('is-editing') ??
      document.body.classList.contains('is-editing'))
    editDetail = editOk ? 'is-editing applied' : 'clicked but is-editing not set'
    if (editOk) { await editBtn.click(); await page.waitForTimeout(400) }
  } else {
    editOk = true
  }
  record('edit mode toggles', editOk, editDetail)

  // 6. The whole-map view renders when offered.
  const mapBtn = page.locator('[data-dd="map-toggle"], #map-toggle').first()
  let mapOk = true
  let mapDetail = 'no map button'
  if (await mapBtn.count() > 0 && await mapBtn.isVisible()) {
    await mapBtn.click()
    await page.waitForTimeout(1800)
    const clusters = await page.locator('g.cluster').count()
    mapOk = clusters > 0
    mapDetail = `${clusters} cluster(s) in map`
  }
  record('whole map renders', mapOk, mapDetail)

  // 7. No uncaught errors.
  record('no console errors', errors.length === 0, errors.slice(0, 2).join(' | '))
} catch (err) {
  record('ran to completion', false, err.message)
} finally {
  await browser.close()
  server.close()
}

const failed = results.filter(r => !r.pass)
console.log(`\n${results.length - failed.length}/${results.length} checks passed`)
process.exit(failed.length === 0 ? 0 : 1)
