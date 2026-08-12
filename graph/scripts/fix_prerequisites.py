"""
从 knowledge_graph_v3 的 related_section 字段解析缺失的 PREREQUISITE 关系
并补全到 knowledge_graph.json 中

支持的格式模式:
  1. ### 前置知识后 & - **[[NNN-类型-名称]]** - 描述      (第8-9章)
  2. ### 前置知识后 & - **NNN-类型-名称** - 描述          (第3-7,10章)
  3. - **前置知识**：[[NNN-名称]]（描述）                  (第11-12章，单行内)
  4. - 前置节点：[[NNN-名称]], [[NNN-名称]]               (第10章变体)
  5. - **前置概念**：[[NNN-名称]]                          (第12章变体)
  6. 前置知识**：无 / - 无特殊前置要求 / - 无特定前置要求 (跳过)
  7. **NNN-类型-名称** 中 NNN 后跟 - 分隔                  (各章通用)
  8. [[NNN-名称]] 中 NNN 后跟 - 分隔                       (各章通用)
"""
import json
import re
from pathlib import Path
from collections import defaultdict


def extract_node_ids_from_text(text: str) -> list[tuple[str, str]]:
    """
    从文本中提取所有节点引用，返回 (node_id, 描述) 列表
    支持:
      - [[310-归并排序]]  → NODE_310, 描述="归并排序"
      - [[311-2路归并]]   → NODE_311, 描述="2路归并"
      - **287-核心抽象-排序** → NODE_287, 描述="核心抽象-排序"
      - **026-核心实体-线性表** → NODE_026, 描述="核心实体-线性表"
    """
    results = []
    
    # 模式A: [[NNN-名称]] 或 [[NNN-类型-名称]]
    bracket_pattern = re.compile(r'\[\[(\d{3})(?:-[^\]]+)?\]\]')
    for m in bracket_pattern.finditer(text):
        node_num = m.group(1)
        node_id = f"NODE_{node_num}"
        # 提取整个引用文本作为描述
        full_match = m.group(0)
        # 去掉 [[ 和 ]] 
        desc = full_match[2:-2]
        results.append((node_id, desc))
    
    # 模式B: **NNN-类型-名称** 或 **NNN-名称** (不在 [[ ]] 中的)
    # 注意：要排除已被模式A匹配的部分
    bold_pattern = re.compile(r'\*\*(\d{3})-([^*]+)\*\*')
    for m in bold_pattern.finditer(text):
        node_num = m.group(1)
        node_id = f"NODE_{node_num}"
        full_match = m.group(0)
        desc = m.group(2).strip()
        # 检查是否已被模式A匹配（通过位置判断）
        start = m.start()
        # 检查是否有 [[ 在之前
        if text[max(0, start-2):start] == '[[':
            continue  # 已在 [[ ]] 中
        results.append((node_id, desc))
    
    return results


def extract_prerequisite_section(related_section: str) -> str:
    """
    从 related_section 中提取"前置知识/前置概念/前置节点"章节的内容
    返回该章节的文本，如果没有则返回空字符串
    """
    if not related_section:
        return ""
    
    # 识别前置部分的起始标记
    prereq_keywords = ['前置知识', '前置概念', '前置节点']
    
    for kw in prereq_keywords:
        idx = related_section.find(kw)
        if idx < 0:
            continue
        
        # 向前查找行首（处理同一行内如 "- **前置知识**："的情况）
        line_start = related_section.rfind('\n', 0, idx)
        if line_start < 0:
            line_start = 0
        else:
            line_start += 1
        
        # 向后查找该部分的结束位置
        # 结束标记：下一个 ### 标题、下一个 ## 标题、或者遇到非列表/非空行
        rest = related_section[line_start:]
        lines = rest.split('\n')
        
        prereq_lines = []
        in_section = False
        for line in lines:
            stripped = line.strip()
            
            # 检测是否是前置部分的行
            is_prereq_header = any(kw in stripped for kw in prereq_keywords)
            
            if not in_section and is_prereq_header:
                in_section = True
                prereq_lines.append(stripped)
                continue
            
            if not in_section:
                continue
            
            # 已经在前置部分内
            if stripped.startswith('###') or stripped.startswith('##'):
                # 遇到下一个标题，前置部分结束
                break
            
            if stripped == '' and len(prereq_lines) > 0 and prereq_lines[-1] == '':
                # 连续空行，可能结束
                # 但有时前置部分后跟空行再跟其他内容
                # 保守策略：遇到空行且下一个非空行以 ###/## 开头或不是列表项时结束
                continue
            
            prereq_lines.append(stripped)
        
        if prereq_lines:
            return '\n'.join(prereq_lines)
    
    return ""


