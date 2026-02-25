# CBT 数据字段统一后检查报告（assistant/user + content）

- 生成时间：2026-02-24 19:05:28
- 数据目录：`Psych/ab_data/cbt`
- JSON 文件数：110
- Python：`3.10.18`

## 任务目标
- 已完成字段统一：turn 字段为 `role` + `content`，role 取值为 `assistant` / `user`
- 基于统一后的数据，按更新规则检查 `session_dialogue` 与 `refined_session`
- 输出不合规样本报告（本文件与同目录 JSON 明细）

## 方法与参数（实现说明）
- 扫描范围：`Psych/ab_data/cbt/*.json`
- 检查字段：`session_dialogue`、`refined_session`
  - 字段类型应为 turn 列表（list）
  - 每个 turn 应为对象（dict），且包含 `role` 与 `content`
- `<think>` 检查细节（仅对 `role == assistant` 的 turn）：
  - `content` 中需存在至少一段可配对的 `<think>...</think>`
  - 仅检查第一段 `<think>...</think>` 内部结构
  - `<think>` 内必须且仅各出现一次并正确闭合：`assessment`、`client_state`、`skill`、`strategy`（并检查出现顺序）
- 输出：
  - 报告（Markdown）：`Psych/ab_data/check/cbt_data_check_report.md`
  - 明细（JSON）：`Psych/ab_data/check/cbt_data_check_report.json`

## 字段统一验证（Sanity Check）
- turn 中残留 `text` 键计数：0
- role 值分布（按 turn 计数）：
  - `assistant`: 5391
  - `user`: 5178

## 检查规则（更新后）
1. `role` 只能是 `assistant` 或 `user`（区分大小写）
2. 第一条与最后一条的 `role` 必须都是 `assistant`
3. `assistant` 与 `user` 必须严格交替（不允许连续相同 role）
4. 对所有 `assistant` turn：`content` 必须包含 `<think>...</think>`，且 `<think>` 内必须且仅必须各出现一次并正确闭合：
   - `<assessment>...</assessment>`
   - `<client_state>...</client_state>`
   - `<skill>...</skill>`
   - `<strategy>...</strategy>`

## 总览（按字段）
### session_dialogue
- 有问题的文件数：0/110

### refined_session
- 有问题的文件数：18/110
- 问题类型计数（出现次数统计为“文件内出现该问题类型”的次数，不是逐 turn）：
  - `alternation_break`: 18
  - `assistant_think`: 1

## 详细问题（逐文件）
> 说明：为避免刷屏，部分问题只展示前 10 个示例 turn/位置，完整细节请查看同目录 JSON：`cbt_data_check_report.json`。

### `Psych/ab_data/cbt/user_10_session_1.json`
- **refined_session**（turn 数：70）
  - `alternation_break`: break_count=1, examples=[{'idx_prev': 48, 'idx': 49, 'role': 'assistant', 'role_prev_raw': 'assistant', 'role_raw': 'assistant'}]

### `Psych/ab_data/cbt/user_10_session_2.json`
- **refined_session**（turn 数：50）
  - `alternation_break`: break_count=1, examples=[{'idx_prev': 45, 'idx': 46, 'role': 'user', 'role_prev_raw': 'user', 'role_raw': 'user'}]

### `Psych/ab_data/cbt/user_10_session_5.json`
- **refined_session**（turn 数：48）
  - `alternation_break`: break_count=1, examples=[{'idx_prev': 19, 'idx': 20, 'role': 'user', 'role_prev_raw': 'user', 'role_raw': 'user'}]

### `Psych/ab_data/cbt/user_10_session_6.json`
- **refined_session**（turn 数：60）
  - `alternation_break`: break_count=1, examples=[{'idx_prev': 53, 'idx': 54, 'role': 'user', 'role_prev_raw': 'user', 'role_raw': 'user'}]

### `Psych/ab_data/cbt/user_11_session_4.json`
- **refined_session**（turn 数：56）
  - `alternation_break`: break_count=1, examples=[{'idx_prev': 41, 'idx': 42, 'role': 'user', 'role_prev_raw': 'user', 'role_raw': 'user'}]

