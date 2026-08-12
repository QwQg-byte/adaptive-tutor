function addAll(target, values) {
  if (!values) return
  for (const value of values) target.add(value)
}

export function collectRetainedGraphIds({
  baseNodeIds = [],
  baseEdgeIds = [],
  retainedNodeIds = [],
  retainedEdgeIds = [],
  expansionFragments = new Map()
} = {}) {
  const nodeIds = new Set(baseNodeIds)
  const edgeIds = new Set(baseEdgeIds)

  addAll(nodeIds, retainedNodeIds)
  addAll(edgeIds, retainedEdgeIds)
  for (const fragment of expansionFragments.values()) {
    addAll(nodeIds, fragment?.nodeIds)
    addAll(edgeIds, fragment?.edgeIds)
  }

  return { nodeIds, edgeIds }
}
