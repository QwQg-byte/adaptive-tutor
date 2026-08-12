import { describe, expect, it } from 'vitest'
import { toMathSegments } from './questionMathText'

function joined(raw) {
  return toMathSegments(raw)
    .map((s) => (s.type === 'math' ? `⟪${s.value}⟫` : s.value))
    .join('')
}

describe('questionMathText', () => {
  it('空内容返回空数组', () => {
    expect(toMathSegments('')).toEqual([])
    expect(toMathSegments(null)).toEqual([])
  })

  it('数列下标：a\\n1\\n∼a\\nn 还原为 a_{1}∼a_{n}', () => {
    expect(joined('天数列\na\n1\n∼a\nn\n，每个数皆为正整数。')).toBe(
      '天数列⟪a_{1}⟫∼⟪a_{n}⟫，每个数皆为正整数。'
    )
  })

  it('“丫鬟的月例银”题面中的数列下标和断行被完整还原', () => {
    const raw = '现在假设荣国府一共有\nn个丫鬟，她们的月例银排成正整数序列为\na\n1\n∼a\nn\n。现在削减开支的目标，是要让这\nn个数字之和不超过\nm。'
    expect(joined(raw)).toBe(
      '现在假设荣国府一共有n个丫鬟，她们的月例银排成正整数序列为⟪a_{1}⟫∼⟪a_{n}⟫。现在削减开支的目标，是要让这n个数字之和不超过m。'
    )
  })

  it('数字指数：10\\n5 还原为 10^{5}', () => {
    expect(joined('第一行一个整数\nn(1≤n≤10\n5\n)。')).toBe(
      '第一行一个整数n(1≤n≤⟪10^{5}⟫)。'
    )
  })

  it('求和：∑\\ni=1\\nn\\na\\ni 还原为 \\sum 且相邻公式合并', () => {
    expect(joined('((∑\ni=1\nn\na\ni\n)×2)')).toBe(
      '((⟪\\sum_{i=1}^{n} a_{i}⟫)×2)'
    )
  })

  it('英文单词结尾不被误判为下标', () => {
    expect(joined('请回答odd\n或者even。')).toBe('请回答odd或者even。')
  })

  it('句末标点后的换行保留为分段', () => {
    expect(joined('第一句。\n第二句。')).toBe('第一句。\n第二句。')
  })

  it('句中断行（公式边界产生）被拼回', () => {
    expect(joined('长度均为\nn的神秘数列')).toBe('长度均为n的神秘数列')
  })

  it('空行保留为段落分隔', () => {
    expect(joined('第一段\n\n第二段')).toBe('第一段\n\n第二段')
  })

  it('无公式的普通文本原样保留', () => {
    expect(joined('一行一个字符串，表示答案。')).toBe('一行一个字符串，表示答案。')
  })

  it('显式 $$...$$ 公式转换为数学片段且不保留定界符', () => {
    expect(joined('例如把$$AbC$$改成$$abc$$，改过后的密语记作$$s$$。')).toBe(
      '例如把⟪AbC⟫改成⟪abc⟫，改过后的密语记作⟪s⟫。'
    )
  })

  it('未闭合的 $$ 作为普通文本保留', () => {
    expect(joined('字符串以$$作为标记')).toBe('字符串以$$作为标记')
  })
})
