# agent.md — Codex Agent Operating Rules (Repo-Safe)

> 目的：让代码代理在**root 权限/无 OS sandbox**等高风险环境下，仍能以“最小风险、可回滚、可审计”的方式工作。
> 适用范围：本仓库内所有自动化改动、脚本执行、依赖安装、测试运行、配置生成。
Always run python commands using `conda activate p_verl`
---

## 0) 最高优先级原则（必须遵守）

1. **不破坏**：任何操作都不得导致仓库、系统环境、关键数据不可逆损坏。
2. **最小化文件足迹 (Minimal File Footprint)**：能用一个文件解决的，绝不拆分成两个。避免创建琐碎的 `utils.py`, `consts.py`。
3. **可回滚**：改动前后必须可用 `git diff` 清晰查看；必要时提供回滚指令。
4. **可审计**：所有执行过的命令与关键输出必须记录在响应中（或写入 `logs/`）。
5. **默认拒绝危险命令**：遇到不确定风险时，选择更安全路径或停止并解释原因。
6. 每次执行任务后,都要在目录下生成任务说明和代码实现文档,说明任务实现目标、方法和代码参数.语言都默认为中文.
---

## 1) 工作目录与路径安全

- **强制工作目录**：所有命令都必须在仓库根目录执行（即包含 `.git/` 的目录）。
- **禁止跨仓库操作**：不得 `cd ..` 到仓库外，也不得写入仓库外的路径。
- **相对路径优先**：文件读写必须使用相对路径（相对 repo root）。
- **路径校验**：
  - 禁止出现 `../`、`~`、绝对路径（如 `/etc/...`、`/root/...`）用于写操作。
  - 仅允许读取系统信息（如 `uname -a`）用于排障，但不得改动系统配置。

---

## 2) 命令执行安全策略（Allow / Ask / Forbid）

### 2.1 默认允许（Allow：只读/低风险）
可直接执行（仍需在 repo root）：
- 只读查看：`pwd`, `ls`, `find`（仅仓库内）, `cat`, `sed -n`, `head`, `tail`
- Git 只读：`git status`, `git diff`, `git log`, `git show`, `git rev-parse --show-toplevel`
- 搜索：`rg`, `grep`
- 解释/格式检查：`python -m compileall`, `python -m pip show ...`（仅查看）
- 运行测试：`pytest`, `python -m pytest`, `npm test`（前提：不触发 install/网络）

> 备注：`find` 仅允许在仓库内，不允许扫描 `/` 或用户目录。

### 2.2 需要先说明理由与影响（Ask：中风险/可能改动环境）
以下操作必须先在回复里说明 **目的、影响范围、可回滚方式**，再执行：
- 依赖安装/更新：`pip install`, `npm install`, `pnpm install`, `poetry install`
- 格式化工具写入：`black`, `ruff --fix`, `prettier --write`, `go fmt`
- 生成/迁移：`alembic upgrade`, `prisma migrate`, `django migrate`
- 构建产物：`npm run build`, `make build`
- 大范围替换：`sed -i`, `perl -pi`, 批量重命名

执行后必须提供：
- 改动文件列表（`git diff --name-only`）
- 关键变更摘要
- 可回滚指令（如 `git restore ...` 或 `git checkout -- ...`）

### 2.3 严格禁止（Forbid：高风险/破坏性/越权/外联）
无论何种理由，一律不执行：
- 破坏性删除/覆盖：
  - `rm -rf`, `rm -r`, `rmdir`（除非明确限定在 `./tmp/` 且为任务必需）
  - `dd`, `mkfs`, `wipefs`, `shred`
- 权限/用户/系统修改：
  - `sudo`, `su`, `passwd`, `useradd`, `usermod`, `chmod -R`, `chown -R`
  - 修改 `/etc`, `/usr`, `/bin`, `/root` 等系统路径
- 网络外联/下载执行：
  - `curl | sh`, `wget | sh`, `bash <(curl ...)`
  - 任意形式的“远程脚本直接执行”
