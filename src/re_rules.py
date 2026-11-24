"""关系触发词/邻接规则（与具体分词器无关，spaCy 与回退引擎共用）。"""
from __future__ import annotations

import re

TRIGGERS = [
    (r"结婚|娶|嫁给|夫妻|丈夫|妻子|爱人|成亲", "夫妻", "lr"),
    (r"恋爱|相爱|爱慕|情愫|喜欢|倾心|青梅竹马|表白|女友|男友|相亲", "爱慕", "lr"),
    (r"父亲|母亲|爸爸|妈妈", "父亲", "rl"),
    (r"女儿|儿子", "父亲", "lr"),
    (r"哥哥|弟弟|姐姐|妹妹|之妹|之兄", "兄弟", "lr"),
    (r"同学|同班", "同学", "lr"),
    (r"朋友|友情|玩伴", "朋友", "lr"),
    (r"介绍|相识|邂逅|遇见", "介绍", "lr"),
    (r"任职|工作|担任|职务|主任|支书|教师|记者|工人|队长", "任职于", "lr"),
    (r"毕业|读书|就读", "就读于", "lr"),
    (r"成为|成了|当上", "成为", "lr"),
    (r"领导|组织|召开|推行|实行|推广|抵制|反对|抵触|破坏|抢水|炸山", "领导", "lr"),
    (r"帮助|救|资助|出资|通知|承认|支持", "帮助", "lr"),
    (r"揭发|说破|拒绝|批判", "揭发", "lr"),
    (r"建|经营|扩建|贷款|烧砖|制砖|生产", "经营", "lr"),
    (r"属于|隶属", "属于", "lr"),
    (r"牺牲|受伤|重伤|确诊|致残|事故|去世", "牺牲", "lr"),
    (r"到|回到|去|前往|进城|来到|远离", "到", "lr"),
]

ROLE_WORDS = {"教师", "村支书", "副主任", "记者", "建筑工人", "煤矿工人", "揽工汉", "学生",
              "工人", "冒尖户", "领头人", "技师", "县长", "徒弟", "朋友", "农民子弟", "灾民"}

# 关系 -> (头实体允许类型, 尾实体允许类型)，用于压制类型不合法的候选
TYPE_CONSTRAINTS = {
    "夫妻": ({"PER"}, {"PER"}),
    "爱慕": ({"PER"}, {"PER"}),
    "父亲": ({"PER"}, {"PER"}),
    "兄弟": ({"PER"}, {"PER"}),
    "同学": ({"PER"}, {"PER"}),
    "朋友": ({"PER"}, {"PER"}),
    "介绍": ({"PER"}, {"PER"}),
    "揭发": ({"PER"}, {"PER"}),
    "任职于": ({"PER"}, {"ORG", "LOC"}),
    "就读于": ({"PER"}, {"ORG"}),
    "成为": ({"PER"}, {"POS"}),
    "担任": ({"PER"}, {"POS"}),
    "领导": ({"PER"}, {"ORG", "POLICY", "EVENT", "LOC", "PER"}),
    "帮助": ({"PER", "ORG", "POS"}, {"PER", "ORG", "POS"}),
    "经营": ({"PER"}, {"LOC", "ORG"}),
    "牺牲": ({"PER"}, {"EVENT", "LOC", "DIS"}),
    "到": ({"PER"}, {"LOC"}),
    "属于": ({"PER"}, {"ORG"}),
}


def compatible(h_label, rel, t_label):
    if rel not in TYPE_CONSTRAINTS:
        return True
    heads, tails = TYPE_CONSTRAINTS[rel]
    return h_label in heads and t_label in tails


def apply_rules(text: str, ents):
    """ents: [(start, end, surface, label)]，按 start 升序。"""
    from common import canon

    ents = sorted([(s, e, canon(t), l) for s, e, t, l in ents], key=lambda e: e[0])
    label_of = {t: l for _, _, t, l in ents}
    triples = []
    seen = set()

    def push(h, r, t):
        if not (h and t and h != t):
            return False
        if not compatible(label_of.get(h, "UNK"), r, label_of.get(t, "UNK")):
            return False
        if (h, r, t) in seen:
            return True
        seen.add((h, r, t))
        triples.append((h, r, t))
        return True

    for i, (s1, e1, t1, l1) in enumerate(ents):
        for s2, e2, t2, l2 in ents[i + 1 : i + 3]:  # 相邻与间隔一个实体
            if s2 - e1 > 30:
                break
            mid = text[e1:s2]
            for pat, rel, direction in TRIGGERS:
                if not re.search(pat, mid):
                    continue
                h, t = (t1, t2) if direction == "lr" else (t2, t1)
                if push(h, rel, t):
                    break
            else:
                # 邻接模式：机构+职务+人名、职务+人名、机构+人名
                if s2 - e1 <= 2:
                    if l1 == "ORG" and l2 == "POS" and i + 2 < len(ents) and ents[i + 2][3] == "PER":
                        push(ents[i + 2][2], "任职于", t1)
                        push(ents[i + 2][2], "担任", t2)
                    elif l1 == "POS" and l2 == "PER" and t1 in ROLE_WORDS:
                        push(t2, "担任", t1)
                    elif l1 == "ORG" and l2 == "PER":
                        push(t2, "任职于", t1)
    return triples
