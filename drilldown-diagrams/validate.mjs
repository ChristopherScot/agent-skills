export const HUES = ['blue', 'green', 'amber', 'violet', 'rose', 'slate', 'ghost']
export const RESERVED_VIEW_IDS = ['settings', 'sidebar', 'customize', 'upgrade', 'downloads', 'whole-map']
const STRUCTURAL_CLASSES = ['drill']

export function parseLegend(graphs) {
  const entries = new Map()
  for (const graph of graphs) {
    const value = String(graph.legend ?? '')
    if (value.trim() === '') continue
    for (const entry of value.split(value.includes(';') ? ';' : ',')) {
      const match = /^\s*([A-Za-z0-9_-]+)\s*:\s*(.*?)\s*(#[0-9a-fA-F]{3,8})?\s*$/.exec(entry)
      if (match == null) continue
      const [, name, label, color] = match
      const previous = entries.get(name) ?? { label: '', color: null }
      entries.set(name, { label: label !== '' ? label : previous.label, color: color ?? previous.color })
    }
  }
  return entries
}

export function validateModel(graphs) {
  const problems = []
  if (graphs.length === 0) problems.push('The model has no digraph views.')
  const legend = parseLegend(graphs)
  for (const [name, entry] of legend) {
    if (HUES.includes(name)) continue
    if (!/^[a-z][a-z0-9-]*$/.test(name)) problems.push(`Legend class "${name}": use lowercase letters, digits and hyphens, starting with a letter.`)
    if (entry.color == null) problems.push(`Legend class "${name}": a new class needs a color, for example "${name}: ${entry.label || 'Label'} #3a7bd5".`)
  }
  const classes = new Set([...HUES, ...STRUCTURAL_CLASSES, ...legend.keys()])
  const viewIds = new Set(graphs.map(graph => graph.name))
  const seen = new Set()
  for (const graph of graphs) {
    const id = graph.name
    if (seen.has(id)) problems.push(`Two views are named "${id}".`)
    seen.add(id)
    if (!/^[a-z0-9-]+$/.test(id)) problems.push(`View "${id}": names use only lowercase letters, digits and hyphens.`)
    if (RESERVED_VIEW_IDS.includes(id) || id.startsWith('comment-')) problems.push(`View "${id}": that name is reserved (by claude.ai, or for the whole-map page).`)
    if (graph.parent != null && graph.parent !== '' && !viewIds.has(graph.parent))
      problems.push(`View "${id}": parent "${graph.parent}" is not a view.`)
    for (const item of [graph, ...(graph.objects ?? []), ...(graph.edges ?? [])]) {
      const where = item === graph ? `View "${id}"` : `View "${id}", ${item.name != null ? `"${item.name}"` : 'an arrow'}`
      if (typeof item.URL === 'string' && item.URL.startsWith('#') && !viewIds.has(item.URL.slice(1)))
        problems.push(`${where}: links to "${item.URL}", which is not a view.`)
      if (item !== graph && typeof item.class === 'string')
        for (const name of item.class.split(/\s+/).filter(Boolean))
          if (!classes.has(name))
            problems.push(`${where}: class "${name}" is not a built-in color (${HUES.join(', ')}) and is not declared in a legend; declare it, e.g. legend="${name}: Label #3a7bd5".`)
    }
  }
  return problems
}
