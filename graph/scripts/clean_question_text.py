# -*- coding: utf-8 -*-
"""
clean_question_text.py —— 清洗题目文本中的私有区乱码字符

码蹄集网站用私有字体把 U+E020 + "=" 渲染为 ≠（不等号），爬取数据原样保留了
该私有字符，普通浏览器显示为乱码方块。本脚本将其还原为标准的 ≠ 字符，
并顺带清除其他私有区（U+E000-F8FF）和替换符（U+FFFD）字符。

用法:
    python scripts/clean_question_text.py           # 干跑预览
    python scripts/clean_question_text.py --apply   # 写入（自动备份）

写入后需重建数据库: python import_data.py
"""
import json
import re
import sys
import shutil
import argparse
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8')
    except Exception:
        pass

MATIJI = Path(__file__).parent.parent / 'data' / 'processed' / 'matiji_knowledge_graph.json'

# U+E020（斜线覆盖）+ 可选空白 + "=" → ≠
NEQ_PAT = re.compile('\\s*=')
# 兜底：清除残余私有区字符和替换符
PUA_PAT = re.compile('[-�]')


def clean(text: str):
    fixed = NEQ_PAT.sub('≠', text)
    fixed = PUA_PAT.sub('', fixed)
    return fixed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='实际写入（默认干跑）')
    args = ap.parse_args()

    data = json.load(open(MATIJI, encoding='utf-8'))
    neq_count = pua_count = 0
    touched = []
    for e in data['entities']:
        for k, v in e.items():
            if not isinstance(v, str):
                continue
            n1 = len(NEQ_PAT.findall(v))
            fixed = NEQ_PAT.sub('≠', v)
            n2 = len(PUA_PAT.findall(fixed))
            fixed = PUA_PAT.sub('', fixed)
            if fixed != v:
                neq_count += n1
                pua_count += n2
                touched.append((e.get('id'), e.get('name', '')[:20], k))
                if args.apply:
                    e[k] = fixed

    print(f"≠ 还原: {neq_count} 处 | 其他私有区字符清除: {pua_count} 处 | 涉及字段: {len(touched)} 个")
    for t in touched:
        print('  ', *t)

    if not args.apply:
        print("\n[dry-run] 未写入。执行 --apply 生效，然后 python import_data.py")
        return

    shutil.copy2(MATIJI, MATIJI.with_suffix('.json.bak'))
    json.dump(data, open(MATIJI, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f"\n[完成] 已写入 {MATIJI}（备份 .bak）")
    print("下一步：python import_data.py")


if __name__ == '__main__':
    main()