### `Psych/ab_data/cbt/user_12_session_5.json`
- **refined_session**（turn 数：40）
  - `alternation_break`: break_count=1, examples=[{'idx_prev': 35, 'idx': 36, 'role': 'user', 'role_prev_raw': 'user', 'role_raw': 'user'}]

### `Psych/ab_data/cbt/user_12_session_6.json`
- **refined_session**（turn 数：46）
  - `alternation_break`: break_count=1, examples=[{'idx_prev': 29, 'idx': 30, 'role': 'user', 'role_prev_raw': 'user', 'role_raw': 'user'}]

### `Psych/ab_data/cbt/user_12_session_7.json`
- **refined_session**（turn 数：44）
  - `alternation_break`: break_count=1, examples=[{'idx_prev': 31, 'idx': 32, 'role': 'user', 'role_prev_raw': 'user', 'role_raw': 'user'}]

### `Psych/ab_data/cbt/user_12_session_8.json`
- **refined_session**（turn 数：62）
  - `alternation_break`: break_count=1, examples=[{'idx_prev': 40, 'idx': 41, 'role': 'assistant', 'role_prev_raw': 'assistant', 'role_raw': 'assistant'}]

### `Psych/ab_data/cbt/user_13_session_2.json`
- **refined_session**（turn 数：60）
  - `alternation_break`: break_count=1, examples=[{'idx_prev': 52, 'idx': 53, 'role': 'assistant', 'role_prev_raw': 'assistant', 'role_raw': 'assistant'}]

### `Psych/ab_data/cbt/user_14_session_7.json`
- **refined_session**（turn 数：52）
  - `alternation_break`: break_count=1, examples=[{'idx_prev': 41, 'idx': 42, 'role': 'user', 'role_prev_raw': 'user', 'role_raw': 'user'}]
  - `assistant_think`: issue_count=1, examples=[{'idx': 51, 'errors': ['think_missing', 'think_inner_missing']}]

### `Psych/ab_data/cbt/user_16_session_1.json`
- **refined_session**（turn 数：67）
  - `alternation_break`: break_count=2, examples=[{'idx_prev': 50, 'idx': 51, 'role': 'assistant', 'role_prev_raw': 'assistant', 'role_raw': 'assistant'}, {'idx_prev': 55, 'idx': 56, 'role': 'assistant', 'role_prev_raw': 'assistant', 'role_raw': 'assistant'}]

### `Psych/ab_data/cbt/user_16_session_6.json`
- **refined_session**（turn 数：44）
  - `alternation_break`: break_count=1, examples=[{'idx_prev': 19, 'idx': 20, 'role': 'user', 'role_prev_raw': 'user', 'role_raw': 'user'}]

### `Psych/ab_data/cbt/user_19_session_1.json`
- **refined_session**（turn 数：64）
  - `alternation_break`: break_count=1, examples=[{'idx_prev': 53, 'idx': 54, 'role': 'user', 'role_prev_raw': 'user', 'role_raw': 'user'}]

### `Psych/ab_data/cbt/user_19_session_3.json`
- **refined_session**（turn 数：50）
  - `alternation_break`: break_count=1, examples=[{'idx_prev': 33, 'idx': 34, 'role': 'user', 'role_prev_raw': 'user', 'role_raw': 'user'}]

### `Psych/ab_data/cbt/user_19_session_6.json`
- **refined_session**（turn 数：56）
  - `alternation_break`: break_count=1, examples=[{'idx_prev': 41, 'idx': 42, 'role': 'user', 'role_prev_raw': 'user', 'role_raw': 'user'}]

### `Psych/ab_data/cbt/user_19_session_7.json`
- **refined_session**（turn 数：54）
  - `alternation_break`: break_count=1, examples=[{'idx_prev': 41, 'idx': 42, 'role': 'user', 'role_prev_raw': 'user', 'role_raw': 'user'}]

### `Psych/ab_data/cbt/user_1_session_2.json`
- **refined_session**（turn 数：38）
  - `alternation_break`: break_count=1, examples=[{'idx_prev': 28, 'idx': 29, 'role': 'assistant', 'role_prev_raw': 'assistant', 'role_raw': 'assistant'}]