- 进程/服务管理：
  - `systemctl`, `service`, `kill -9`（除非明确仅终止本 agent 启动的进程且解释原因）
- 磁盘与挂载：
  - `mount`, `umount`, `fdisk`, `parted`
- 数据破坏风险：
  - 对数据库/生产环境执行写操作（除非有明确的本地 mock 环境与回滚方案）

> 若任务需要网络资源：必须改为 **“把链接写进文档/注释，让人类手动执行”** 的方式。

---

## 3) 代码改动流程（必须遵守）

### 3.1 改动前
- 先读相关文件与现状（最少必要读取），说明你将改哪里、为什么。
- 如有配置/依赖变更，先说明影响范围与回滚方式。

### 3.2 改动中
- 避免无关重排与全文件格式化。
- 保持修改小步可验证：一次只做一类变更（修 bug / 加功能 / 改配置）。

### 3.3 改动后（交付标准）
必须提供：
1. **变更摘要**（3–8 条）
2. **改动文件列表**
3. **关键 diff 片段**（只贴最关键部分，不要刷屏）
4. **本地验证命令**（可复制粘贴）
5. **回滚指令**（最少提供一种）

---

## 4)代码风格文档（基于 `代码风格示例.py`）

> **核心原则**：简洁、可读性高、可维护、模块化；保持一致的 `gpt-5` 调用方式。
> **适用范围**：本仓库所有 Python 脚本与自动化工具（如与其他规则冲突，以全局规则为准）。

### 4.1 结构与模块化
- **职责拆分**：采用 `Config` / `APIHandler` / `DataManager` / `SessionGenerator` 等职责类；业务逻辑放在 Manager/Generator 中。
- **依赖注入**：类通过 `__init__` 注入依赖，禁止在类内实例化其他业务类，避免高耦合。
- **入口统一**：只允许 `main()` 作为执行入口，并在 `if __name__ == "__main__":` 中调用。
- **单文件优先**：可在单文件内用分隔段（如 `# --- Section ---`）组织；避免碎片化 `utils.py`。

### 4.2 API 调用与 `gpt-5` 一致性
- **初始化方式**：使用 OpenAI v1.0+ 标准写法 `client = openai.OpenAI(api_key=..., base_url=...)`。
- **请求规范**：
  - `model="gpt-5"` 固定一致。
  - `messages=[{"role":"system","content":...},{"role":"user","content":...}]`。
  - 需要结构化输出时，必须指定 `response_format={"type":"json_object"}`。
  - 设置合理超时 `timeout=...`。
- **Token 审计**：记录 `response.usage`，写入日志。

### 4.3 错误处理与重试
- **Tenacity**：对外部 API 必须使用 `retry`，配置 `stop_after_attempt` + `wait_random_exponential`。
- **自定义等待策略**：为 429 设定更长退避（`custom_wait_strategy`）。
- **JSON 防御**：`json.loads` 必须捕获 `json.JSONDecodeError`；记录原始返回以便排查。
- **I/O 防御**：文件读写捕获 `FileNotFoundError` / `IOError`。

### 4.4 日志规范
- **禁止 print**：统一使用 `logging`。
- **双通道日志**：`StreamHandler` + `FileHandler`。
- **格式**：`[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s`。
- **Emoji 约定**：`✅` 成功、`⚠️/↪️` 重试、`❌/🛑` 错误、`🚀/🔍/📊/[FLOW]` 过程。

### 4.5 数据读写与格式
- **JSON 输出**：`ensure_ascii=False` + `indent=4`。
- **路径拼接**：使用 `os.path.join`，禁止字符串拼接路径。
- **深拷贝**：涉及复杂嵌套数据时使用 `copy.deepcopy()` 防止引用污染。

### 4.6 并发与线程安全
- **并发模型**：I/O 密集优先 `ThreadPoolExecutor` + `tqdm` 进度显示。
- **线程安全**：共享写入必须 `threading.Lock()`。

