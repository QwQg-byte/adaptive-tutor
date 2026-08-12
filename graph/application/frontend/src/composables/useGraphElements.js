export function useGraphElements({ getNodeColor, getRelationColor, relationTypeLabels, generateTooltip }) {
  function toGraphNode(node) {
    return {
      id: node.id,
      label: node.label,
      title: generateTooltip(node),
      group: node.type === 'KnowledgeNode'
        ? (node.properties?.node_type || node.type)
        : node.type,
      nodeType: node.type,
      color: getNodeColor(node),
      font: {
        size: node.type === 'Chapter' ? 16 : 14,
        bold: node.type === 'Chapter'
      },
      size: node.type === 'Chapter'
        ? 25
        : (node.type === 'Question' ? 20 : (node.type === 'NodeType' ? 30 : 18)),
      properties: node.properties
    }
  }

  function toGraphEdge(edge) {
    return {
      id: `${edge.from}-${edge.to}-${edge.label}`,
      from: edge.from,
      to: edge.to,
      label: relationTypeLabels[edge.label] || edge.label,
      title: relationTypeLabels[edge.label] || edge.label,
      color: getRelationColor(edge.label),
      arrows: 'to',
      smooth: { type: 'curvedCW', roundness: 0.2 },
      relationshipType: edge.label,
      properties: edge.properties
    }
  }

  return { toGraphNode, toGraphEdge }
}
