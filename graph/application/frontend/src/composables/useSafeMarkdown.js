import DOMPurify from 'dompurify'
import { Marked } from 'marked'
import { markedHighlight } from 'marked-highlight'
import markedKatex from 'marked-katex-extension'
import katex from 'katex'
import hljs from 'highlight.js/lib/core'
import c from 'highlight.js/lib/languages/c'
import cpp from 'highlight.js/lib/languages/cpp'
import python from 'highlight.js/lib/languages/python'
import java from 'highlight.js/lib/languages/java'
import matlab from 'highlight.js/lib/languages/matlab'
import fortran from 'highlight.js/lib/languages/fortran'
import plaintext from 'highlight.js/lib/languages/plaintext'
import 'katex/dist/katex.min.css'
import 'highlight.js/styles/github-dark.min.css'
import { toMathSegments } from '@/utils/questionMathText'

// 只注册数据源中实际出现的语言，控制打包体积
hljs.registerLanguage('c', c)
hljs.registerLanguage('cpp', cpp)
hljs.registerLanguage('python', python)
hljs.registerLanguage('java', java)
hljs.registerLanguage('matlab', matlab)
hljs.registerLanguage('fortran', fortran)
hljs.registerLanguage('plaintext', plaintext)

const markedInstance = new Marked(
  markedHighlight({
    langPrefix: 'hljs language-',
    highlight(code, lang) {
      const language = hljs.getLanguage(lang) ? lang : 'plaintext'
      return hljs.highlight(code, { language }).value
    }
  })
)

markedInstance.use(
  markedKatex({
    throwOnError: false,
    nonStandard: true
  })
)

markedInstance.setOptions({ gfm: true, breaks: true })

// 数据源中块级公式常紧贴正文（含引用块内），breaks: true 会把 $$ 行并入段落
// 导致公式不被解析；给 $$ 定界行前后补空行使其独立成块。代码围栏内不处理。
function padMathBlocks(text) {
  const lines = text.split('\n')
  const out = []
  let inFence = false
  let inMath = false
  for (const line of lines) {
    if (/^\s*(`{3,}|~{3,})/.test(line)) inFence = !inFence
    const isMathDelim = !inFence && /^\s*(>\s*)*\$\$\s*$/.test(line)
    if (isMathDelim) {
      const quotePrefix = (line.match(/^\s*(>\s*)+/) || [''])[0].trimEnd()
      if (!inMath) {
        out.push(quotePrefix, line)
      } else {
        out.push(line, quotePrefix)
      }
      inMath = !inMath
    } else {
      out.push(line)
    }
  }
  return out.join('\n')
}

// 行内渲染不识别多行 $$ 块：折叠为单行 $$...$$ 供行内 katex 规则识别，
// 并去掉块内的引用前缀
function collapseMathBlocks(text) {
  return text.replace(/\$\$[^\S\n]*\n([\s\S]*?)\n[^\S\n]*(?:>[^\S\n]*)*\$\$/g, (_, body) =>
    '$$' + body.replace(/^[^\S\n]*(>[^\S\n]*)+/gm, '').replace(/\n/g, ' ').trim() + '$$'
  )
}

function sanitize(html) {
  return DOMPurify.sanitize(html)
}

export function useSafeMarkdown() {
  function renderMarkdown(content) {
    if (!content) return ''
    return sanitize(markedInstance.parse(padMathBlocks(String(content))))
  }

  // 行内渲染：不产生 p/pre/table 等块级元素，用于 quote 等单段场景
  function renderMarkdownInline(content) {
    if (!content) return ''
    return sanitize(markedInstance.parseInline(collapseMathBlocks(String(content))))
  }

  function renderRelatedSection(content) {
    if (!content) return ''
    return renderMarkdown(
      String(content).replace(/\[\[(\d+)-([^\]]+)\]\]/g, '$2')
    )
  }

  // 题目文本渲染：不走 markdown（题面是纯文本），只做拍平公式重建 + KaTeX。
  // 文本段做 HTML 转义，换行由容器的 pre-wrap 呈现。
  function renderQuestionText(content) {
    if (!content) return ''
    const html = toMathSegments(content)
      .map((seg) => {
        if (seg.type === 'math') {
          return katex.renderToString(seg.value, { throwOnError: false })
        }
        return seg.value
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
      })
      .join('')
    return sanitize(html)
  }

  return {
    renderMarkdown,
    renderMarkdownInline,
    renderRelatedSection,
    renderQuestionText
  }
}