### 4.7 类型提示与文档
- **类型提示**：核心函数/方法必须加 Type Hints。
- **Docstrings**：对核心类/复杂方法写 Google 风格 Docstring（Args/Returns/Raises）。
- **命名清晰**：语义化变量名，避免缩写。

### 4.8 简短模板（最小骨架）
```python
import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

import openai
from tenacity import retry, stop_after_attempt, wait_random_exponential


class Config:
    API_KEY = "sk-xxx"
    BASE_URL = "http://host/v1/"
    API_MODEL = "gpt-5"
    INPUT_DIR = "input"
    OUTPUT_DIR = "output"


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("app")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s"
    )
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)
    return logger


class APIHandler:
    def __init__(self, config: Config, logger: logging.Logger) -> None:
        self._config = config
        self._logger = logger
        self._client = openai.OpenAI(
            api_key=self._config.API_KEY,
            base_url=self._config.BASE_URL,
        )

    @retry(stop=stop_after_attempt(5), wait=wait_random_exponential(min=1, max=30))
    def call(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        response = self._client.chat.completions.create(
            model=self._config.API_MODEL,
            messages=messages,
            response_format={"type": "json_object"},
            timeout=500,
        )
        self._logger.debug(f"📊 Token usage: {response.usage}")
        return json.loads(response.choices[0].message.content or "{}")


def main() -> None:
    logger = setup_logging()
    api = APIHandler(Config, logger)
    messages = [
        {"role": "system", "content": "system_prompt"},
        {"role": "user", "content": "user_prompt"},
    ]
    result = api.call(messages)
    logger.info("✅ 完成")


if __name__ == "__main__":
    main()
```

---

## 5) 测试、运行与验证

- 能跑测试就跑测试；跑不了要说明原因（缺依赖/耗时/环境限制）。
- 最低要求：
  - Python：`python -m compileall .` 或目标模块导入检查
  - Node：`npm test` / `npm run lint`（若仓库已有）
- 若新增功能：必须补最小可行的单测或提供手动验证步骤。

---

## 6) Git 纪律（强制）

- 改动前后都要 `git status` / `git diff`。
- 不执行破坏性 git 操作：
  - 禁止 `git reset --hard`（除非明确且提供理由与备份策略）
  - 禁止 `git clean -fdx`
  - 禁止改写历史（`rebase`, `push --force`）
- 允许本地提交/合并，但必须遵守：
  - 禁止直接在基础分支（如 `master`）上提交
  - 必须在独立工作分支（如 `codex/...`）上提交
  - 未经用户明确确认：禁止合并回基础分支
- 如需提交信息（建议模板，可实际使用）：
  - `feat: ...`, `fix: ...`, `chore: ...`, `docs: ...`, `refactor: ...`
- 为避免“分支过于频繁”，允许使用**常驻工作分支**来减少 `codex/` 分支数量，并用**tag 作为回滚锚点**来减少 `backup/` 分支数量：
  - 小改动/串行任务：固定使用 `codex/wip`（或按天 `codex/YYYYMMDD`）持续提交多个 commit
  - 大改动/并行任务：仍使用一次性 `codex/${TS}-${TASK_SLUG}`（每任务一个分支）
  - 回滚锚点：优先用 tag（如 `backup/<base>-<TS>`），必要时再用 `backup/` 分支（见 6.1.1）

### 6.1 每次改动的标准 Git 流程（必须照做：备份 + 分支隔离 + 确认后合并）

> 目标：原始状态可恢复、改动隔离、人工确认后再合并；仅本地 git，不做 pull/push。

#### 6.1.0 分支策略（推荐）：常驻工作分支（减少分支频率）

- **核心目标**：在不污染基础分支（如 `master`）的前提下，减少“频繁创建/切换分支”的成本，同时保持可审计与可回滚。
- **做法**：
  - 常驻工作分支默认：`codex/wip`（或按天：`codex/$(date +%Y%m%d)`）。
  - 每个小任务一个 commit；避免把多个无关改动堆到同一个 commit。
  - 合并回基础分支前：先完成最小验证（见 6.1.3），再 `git merge --no-ff`。
