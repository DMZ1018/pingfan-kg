# 《平凡的世界》三部梗概 · 实体 / 关系 / 知识图谱 全流程

把三幅图片里的《平凡的世界》三部梗概（21 句 / 1103 字）做成一条可复现的知识抽取流水线：
**实体词典 → 三种实体抽取 → 三种关系抽取 → 两种知识图谱路线**，每一步都有金标准、有指标、有误差分析。

> 语料仅为三部梗概的转写文本，用于方法演示，不含小说原文。

## 结果速览

| 任务 | 最好方法 | 指标（micro） |
|---|---|---|
| 实体抽取 | LLM | P 1.000 / R 0.992 / **F1 0.996** |
| 实体抽取（可离线部署） | BiLSTM-CRF + 词典 | P 0.660 / R 0.516 / F1 0.579 |
| 关系抽取（粗粒度 11 类） | LLM | P 0.971 / R 1.000 / **F1 0.986** |
| 关系抽取（可离线部署） | 规则引擎 | P 0.540 / R 0.294 / F1 0.381 |
| 知识图谱 | LLM 生成 → Cypher 入库 | 52 节点 / 77 边 / 47 种关系 |

金标准：21 句、124 个实体提及（9 类）、75 条三元组（其中 10 条依赖指代消解）。

## 一条命令跑完

```bash
cd pingfan_kg
python pipeline.py --all --device cpu
```

流水线会按依赖顺序执行 13 步，自动跳过已是最新的步骤，每一步的日志写到 `out/logs/`，
产物哈希与耗时写到 `out/run_manifest.json`。

```bash
python pipeline.py --list                 # 看步骤与依赖
python pipeline.py --steps ner_eval,kg     # 只跑某几步（自动补齐依赖）
python pipeline.py --all --force           # 忽略缓存
python pipeline.py --all --device cuda     # 有 GPU 时
python pipeline.py --all --keep-going      # 某步失败继续
python pipeline.py --all --dry-run         # 只打印执行计划
```

### 流水线步骤

| 步骤 | 说明 | 产物 |
|---|---|---|
| `segment` | 语料分句 | `data/sentences.json` |
| `dict` | 构建实体词典 | `data/dict/entity_dict.{json,csv}` |
| `ner_dict` | 词典 + 规则实体抽取 | `out/pred_dict_rule.json` |
| `ner_bilstm` | BiLSTM-CRF（纯模型 / +词典特征） | `out/pred_bilstm_crf*.json` |
| `ner_bert` | BERT 实体抽取（无预训练权重则从头训练） | `out/pred_bert_scratch.json` |
| `ner_eval` | 实体抽取统一评测 | `out/metrics_ner.json` |
| `re_rules` | 规则 / spaCy 关系抽取 | `out/pred_re_spacy.json` |
| `re_bert` | BERT 关系分类 | `out/pred_re_bert.json` |
| `re_eval` | 关系抽取统一评测 | `out/metrics_re.json` |
| `kg` | 构建三张知识图谱 | `out/kg_{llm,gold,pipeline}.json` |
| `viz` | 图谱可视化 | `figures/*.png` |
| `bench` | Cypher 装载/查询基准（需 `kuzu`） | `out/kg_bench.json` |
| `report` | 重生成报告中的大表格 | `reports/*.md` |

## 目录结构

```
pingfan_kg/
├── pipeline.py                 # 流水线编排（缓存 / 计时 / 清单）
├── data/
│   ├── corpus/                 # 三部梗概原文
│   ├── sentences.json          # 分句结果
│   ├── gold/                   # 金标准：124 实体 + 75 三元组
│   ├── dict/                   # 词典：种子、JSON、CSV
│   └── llm/                    # LLM 输出与提示词
├── src/
│   ├── common.py               # 路径、加载、指标
│   ├── bilstm_crf.py           # BiLSTM-CRF（自研 CRF）
│   ├── bert_ner.py             # BERT 实体抽取
│   ├── re_rules.py             # 触发词规则
│   ├── re_spacy.py             # spaCy 管线（不可用时降级）
│   ├── re_bert.py              # BERT 关系分类
│   ├── build_kg.py             # 建图 + 导出 Cypher
│   ├── kg_cypher.py            # Kùzu 上的 Cypher 基准
│   ├── kg_neo4j.py             # Neo4j 装载
│   ├── viz.py                  # 可视化
│   └── ...
├── cypher/                     # Neo4j 装载与 7 条查询
├── tests/                      # 冒烟测试（不依赖 torch）
├── reports/                    # 四份 Markdown 报告
├── figures/                    # 图谱 PNG
└── tools/publish_github.py     # 一键发布到 GitHub（设备码授权 + Git Data API）
```

## 报告

1. [实体词典](reports/01_实体词典.md) —— 类型体系、80 词条全表、别名与指代处理
2. [实体抽取对比](reports/02_实体抽取对比.md) —— BERT / BiLSTM-CRF / LLM / 词典 四路对比
3. [关系三元组](reports/03_关系三元组.md) —— spaCy / BERT / LLM，77 条三元组全表
4. [知识图谱](reports/04_知识图谱.md) —— Neo4j/Cypher 与 LLM 两条路线，图结构与性能对比

## 环境说明（重要）

本工程在一台 **Windows + 离线白名单网络** 的机器上完成，以下三件事受限，报告中逐处标注，没有用"假装跑通"掩盖：

| 受限项 | 现象 | 替代方案 |
|---|---|---|
| HuggingFace 不可达 | 拿不到 `bert-base-chinese` | BERT 分支改为 4 层随机初始化从头训练；`--bert-dir` 可切回微调 |
| PyPI 限速 ~34 kB/s | spaCy / jieba 装不上 | 关系抽取用等价规则引擎，与 spaCy 版共用 `re_rules.py` |
| 无 Java / 无 Docker | Neo4j 服务端装不上 | 用 Kùzu 0.11 执行同一套 Cypher 并计时；`cypher/` 可直接用于 Neo4j |

另外两个坑记录在代码里：

- **DSH 沙箱 + pip**：`mkdir(mode=0o700)` 会建出当前令牌不可写的目录，而 `tempfile.mkdtemp()` 固定用 0700 → pip 必然 `EACCES`。`tools/pip_run.py` 把 `os.mkdir` 的 mode 抬到 0777 后正常。
- **Kùzu + 中文路径**：C++ 层按本地编码解析路径，`C:\Users\董铭政\...` 直接报错，只能用 `:memory:`。

## 发布到 GitHub

本机没有 git 二进制，且 `github.com` 的 HTTPS 时通时断，因此提供 API 发布脚本（设备码授权，token 不落盘）：

```bash
python tools/publish_github.py --repo pingfan-kg --public
```

已授权时可用环境变量跳过设备码：

```bash
set GITHUB_TOKEN=ghp_xxx
python tools/publish_github.py --repo pingfan-kg
```

## 已知局限

1. 语料 1103 字，5 折交叉验证每折仅 17 句训练，神经模型指标方差大（已用 3 seed 投票缓解）。
2. 金标准与 LLM 输出同源，LLM 列存在乐观偏差。
3. BERT 列是"无预训练的 BERT"，不代表预训练 BERT 的真实水平。
4. spaCy 列是"spaCy 设计的规则引擎"，不是 spaCy 本体跑出的结果。
5. 规则关系抽取没有句法，方向判断会错（见报告 3.4.1）。

## License

MIT
