# 如何把本工程上传到 GitHub

三种方式，按"是否愿意装东西"排序。仓库已经建好：
<https://github.com/DMZ1018/pingfan-kg>（当前是空的）。

---

## 方式 A：网页拖拽（不装任何东西，推荐）

1. 解压 `pingfan-kg.zip`，得到 `pingfan-kg/` 文件夹。
2. 浏览器打开 <https://github.com/DMZ1018/pingfan-kg/upload/main>
3. 打开解压后的 `pingfan-kg/`，**全选里面的内容**（不是选文件夹本身），拖进网页的上传区域。
   - 目录结构会被保留（`src/`、`data/`、`reports/`…）。
   - 如果直接把 `pingfan-kg` 文件夹拖进去，会多出一层 `pingfan-kg/pingfan-kg/`，需要避免。
4. 底部 Commit message 填：`feat: 端到端知识抽取流水线`，点 **Commit changes**。

上传约 73 个文件、1.9 MB，Chrome / Edge 都支持文件夹拖拽。上传完刷新仓库首页即可看到 README。

> 如果提示"文件数超过 100"，分两次拖：先拖 `README.md`、`LICENSE`、`pipeline.py` 等根目录文件，
> 再拖 `data/`、`src/`、`reports/` 等目录。

---

## 方式 B：Git 命令（需要先装 Git for Windows）

```powershell
# 1. 安装：https://git-scm.com/download/win  或  winget install Git.Git
# 2. 解压 zip 后进入目录
cd pingfan-kg

git init -b main
git add .
git commit -m "feat: 端到端知识抽取流水线"
git remote add origin https://github.com/DMZ1018/pingfan-kg.git
git push -u origin main
```

首次 push 会弹出浏览器让你登录 GitHub（Git Credential Manager 自动处理，不需要手输密码）。
之后改动用 `git add . && git commit -m "..." && git push` 即可。

---

## 方式 C：用仓库里的发布脚本（不需要 git）

需要一次性 token（classic，勾 `repo` 权限）：<https://github.com/settings/tokens/new?scopes=repo&description=pingfan-kg>

```powershell
cd pingfan_kg
$env:GITHUB_TOKEN="ghp_xxxxxxxx"       # 只在本进程有效
python tools\publish_github.py --repo pingfan-kg --public
```

脚本会：建仓库（已存在则复用）→ 逐文件上传 → 一次 commit → 推送分支。
token 不写盘，进程结束即失效；用完记得在 GitHub 上 revoke。

---

## 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| 网页上传后多一层目录 | 拖了文件夹本身 | 删掉重传，拖文件夹里的内容 |
| `git push` 卡住/超时 | 本机到 github.com 的 HTTPS 不稳定 | 换手机热点，或用方式 A |
| 上传后 Action 失败 | CI 需要 `requirements-ci.txt` | 正常，仓库里已包含该文件 |
| 误传了 `libs/` | 用了方式 B 且没加 `.gitignore` | 仓库里已带 `.gitignore`，正常不会发生 |

## 上传后建议

- 仓库 Settings → 把 Description 填上：`《平凡的世界》梗概的实体/关系/知识图谱全流程`
- About → 勾选 README 自动展示
- 如果想删掉当前这个空仓库：Settings → 最底部 Delete this repository