- **何时必须改用一次性工作分支**（每任务一个 `codex/${TS}-${TASK_SLUG}`）：
  - 需要并行推进多个任务（避免互相污染）
  - 变更跨度大/风险高（依赖安装、迁移、批量替换、重构、训练/生成大量产物）
  - 需要给某个任务单独留审计边界/回滚边界（便于 review / revert）
- **常驻分支变“臃肿”时的整理**：
  - 归档旧分支：`git branch -m codex/wip codex/wip-<TS>`
  - 从基础分支重建一个新的 `codex/wip`：`git switch <base> && git switch -c codex/wip`

#### 6.1.1 开工前（必须）：创建回滚锚点（tag/分支）+（可选）stash 备份 + 切换工作分支

```bash
# 0) 必须在仓库根目录
git rev-parse --show-toplevel

# 1) 记录基础分支（为空代表 detached HEAD，必须停止并让用户先 checkout 分支）
BASE_BRANCH="$(git branch --show-current)"
if [ -z "${BASE_BRANCH}" ]; then
  echo "🛑 当前处于 detached HEAD，请先 checkout 一个基础分支（例如 master）再继续" >&2
  exit 1
fi

# 2) 生成时间戳与任务短名（TASK_SLUG 只用 a-z0-9-，建议 ≤30 字符）
TS="$(date +%Y%m%d-%H%M%S)"
TASK_SLUG="misc"  # 由本次任务决定：例如 fix-xxx / add-yyy

# 2.1) 工作分支策略（为减少分支数量，默认使用“常驻工作分支”）
# - 常驻（推荐）：WORK_BRANCH="codex/wip"
# - 按天：WORK_BRANCH="codex/$(date +%Y%m%d)"
# - 一次性（大改动/并行任务）：WORK_BRANCH="codex/${TS}-${TASK_SLUG}"
WORK_BRANCH="codex/wip"

# 2.2) 回滚锚点策略（为减少 backup 分支数量，优先使用 tag；必要时再用分支）
ANCHOR_REF="backup/${BASE_BRANCH}-${TS}"

# 3) 记录“回滚锚点”（默认用 tag；如需分支，把下一行改为 git branch）
git tag "${ANCHOR_REF}"

# 4) 若工作区不干净：用 stash 备份“原始状态”，但立刻 apply 回来，保证工作区不变
#    -u: 包含未跟踪文件；--index: 尝试恢复暂存区状态
STASH_SHA=""
if [ -n "$(git status --porcelain)" ]; then
  git stash push -u -m "pre-codex ${TS} ${TASK_SLUG}"
  STASH_SHA="$(git rev-parse stash@{0})"
  git stash apply --index "stash@{0}" || { echo "🛑 stash apply 失败，请人工处理冲突后再继续" >&2; exit 1; }
fi

# 5) 切换到工作分支（后续所有提交都只能在这个分支上）
if git show-ref --verify --quiet "refs/heads/${WORK_BRANCH}"; then
  git switch "${WORK_BRANCH}"
else
  git switch -c "${WORK_BRANCH}"
fi

# 5.1)（可选）把基础分支合并到工作分支，减少最终合并冲突（如冲突需人工处理）
# git merge "${BASE_BRANCH}"

# 6) 记录关键信息（必须在回复里写清 BASE/ANCHOR/WORK；如有 stash 也要写 STASH_SHA）
echo "[FLOW] BASE_BRANCH=${BASE_BRANCH}"
echo "[FLOW] ANCHOR_REF=${ANCHOR_REF}"
echo "[FLOW] WORK_BRANCH=${WORK_BRANCH}"
if [ -n "${STASH_SHA}" ]; then
  echo "[FLOW] STASH_SHA=${STASH_SHA}"
fi
git status -sb
```

#### 6.1.2 改动中（必须）：提交策略（避免误提交日志/产物）

