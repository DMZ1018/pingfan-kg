"""替换总报告末尾的发布章节（按标题定位，避免空白字符不匹配）。"""
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "reports" / "00_全流程总报告.md"
lines = p.read_text(encoding="utf-8").splitlines()
idx = next(i for i, ln in enumerate(lines) if ln.startswith("### 9.3"))
new = """### 9.3 发布

- 本地发布包：`release/pingfan-kg/` 与 `release/pingfan-kg.zip`（77 个文件，2.0 MB），已排除 `libs/`、日志、凭据。
- GitHub 仓库 `DMZ1018/pingfan-kg` 已创建，当前为空。
- 上传步骤见 `UPLOAD.md`：网页拖拽（无需安装任何工具）、git 命令、或 `tools/publish_github.py`（token）。
- 上传受阻的原因（网络白名单、设备码过期、空仓库 409）见 7.2 第 4 条。""".splitlines()
p.write_text("\n".join(lines[:idx] + new) + "\n", encoding="utf-8")
print("ok, tail:")
print("\n".join((lines[:idx] + new)[-5:]))
