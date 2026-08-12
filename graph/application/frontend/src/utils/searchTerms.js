const SEARCH_TERM_ALIASES = Object.freeze({
  '折半查找': '二分查找'
})

const CANONICAL_GRAPH_TARGETS = new Map([
  ['折半查找', 'NODE_381'],
  ['二分查找', 'NODE_381'],
  ['246', 'NODE_381'],
  ['NODE_246', 'NODE_381'],
  ['381', 'NODE_381'],
  ['NODE_381', 'NODE_381']
])

export function normalizeSearchTerm(value) {
  const term = String(value || '').trim()
  return SEARCH_TERM_ALIASES[term] || term
}

export function resolveCanonicalGraphTarget(value) {
  const target = String(value || '').trim()
  return CANONICAL_GRAPH_TARGETS.get(target) || target
}
