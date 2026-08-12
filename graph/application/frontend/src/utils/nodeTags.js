export function normalizeNodeTags(node) {
  const tags = normalizeTagValue(node?.tags)
  if (!tags.length) {
    const section = String(node?.section || '').trim()
    const sectionTag = section.replace(/^\d+(?:\.\d+)*\s*/, '').trim()
    if (sectionTag && sectionTag !== String(node?.name || '').trim()) {
      tags.push(sectionTag)
    }
  }

  const seen = new Set()
  return tags
    .map(tag => String(tag).replace(/^[\s"']+/, '').replace(/[\s"']+$/, '').trim())
    .filter(tag => tag && tag !== 'null' && tag !== 'undefined' && !seen.has(tag) && seen.add(tag))
    .slice(0, 8)
}

function normalizeTagValue(value) {
  if (Array.isArray(value)) return value.flatMap(normalizeTagValue)
  if (value === null || value === undefined) return []
  if (typeof value !== 'string') return [value]

  const text = value.trim()
  if (!text) return []
  try {
    const parsed = JSON.parse(text)
    if (Array.isArray(parsed) || typeof parsed === 'string') {
      return normalizeTagValue(parsed)
    }
  } catch {
    // Older imports may contain a plain space/comma-delimited string.
  }
  return text.split(/[\s,，、|]+/).filter(Boolean)
}
