// 码蹄集题目文本的公式重建。
//
// 抓取数据保存的是公式渲染后的可视文本：每个上下标元素独占一行，
// 例如 a₁∼aₙ 被拍平为 "a\n1\n∼a\nn"，10⁵ 被拍平为 "10\n5"，
// ∑_{i=1}^{n} 被拍平为 "∑\ni=1\nn"。LaTeX 源码未保留。
// 本模块按高置信度模式把这些片段还原为 LaTeX，其余文本原样保留。

const MATH_START = ''
const MATH_END = ''

// 句末标点：其后的换行视为真实分段而非公式拍平产生的断行
const SENTENCE_END = /[。！？；：”…)]$|^$/

// 新题接口保留了 KaTeX annotation 中的 TeX 源码，并用 $$...$$ 标记。
// 先转成内部标记，避免后续旧题“拍平公式”重建把定界符当作普通文本。
function markExplicitMath(raw) {
  return String(raw).replace(/\$\$([\s\S]*?)\$\$/g, (_, tex) =>
    `${MATH_START}${tex.trim()}${MATH_END}`
  )
}

function reconstruct(raw) {
  let text = markExplicitMath(raw)

  // ∑ 的上下界：∑ \n i=1 \n n → \sum_{i=1}^{n}
  text = text.replace(
    /∑\n(i=1)\n([A-Za-z0-9]{1,3})\n/g,
    `${MATH_START}\\sum_{$1}^{$2}${MATH_END}`
  )

  // 数字的指数：10 \n 5 → 10^{5}（要求底数行以数字结尾、指数独占一行）
  text = text.replace(
    /(?<![\d.])(\d{1,3})\n(\d{1,2})\n/g,
    `${MATH_START}$1^{$2}${MATH_END}`
  )

  // 字母的下标：a \n i → a_{i}（要求字母前不是字母，避免误伤英文单词结尾）
  text = text.replace(
    /(?<![A-Za-z])([A-Za-z])\n([a-z0-9]{1,2})\n/g,
    `${MATH_START}$1_{$2}${MATH_END}`
  )

  // 相邻公式段合并为一段（如 \sum_{i=1}^{n} 与 a_{i}）
  text = text.replace(new RegExp(`${MATH_END}${MATH_START}`, 'g'), ' ')

  // 断行修复：句中断行（非句末标点后）是公式边界产生的，拼回同一行；
  // 空行保留为分段
  text = text
    .split('\n')
    .reduce((acc, line) => {
      if (acc.length === 0) return [line]
      const prev = acc[acc.length - 1]
      if (line.trim() === '' || SENTENCE_END.test(prev.trim())) {
        acc.push(line)
      } else {
        acc[acc.length - 1] = prev + line
      }
      return acc
    }, [])
    .join('\n')

  return text
}

// 检测正文中间的空行（公式图片被爬虫丢弃留下的空洞）
// 判据：空行前后都有非空文本，且前行不以句末标点结尾
export function detectMissingFormula(raw) {
  if (!raw) return false
  const lines = String(raw).split('\n')
  for (let i = 1; i < lines.length - 1; i++) {
    if (lines[i].trim() !== '') continue
    const prev = lines[i - 1].trim()
    const next = lines[i + 1].trim()
    if (prev && next && !SENTENCE_END.test(prev)) return true
  }
  return false
}
export function toMathSegments(raw) {
  if (!raw) return []
  const segments = []
  for (const piece of reconstruct(raw).split(MATH_START)) {
    const end = piece.indexOf(MATH_END)
    if (end === -1) {
      if (piece) segments.push({ type: 'text', value: piece })
    } else {
      segments.push({ type: 'math', value: piece.slice(0, end) })
      const rest = piece.slice(end + 1)
      if (rest) segments.push({ type: 'text', value: rest })
    }
  }
  return segments
}