- 禁止 `git add .` / `git add -A`（容易把产物、日志、缓存误提交）。
- 默认使用 `git add -u`：只暂存“已跟踪文件”的修改/删除。
- 新增文件必须显式 `git add path/to/file`（只加你确定要纳入版本控制的文件）。
- 每次提交前后都要 `git diff` / `git status -sb`，并在回复里记录 commit sha。

```bash
git diff
git add -u
# 新增文件示例：git add path/to/new_file.py
git commit -m "feat: <简短说明>"
git status -sb
```

#### 6.1.3 完成后（必须）：验证 + 提交审核材料（未经确认不合并）

- 在工作分支上跑最小验证（例如：`python -m compileall .` 或 `pytest`，按仓库实际情况）。
- 给用户提供审核材料：
  - `git diff --stat "${BASE_BRANCH}..${WORK_BRANCH}"`
  - `git log --oneline "${BASE_BRANCH}..${WORK_BRANCH}"`
- 未经用户明确确认：禁止执行 merge。

#### 6.1.4 用户确认后：合并回基础分支（固定使用 --no-ff）

```bash
git switch "${BASE_BRANCH}"
git merge --no-ff "${WORK_BRANCH}"
git status -sb
```

#### 6.1.5 清理（可选，需用户确认）：删除工作分支/备份/清理 stash

```bash
# 一次性工作分支：可删除（失败则说明未合并或有问题，先不要强删）
# git branch -d "${WORK_BRANCH}"

# 常驻工作分支：通常不删除；如需整理，建议归档（重命名）而不是强删
# git branch -m "${WORK_BRANCH}" "${WORK_BRANCH}-${TS}"

# 如确认不再需要回滚锚点，再删除 tag 与 stash（tag 不会自动推送，是否保留由人类决定）
# git tag -d "${ANCHOR_REF}"
# stash 可能不是最新的，请优先用 STASH_SHA 定位；示例以 stash@{0} 表示“最近一次 stash”
git stash drop "stash@{0}"
```

### 6.2 回滚（必须会用，禁止 reset --hard）

- 如果已经合并：优先用 `git revert` 回滚 merge commit（可审计、可回放）。

```bash
git log --oneline --merges -n 10
git revert -m 1 <merge_commit_sha>
```

- 如果需要回到“开工前”查看/恢复：可以直接切到备份分支或应用 stash
  - `git switch --detach <backup_tag>`（若 6.1.1 使用 tag 作为锚点）
  - `git switch <backup_branch>`（若你使用的是 `backup/` 分支）
  - `git stash list` 然后 `git stash apply <stash_ref 或 STASH_SHA>`

---

## 7) 生成文件与目录约定

- **避免文件碎片化**：除非必要，不要创建 `temp_script_1.py` 这种临时命名文件。
- 自动生成/临时产物统一放：
  - `tmp/` 或 `artifacts/` 或 `logs/`（若存在则沿用）。
- **清理原则**：如果生成的脚本是临时的，任务结束后应提供删除指令。

---

## 8) 响应输出格式（给人类审查用）

每次交付按以下结构输出（除非用户要求其他格式）：

- **Plan**：你准备做什么（简短）
- **Commands**：你执行了哪些命令（逐条列出）
- **Changes**：
  - Summary（要点）
  - Files changed（列表）
  - Key diff snippets（关键片段）
- **Validation**：测试/运行结果
- **Rollback**：如何恢复到改动前

---

## 9) 任务边界与拒绝策略

- 如果用户请求包含高风险指令（删库/提权/外联下载执行等），必须拒绝并给安全替代方案：
  - 改为只输出“建议的人类手动步骤”
  - 或提供可审计、可回滚的等价实现（例如仅生成脚本，不执行）

---

## 10) “安全替代”常用模板

- 删除需求 → 改为移动到 `tmp/trash/`，并提示人工确认后再删除
- 远程脚本执行 → 改为下载到本地文件、展示校验和、让人类手动执行
- 系统改动 → 改为在仓库内提供配置示例与文档说明

---

**End of agent.md**
