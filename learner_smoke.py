# -*- coding: utf-8 -*-
"""学习者模型冒烟测试 —— 不依赖 LLM，只验证画像层与 dispatch 分支。

跑：python learner_smoke.py
用临时 DB，不污染真实 learner.db。图谱裁剪部分需后端在跑（8000）才验证。
"""
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")

import config
from learner_model import LearnerModel

PASS, FAIL = "✅", "❌"


def check(cond, label, extra=""):
    print(f"{PASS if cond else FAIL} {label}{(' — ' + extra) if extra else ''}")
    return cond


def main():
    tmp = tempfile.mkdtemp(prefix="learner_smoke_")
    db = os.path.join(tmp, "test.db")
    lm = LearnerModel(db_path=db)
    sid = "smoke_student"
    th = config.MASTERY_THRESHOLD
    ok = True

    # 1) 冷启动：一条正确 → mastery == alpha
    m1 = lm.record(sid, "NODE_A", "循环", correct=True, kind="diagnose")
    ok &= check(abs(m1 - 0.4) < 1e-9, "冷启动一条正确 → mastery=0.4", f"got {m1:.3f}")

    # 2) 连续答对 3 次总能越过阈值 0.7
    lm.record(sid, "NODE_A", "循环", correct=True)
    m3 = lm.record(sid, "NODE_A", "循环", correct=True)
    ok &= check(m3 >= th, f"连对3次 → mastery≥{th}（判定为已掌握）", f"got {m3:.3f}")

    # 3) 另一个节点连续答错 → 保持薄弱
    lm.record(sid, "NODE_B", "递归", correct=False)
    mb = lm.record(sid, "NODE_B", "递归", correct=False)
    ok &= check(mb < th, "连错 → 仍薄弱", f"got {mb:.3f}")

    # 4) 画像分区正确
    prof = lm.profile(sid)
    ok &= check("NODE_A" in prof["mastered"], "画像 mastered 含 NODE_A")
    ok &= check(any(n["node_id"] == "NODE_B" for n in prof["weak"]), "画像 weak 含 NODE_B")
    ok &= check(prof["total_tracked"] == 2, "共跟踪 2 个节点", str(prof["total_tracked"]))

    # 5) mastered_ids 直接可喂 /path/plan
    mids = lm.mastered_ids(sid)
    ok &= check(mids == ["NODE_A"], "mastered_ids=['NODE_A']", str(mids))

    # 6) 事件历史可回看（反思用）
    hist = lm.history(sid)
    ok &= check(len(hist) == 5, "events 记满 5 条", str(len(hist)))

    # 7) dispatch 分支：record_result / get_student_profile 走 graph_tools
    import graph_tools
    graph_tools._learner = LearnerModel(db_path=db)  # 指向同一临时库
    import json
    r = json.loads(
        graph_tools.dispatch(
            "record_result",
            {"node_id": "NODE_A", "node_name": "循环", "correct": True},
            student_id=sid,
        )
    )
    ok &= check(r.get("ok") is True and "new_mastery" in r, "dispatch record_result 正常", str(r))
    p = json.loads(graph_tools.dispatch("get_student_profile", {}, student_id=sid))
    ok &= check(p["student_id"] == sid and "NODE_A" in p["mastered"],
                "dispatch get_student_profile 正常")

    print()
    print("全部通过 🎉" if ok else "有用例失败，见上。")
    print(f"（临时库：{db}）")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
