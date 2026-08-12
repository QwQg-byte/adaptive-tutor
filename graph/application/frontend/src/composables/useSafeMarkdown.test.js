import { describe, expect, it } from 'vitest'
import { useSafeMarkdown } from './useSafeMarkdown'

const { renderMarkdown, renderMarkdownInline, renderRelatedSection, renderQuestionText } = useSafeMarkdown()

describe('useSafeMarkdown', () => {
  it('空内容返回空字符串', () => {
    expect(renderMarkdown('')).toBe('')
    expect(renderMarkdown(null)).toBe('')
    expect(renderMarkdownInline(undefined)).toBe('')
  })

  it('渲染基础 markdown 为标准标签', () => {
    const html = renderMarkdown('### 标题\n\n**加粗** 与 `行内代码`\n\n- 列表项')
    expect(html).toContain('<h3')
    expect(html).toContain('<strong>加粗</strong>')
    expect(html).toContain('<code>行内代码</code>')
    expect(html).toContain('<li>列表项')
  })

  it('渲染 GFM 表格', () => {
    const html = renderMarkdown('| A | B |\n| --- | --- |\n| 1 | 2 |')
    expect(html).toContain('<table>')
    expect(html).toContain('<th>A</th>')
    expect(html).toContain('<td>1</td>')
  })

  it('渲染行内公式 $...$ 为 KaTeX 输出', () => {
    const html = renderMarkdown('设 $d_i$ 为数据元素')
    expect(html).toContain('class="katex"')
    expect(html).not.toContain('$d_i$')
  })

  it('渲染块级公式 $$...$$ 为 KaTeX display 模式', () => {
    const html = renderMarkdown('$$\nN = \\{0, \\pm1, \\pm2\\}\n$$')
    expect(html).toContain('katex-display')
  })

  it('紧贴正文的块级公式也能解析（breaks 模式回归）', () => {
    const html = renderMarkdown('定义为二元组\n$$\nD = (A, B)\n$$\n其中略')
    expect(html).toContain('katex-display')
    expect(html).not.toContain('$$')
  })

  it('引用块内的块级公式也能解析', () => {
    const html = renderMarkdown('> 形式定义为：\n> $$\n> D = (A, B)\n> $$\n> 其中：$D$ 是有限集')
    expect(html).toContain('<blockquote>')
    expect(html).toContain('katex-display')
    expect(html).not.toContain('$$')
  })

  it('代码围栏内的 $$ 不被当作公式', () => {
    const html = renderMarkdown('```c\n// price is $$x$$\n```')
    expect(html).not.toContain('katex')
  })

  it('非法 LaTeX 不抛异常（throwOnError: false）', () => {
    expect(() => renderMarkdown('$\\undefinedcmd{x}$')).not.toThrow()
  })

  it('代码块按语言高亮并带 hljs class', () => {
    const html = renderMarkdown('```c\nint main() { return 0; }\n```')
    expect(html).toContain('language-c')
    expect(html).toContain('hljs')
    expect(html).toContain('<span')
  })

  it('未知语言的代码块回退 plaintext 不报错', () => {
    const html = renderMarkdown('```unknownlang\nfoo bar\n```')
    expect(html).toContain('<pre>')
    expect(html).toContain('foo bar')
  })

  it('行内渲染不产生块级元素（quote 场景）', () => {
    const html = renderMarkdownInline('**核心** 定义 $n$ 见原文')
    expect(html).not.toContain('<p>')
    expect(html).not.toContain('<pre>')
    expect(html).toContain('<strong>核心</strong>')
    expect(html).toContain('class="katex"')
  })

  it('行内渲染折叠多行 $$ 块（引用块内公式回归）', () => {
    const html = renderMarkdownInline('> 定义为二元组\n> $$\n> D = (A, B)\n> $$\n> 其中略')
    expect(html).toContain('katex')
    expect(html).not.toContain('$$')
  })

  it('孤立的字面 $ 符号不触发公式渲染', () => {
    const html = renderMarkdownInline('特殊符号$表示字符串的结束')
    expect(html).not.toContain('katex')
    expect(html).toContain('$表示字符串的结束')
  })

  it('XSS：script 标签与事件属性被清除', () => {
    const html = renderMarkdown('<script>alert(1)</script><img src=x onerror=alert(1)>正文')
    expect(html).not.toContain('<script')
    expect(html).not.toContain('onerror')
    expect(html).toContain('正文')
  })

  it('XSS：javascript 协议链接被清除', () => {
    const html = renderMarkdown('[点我](javascript:alert(1))')
    expect(html).not.toContain('javascript:')
  })

  it('XSS：公式内容不逃逸 sanitize', () => {
    const html = renderMarkdown('$x$<iframe src="evil"></iframe>')
    expect(html).not.toContain('<iframe')
    expect(html).toContain('class="katex"')
  })

  it('related_section 的 [[id-名称]] 链接降级为纯名称', () => {
    const html = renderRelatedSection('前置：[[123-线性表]] 与 [[45-栈]]')
    expect(html).toContain('线性表')
    expect(html).toContain('栈')
    expect(html).not.toContain('[[')
  })

  it('题目文本：拍平公式重建为 KaTeX 输出', () => {
    const html = renderQuestionText('两组数列\na\n1\n∼a\nn\n(1≤n≤10\n5\n)。')
    expect(html).toContain('class="katex"')
    expect(html).not.toContain('\na\n')
  })

  it('题目文本：MC0577 的显式公式由 KaTeX 渲染且不显示 $$', () => {
    const html = renderQuestionText('例如把$$AbC$$改成$$abc$$），改过后的密语记作$$s$$。')
    expect(html).toContain('class="katex"')
    expect(html).toContain('AbC')
    expect(html).toContain('abc')
    expect(html).not.toContain('$$')
  })

  it('题目文本：纯文本被 HTML 转义且不走 markdown', () => {
    const html = renderQuestionText('比较 a<b 与 c>d，**不是加粗**')
    expect(html).toContain('a&lt;b')
    expect(html).toContain('c&gt;d')
    expect(html).toContain('**不是加粗**')
    expect(html).not.toContain('<strong>')
  })

  it('题目文本：XSS 注入被转义为纯文本而非真实标签', () => {
    const html = renderQuestionText('<img src=x onerror=alert(1)>题面')
    expect(html).not.toContain('<img')
    expect(html).toContain('&lt;img src=x onerror=alert(1)&gt;')
    expect(html).toContain('题面')
  })
})