def has_no_prerequisite(text: str) -> bool:
    """判断前置文本是否表示"没有前置知识" """
    no_pre_indicators = [
        '无（最基础概念）',
        '无特殊前置要求',
        '无特定前置要求',
        '无（最基础',
    ]
    # 移除标记和列表符号后检查
    cleaned = text.replace('**', '').replace('###', '').replace('-', '').strip()
    for indicator in no_pre_indicators:
        if indicator in cleaned:
            refs = extract_node_ids_from_text(text)
            if not refs:
                return True
    return False


def main():
    # scripts/ 在 knowledge/ 子目录下，需回退一级到 knowledge/
    base_dir = Path(__file__).resolve().parent.parent
    json_path = base_dir / 'data' / 'processed' / 'knowledge_graph_v3' / 'knowledge_graph.json'
    
    print(f"读取文件: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    entities = data.get('entities', [])
    relationships = data.get('relationships', [])
    
    # 构建节点ID集合（用于验证引用有效性）
    valid_node_ids = set()
    node_id_to_name = {}
    for e in entities:
        eid = e.get('id', '')
        valid_node_ids.add(eid)
        node_id_to_name[eid] = e.get('name', '')
    
    print(f"总实体数: {len(entities)}")
    print(f"KnowledgeNode 数: {sum(1 for e in entities if e.get('type')=='KnowledgeNode')}")
    print(f"有效节点ID数: {len(valid_node_ids)}")
    
    # 构建已有 PREREQUISITE 关系集合（避免重复）
    existing_prereq_pairs = set()
    for r in relationships:
        if r.get('type') == 'PREREQUISITE':
            pair = (r.get('source', ''), r.get('target', ''))
            existing_prereq_pairs.add(pair)
    
    print(f"已有 PREREQUISITE 关系: {len(existing_prereq_pairs)} 条")
    
    # 统计
    stats = defaultdict(lambda: {'total': 0, 'has_prereq_text': 0, 
                                  'parsed_refs': 0, 'valid_refs': 0,
                                  'new_rels': 0, 'skipped_no_prereq': 0,
                                  'skipped_existing': 0})
    
    new_relationships = []
    skipped_invalid = []
    
    # 遍历所有 KnowledgeNode
    for e in entities:
        if e.get('type') != 'KnowledgeNode':
            continue
        
        node_id = e.get('id', '')
        node_name = e.get('name', '')
        chapter_id = str(e.get('chapter_id', '?'))
        related_section = e.get('related_section', '')
        
        stats[chapter_id]['total'] += 1
        
        if not related_section:
            continue
        
        # 提取前置部分
        prereq_section = extract_prerequisite_section(related_section)
        if not prereq_section:
            continue
        
        stats[chapter_id]['has_prereq_text'] += 1
        
        # 检查是否是"无前置知识"
        if has_no_prerequisite(prereq_section):
            stats[chapter_id]['skipped_no_prereq'] += 1
            continue
        
        # 从前置部分提取节点引用
        refs = extract_node_ids_from_text(prereq_section)
        stats[chapter_id]['parsed_refs'] += len(refs)
        
        for ref_node_id, ref_desc in refs:
            # 形成标准 NODE_XXX 格式
            if not ref_node_id.startswith('NODE_'):
                ref_node_id = f"NODE_{ref_node_id}"
            
            # 验证节点是否存在
            if ref_node_id not in valid_node_ids:
                skipped_invalid.append((node_id, node_name, ref_node_id, ref_desc, chapter_id))
                continue
            
            stats[chapter_id]['valid_refs'] += 1
            
            # 检查是否已有此 PREREQUISITE 关系
            pair = (node_id, ref_node_id)
            if pair in existing_prereq_pairs:
                stats[chapter_id]['skipped_existing'] += 1
                continue
            
            # 创建新的 PREREQUISITE 关系
            # source 依赖 target（source 需要先学 target）
            new_rel = {
                "type": "PREREQUISITE",
                "source": node_id,
                "target": ref_node_id,
                "description": ref_desc
            }
            new_relationships.append(new_rel)
            existing_prereq_pairs.add(pair)  # 避免后续重复
            stats[chapter_id]['new_rels'] += 1
    
    # ====== 输出报告 ======
    print("\n" + "=" * 75)
    print("章节分析报告")
    print("=" * 75)
    print(f"{'章节':<6} {'节点':<5} {'有前置文本':<10} {'解析引用':<8} {'有效引用':<8} {'新增关系':<8} {'无前置':<6} {'已存在':<6}")
    print("-" * 75)
    
    total_new = 0
    for ch in sorted(stats.keys(), key=lambda x: (x.isdigit(), int(x) if x.isdigit() else 0, x)):
        s = stats[ch]
        total_new += s['new_rels']
        print(f"第{ch:<4}章 {s['total']:<5} {s['has_prereq_text']:<10} {s['parsed_refs']:<8} "
              f"{s['valid_refs']:<8} {s['new_rels']:<8} {s['skipped_no_prereq']:<6} {s['skipped_existing']:<6}")
    
    print("-" * 75)
    print(f"{'合计':<6} {sum(s['total'] for s in stats.values()):<5} "
          f"{sum(s['has_prereq_text'] for s in stats.values()):<10} "
          f"{sum(s['parsed_refs'] for s in stats.values()):<8} "
          f"{sum(s['valid_refs'] for s in stats.values()):<8} "
          f"{total_new:<8} "
          f"{sum(s['skipped_no_prereq'] for s in stats.values()):<6} "
          f"{sum(s['skipped_existing'] for s in stats.values()):<6}")
    
    # 输出无效引用
    if skipped_invalid:
        print(f"\n{'=' * 75}")
        print(f"无效引用（目标节点不存在），共 {len(skipped_invalid)} 个:")
        print(f"{'=' * 75}")
        for src_id, src_name, tgt_id, desc, ch in skipped_invalid[:30]:
            print(f"  [第{ch}章] {src_id}({src_name}) → {tgt_id} ({desc})")
        if len(skipped_invalid) > 30:
            print(f"  ... 还有 {len(skipped_invalid) - 30} 个")
    
    if not new_relationships:
        print("\n未有新的 PREREQUISITE 关系需要添加。数据已是最新。")
        return
    
    # ====== 确认并写入 ======
    print(f"\n{'=' * 75}")
    print(f"将新增 {len(new_relationships)} 条 PREREQUISITE 关系")
    print(f"新增后 PREREQUISITE 总数: {len(existing_prereq_pairs)}")
    print(f"{'=' * 75}")
    
    # 追加到 relationships 数组
    relationships.extend(new_relationships)
    data['relationships'] = relationships
    
    # 更新 metadata 中的关系计数
    if 'metadata' in data:
        old_count = data['metadata'].get('total_relationships', 0)
        data['metadata']['total_relationships'] = old_count + len(new_relationships)
    
    # 备份原文件
    backup_path = json_path.with_suffix('.json.bak')
    import shutil
    shutil.copy2(json_path, backup_path)
    print(f"\n已备份原文件到: {backup_path}")
    
    # 写入
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"已写入更新后的文件: {json_path}")
    print(f"\n完成！新增 {len(new_relationships)} 条 PREREQUISITE 关系。")

    # 打印一些新关系的样本
    print("\n新增关系样本（每章1条）:")
    shown_chapters = set()
    for rel in new_relationships:
        src_id = rel['source']
        # 找到源节点所在章节
        for e in entities:
            if e.get('id') == src_id:
                ch = str(e.get('chapter_id', '?'))
                if ch not in shown_chapters:
                    shown_chapters.add(ch)
                    tgt_id = rel['target']
                    tgt_name = node_id_to_name.get(tgt_id, '?')
                    src_name = e.get('name', '?')
                    print(f"  第{ch}章: {src_id}({src_name}) → PREREQUISITE → {tgt_id}({tgt_name})")
                break


if __name__ == '__main__':
    main()
