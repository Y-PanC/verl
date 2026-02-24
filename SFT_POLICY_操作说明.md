# SFT（Supervised Fine-Tuning）Policy 模型操作说明（verl）

## 0. 任务说明

**目标**：基于本仓库现有实现，说明如何对“Policy（Actor）模型”做 SFT（监督微调），并产出可用于后续 PPO/RL 训练的模型权重。

**核心代码入口（建议先读）**：

- FSDP SFT Trainer：`verl/trainer/fsdp_sft_trainer.py`
- Engine SFT Trainer：`verl/trainer/sft_trainer.py`
- 单轮数据集（prompt/response）：`verl/utils/dataset/sft_dataset.py`
- 多轮数据集（messages/tools/多模态）：`verl/utils/dataset/multiturn_sft_dataset.py`
- 默认配置：
  - FSDP：`verl/trainer/config/sft_trainer.yaml`
  - Engine：`verl/trainer/config/sft_trainer_engine.yaml`
- checkpoint 合并/导出工具：`verl/model_merger`（文档：`docs/advance/checkpoint.rst`）

> 仓库 AGENTS.md 约定：运行 Python 命令前先 `conda activate p_verl`。本文所有示例默认在该环境下执行。

---

## 1. 选哪条 SFT 路径（推荐顺序）

### 1.1 推荐：FSDP 版一文件 Trainer（最直观）

入口：`torchrun -m verl.trainer.fsdp_sft_trainer ...`

适合：

- 你想快速把一个 HuggingFace `AutoModelForCausalLM` 做 SFT
- 单机多卡/多机 torchrun
- 希望训练逻辑、checkpoint、恢复都更“显式”

### 1.2 可选：Engine 版 Trainer（更通用、适配更多例子）

入口：`torchrun -m verl.trainer.sft_trainer ...`

适合：

- 你需要 `engine=fsdp/megatron` 这类统一配置组织方式
- 你想跑 `examples/sft/vlm` 那种脚本（多模态/更复杂配置）
- 你希望 `val_files` 可以为空（Engine Trainer 支持；FSDP Trainer 当前不支持）

---

## 2. 数据准备（Parquet 结构要求）

### 2.1 单轮（Single-turn）：`SFTDataset`

实现：`verl/utils/dataset/sft_dataset.py`

**Parquet 每行至少两列**（列名可配）：

- prompt 列：`data.prompt_key`（默认示例是 `question`）
- response 列：`data.response_key`（默认示例是 `answer`）

训练时内部拼接方式（按代码真实逻辑）：

- prompt 会被包装为 `[{role: "user", content: prompt}]`，然后 `tokenizer.apply_chat_template(..., add_generation_prompt=True)`
- response 直接拼 `response + eos_token`
- loss 仅在 response token 上计算（prompt token 会被 mask）

#### 2.1.1 列里是“嵌套 dict”的情况（常见）

如果 parquet 的某列（例如 `extra_info`）里存的是 dict：

- `extra_info = {"question": "...", "answer": "..."}`

可按 `examples/sft/gsm8k/run_gemma_2b.sh` 的方式取子字段：

- `data.prompt_key=extra_info`
- `data.prompt_dict_keys=['question']`
- `data.response_key=extra_info`
- `data.response_dict_keys=['answer']`

### 2.2 多轮（Multi-turn）：`MultiTurnSFTDataset`

实现：`verl/utils/dataset/multiturn_sft_dataset.py`

> 你的任务是“multi-turn 的心理咨询对话（纯文本）”，请直接按这一节准备数据。

**Parquet 每行至少一列 `messages`（默认列名 `messages`）**：

- `messages`：`list[dict]`，每个 dict 至少包含：
  - `role`：`"system"|"user"|"assistant"|...`
  - `content`：`str`（你的场景是纯文本，就保持字符串）

可选列（纯文本场景通常不需要）：

- `tools`：工具定义（会传给 `apply_chat_template(tools=...)`）
- `enable_thinking`：thinking 开关（会传给 `apply_chat_template(enable_thinking=...)`）

**训练/损失（loss）到底在学什么**（非常重要）：

- 只对 `role == "assistant"` 的 token 计算 loss（`user/system` 的 token 都不会被当作监督信号）
- 同一条对话里如果有多段 assistant 回复，会对每一段 assistant 回复都训练（不是只训练最后一轮）
- 会 mask 掉 assistant 片段前面的“assistant 起始前缀”（generation prompt），避免模型去拟合类似 `<|assistant|>` 的模板前缀

#### 2.2.1 角色（role）如何对应“心理咨询”语境

强烈建议你把数据规范成：

- `role="user"`：来访者（咨询对象）的发言
- `role="assistant"`：咨询师（你希望模型学到的回复）的发言
- `role="system"`：可选，但非常推荐。用来约束风格/伦理/边界（例如“你是一名专业心理咨询师…”）

如果你的原始数据用的是别的字段（例如 `speaker: therapist/client`），请在预处理阶段映射成上面的三种 role，否则训练时会“学不到你想要学的那一部分”。

一个最小示例（单条样本的 `messages` 内容）：

```json
[
  {"role": "system", "content": "你是一名专业的心理咨询师。保持共情、非评判，必要时建议寻求线下专业帮助。"},
  {"role": "user", "content": "我最近总是失眠，脑子停不下来。"},
  {"role": "assistant", "content": "听起来你这段时间压力很大。我们可以先从最近一周最困扰你的念头开始梳理……"}
]
```

#### 2.2.2 如何把原始数据保存成 Parquet（推荐：jsonl → parquet）

`MultiTurnSFTDataset` 是用 `pandas.read_parquet()` 读文件的，并且期望 `messages` 列里是真正的“嵌套结构”（list/dict），而不是把 JSON 整段当字符串塞进去。

下面给一个最常见的 jsonl 输入格式假设：每行一个样本，包含 `messages` 字段（list[dict]）。

```bash
conda activate p_verl

python - << 'PY'
import json
import random
from pathlib import Path

import pandas as pd

random.seed(42)

in_path = Path("data/raw_psych_multiturn.jsonl")      # 你的原始数据
out_dir = Path("data/psych_multiturn")               # 输出目录
out_train = out_dir / "train.parquet"
out_val = out_dir / "val.parquet"

val_ratio = 0.02

rows = []
with in_path.open("r", encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        obj = json.loads(line)
        rows.append({"messages": obj["messages"]})

df = pd.DataFrame(rows)

def is_valid_messages(messages):
    if not isinstance(messages, list) or len(messages) == 0:
        return False
    for m in messages:
        if not isinstance(m, dict):
            return False
        if "role" not in m or "content" not in m:
            return False
        if not isinstance(m["role"], str) or not isinstance(m["content"], str):
            return False
    # 至少要有一段 assistant 才有监督信号
    return any(m["role"] == "assistant" and m["content"].strip() for m in messages)

df = df[df["messages"].apply(is_valid_messages)].reset_index(drop=True)

df = df.sample(frac=1.0, random_state=42).reset_index(drop=True)
n_val = max(1, int(len(df) * val_ratio))
df_val = df.iloc[:n_val].reset_index(drop=True)
df_train = df.iloc[n_val:].reset_index(drop=True)

out_dir.mkdir(parents=True, exist_ok=True)
df_train.to_parquet(out_train, index=False)
df_val.to_parquet(out_val, index=False)

print("train:", len(df_train), "val:", len(df_val))
print("saved:", out_train, out_val)
PY
```

> 小提示：`MultiTurnSFTDataset` 内部会把 parquet 路径先过一遍 `copy_local_path_from_hdfs()`，如果你用的是 `hdfs://...` 路径可以自动拉到本地；另外它会 `assert src[-1] != '/'`，所以路径末尾不要带 `/`。

#### 2.2.3 训练前必须做的两类检查（否则容易“跑一晚上才报错”）

1) **结构检查**：确认 `messages` 真的是 list[dict]，不是字符串

```bash
conda activate p_verl

python - << 'PY'
import pandas as pd

df = pd.read_parquet("data/psych_multiturn/train.parquet")
item = df["messages"].iloc[0]
print(type(item))
print(item[:2])
PY
```

2) **长度检查**：估算 token 长度分布，决定 `data.max_length` 和 `data.truncation`

心理咨询对话通常“上下文很长”，`max_length` 过小会导致：

- `truncation=error`：直接报错停止训练（适合你先清洗/过滤超长样本）
- `truncation=left|right`：会截断一部分对话（适合你接受“截断训练”）

建议做一个小规模统计（比如抽样 200 条）：

```bash
conda activate p_verl

python - << 'PY'
import numpy as np
import pandas as pd
from transformers import AutoTokenizer

data_path = "data/psych_multiturn/train.parquet"
model_id = "Qwen/Qwen2.5-0.5B-Instruct"  # 替换成你要训练的基座模型

tok = AutoTokenizer.from_pretrained(model_id, trust_remote_code=False)
df = pd.read_parquet(data_path)

lengths = []
for msgs in df["messages"].head(200):
    ids = tok.apply_chat_template(msgs, add_generation_prompt=False, tokenize=True)
    lengths.append(len(ids))

lengths = np.array(lengths)
print("sample_n:", len(lengths))
print("max:", lengths.max())
print("p95:", int(np.quantile(lengths, 0.95)))
PY
```

经验建议：

- 如果你希望尽量不丢上下文：把 `data.max_length` 设到 `p95` 左右，再用 `truncation=error` 先清洗掉超长尾部
- 如果你接受截断：把 `data.truncation` 设成 `left`（更偏保留“对话后半段/最新上下文”）或 `right`（更偏保留开头/system 约束），两者各有取舍

#### 2.2.4 input_ids mismatch（多轮场景常见）

`MultiTurnSFTDataset` 会做一个一致性检查：逐轮 `apply_chat_template` 再拼起来的 `input_ids`，应当等于对整段 messages 一次性 `apply_chat_template` 的结果。

某些模型（尤其是带 thinking 模式/对最后一轮特殊加标签的模板）可能导致不一致：

- 你可以加：`+data.ignore_input_ids_mismatch=true`（Engine/FSDP 均可用）
- 但更推荐你先确认 tokenizer 的 chat template 行为符合预期（避免“悄悄训练了不一致的输入”）

---

## 3. 用 FSDP SFT Trainer 跑一个 Policy SFT

### 3.1 最小可跑命令（单机多卡）

```bash
conda activate p_verl

torchrun --standalone --nnodes=1 --nproc_per_node=<GPU数> \
  -m verl.trainer.fsdp_sft_trainer \
  data.train_files=<你的train.parquet> \
  data.val_files=<你的val.parquet> \
  data.prompt_key=<prompt列名> \
  data.response_key=<response列名> \
  data.max_length=2048 \
  data.truncation=error \
  data.train_batch_size=256 \
  data.micro_batch_size_per_gpu=4 \
  model.partial_pretrain=<HF模型名或本地路径> \
  trainer.default_local_dir=<输出目录> \
  trainer.project_name=<项目名> \
  trainer.experiment_name=<实验名> \
  trainer.total_epochs=1 \
  trainer.save_freq=1000 \
  trainer.test_freq=-1 \
  trainer.logger='[\"console\",\"wandb\"]'
```

注意：

- `fsdp_sft_trainer.py` 当前 **要求 `data.val_files` 是有效路径**（代码里无 `None` 分支）。不想做验证可以：
  - 仍给一个合法 `val.parquet`（可以临时指向 train）
  - 并把 `trainer.test_freq=-1`

**batch size 的真实含义（对应 `fsdp_sft_trainer.py`）**：

- `data.train_batch_size`：全局 batch（所有 DP rank 总和）
- 代码会自动做：`train_batch_size_per_rank = data.train_batch_size / dp_size`
- 每 rank 内再用 `data.micro_batch_size_per_gpu` 做梯度累积：
  - `grad_accum_steps = train_batch_size_per_rank / micro_batch_size_per_gpu`

> `fsdp_sft_trainer.py` 只使用 `data.micro_batch_size_per_gpu`，`data.micro_batch_size` 在该 Trainer 中不会生效。

### 3.2 多轮（multi-turn）心理咨询（纯文本）SFT：从 0 到 1（建议你按这一节走）

这一节默认你的数据是“心理咨询对话、纯文本、多轮”，并且你希望模型学习的是“咨询师（assistant）回复”的风格与内容。

#### 3.2.1 仓库里已有 demo 脚本（先跑通再换成你的数据）

仓库已提供可直接跑的 demo：

- `examples/sft/multiturn/run_qwen_05_sp2.sh`

它做了几件事：

- 入口：`torchrun -m verl.trainer.fsdp_sft_trainer`
- 数据：`$HOME/data/multiturn/train.parquet` / `test.parquet`
- 关键开关：`data.multiturn.enable=true`
- 模型：`Qwen/Qwen2.5-0.5B-Instruct`
- 默认只跑 1 step：`trainer.total_training_steps=1`（用于 smoke test）
- 还额外打开了 sequence parallel（`ulysses_sequence_parallel_size=2`）+ remove padding（`use_remove_padding=true`）以展示性能模式

你可以 **不改脚本文件**，直接在命令末尾追加覆盖参数（脚本里 `$@` 会透传给 Hydra），例如：

```bash
conda activate p_verl

bash examples/sft/multiturn/run_qwen_05_sp2.sh 8 checkpoints/psych-multiturn-sft \
  data.train_files=$HOME/data/psych_multiturn/train.parquet \
  data.val_files=$HOME/data/psych_multiturn/val.parquet \
  model.partial_pretrain=Qwen/Qwen2.5-7B-Instruct \
  trainer.total_training_steps=50 \
  ulysses_sequence_parallel_size=1 \
  use_remove_padding=false
```

其中：

- 第 1 个位置参数 `8`：等价于 `torchrun --nproc_per_node=8`（单机 8 卡）
- 第 2 个位置参数 `checkpoints/psych-multiturn-sft`：会传给 `trainer.default_local_dir`（checkpoint 输出目录）
- 后面的 `key=value`：Hydra 覆盖配置

> 新手强烈建议：第一次跑通时先把 `ulysses_sequence_parallel_size=1`、`use_remove_padding=false`，等数据与训练流程完全 OK 之后再开并行/去 padding 优化。

#### 3.2.2 训练前你必须准备好的东西（Checklist）

1) **环境**

- 能运行 `torchrun`
- 有可用 GPU（CUDA/NPU）
- 进入环境：`conda activate p_verl`

2) **数据**

- `train.parquet`：包含 `messages` 列（list[dict]，纯文本）
- `val.parquet`：同格式。即使你不想做验证，`fsdp_sft_trainer.py` 也会在最后一步跑验证，所以必须提供一个可读的 `val_files`

3) **基座模型**

- 推荐直接用 Instruct/Chat 模型（有 chat template）
- `model.partial_pretrain` 支持 HuggingFace repo id 或本地路径

4) **输出目录与磁盘**

- `trainer.default_local_dir` 下会按 step 生成 `global_step_<N>/` 目录
- 多卡 FSDP 的 checkpoint 会有很多分片文件，磁盘要预留空间

#### 3.2.3 一个“可复制即用”的训练脚本模板（单机多卡，纯文本）

你可以把下面内容保存为 `run_psych_multiturn_sft.sh`（放仓库根目录或任意你习惯的位置），然后直接运行。

```bash
#!/usr/bin/env bash
set -euo pipefail
set -x

if [ "$#" -lt 2 ]; then
  echo "Usage: run_psych_multiturn_sft.sh <nproc_per_node> <save_dir> [train_parquet] [val_parquet] [model_id_or_path]"
  exit 1
fi

NPROC_PER_NODE="$1"
SAVE_DIR="$2"
TRAIN_FILE="${3:-$HOME/data/psych_multiturn/train.parquet}"
VAL_FILE="${4:-$HOME/data/psych_multiturn/val.parquet}"
MODEL_ID="${5:-Qwen/Qwen2.5-0.5B-Instruct}"

torchrun --standalone --nnodes=1 --nproc_per_node="${NPROC_PER_NODE}" \
  -m verl.trainer.fsdp_sft_trainer \
  data.train_files="${TRAIN_FILE}" \
  data.val_files="${VAL_FILE}" \
  data.multiturn.enable=true \
  data.max_length=2048 \
  data.truncation=error \
  data.train_batch_size=256 \
  data.micro_batch_size_per_gpu=1 \
  optim.lr=2e-5 \
  model.partial_pretrain="${MODEL_ID}" \
  model.trust_remote_code=false \
  trainer.default_local_dir="${SAVE_DIR}" \
  trainer.project_name=psych-multiturn-sft \
  trainer.experiment_name=run-$(date +%Y%m%d-%H%M%S) \
  trainer.total_epochs=1 \
  trainer.save_freq=500 \
  trainer.test_freq=-1 \
  trainer.max_ckpt_to_keep=3 \
  trainer.logger='[\"console\"]' \
  trainer.resume_mode=auto
```

建议的“先小后大”启动方式：

- 第一次先跑通：把 `trainer.total_training_steps=1` 加上（等价于 smoke test）
- 确认不报错后再删掉 `trainer.total_training_steps`，改用 `trainer.total_epochs`

#### 3.2.4 参数逐项解释（新手必须理解）

下面按“你最可能需要改”的顺序解释参数，并说明它们为什么必要。

**A. 数据相关（`data.*`）**

- `data.train_files`：训练数据 parquet 路径（可为单个文件或列表）。你的 multi-turn 纯文本必须包含 `messages` 列。
- `data.val_files`：验证数据 parquet 路径。**FSDP SFT Trainer 会在最后一步做验证，因此必须可读**。没单独验证集时，至少先切一小份出来。
- `data.multiturn.enable=true`：告诉 Trainer 使用 `MultiTurnSFTDataset`。不设这个会走单轮 `SFTDataset`，训练目标完全不同。
- `data.max_length`：单条样本拼接后的最大 token 长度（超过会按 `data.truncation` 处理）。越大显存越吃紧（注意注意力开销通常随长度增长更快）。
- `data.truncation`：
  - `error`：超长直接报错（适合你先清洗/过滤超长样本）
  - `left`：保留右侧（对话后半段/最新上下文更完整）
  - `right`：保留左侧（system 约束/开头上下文更完整）
- `data.micro_batch_size_per_gpu`：**每张卡每次 forward/backward 的样本数**。显存不够就先降它（通常优先降到 1），再考虑降 `max_length`。
- `data.train_batch_size`：全局 batch size（所有 DP rank 加总）。代码会按 DP size 自动归一化，最终形成“每 rank batch + 梯度累积”的组合。

**B. 模型相关（`model.*`）**

- `model.partial_pretrain`：基座模型（HuggingFace repo id 或本地目录）。建议优先用带 chat template 的 Instruct 模型。
- `model.trust_remote_code`：是否信任远程代码（部分模型需要）。新手建议先 `false`，除非明确需要。
- `model.enable_gradient_checkpointing=true`（默认配置里已开）：用算力换显存，multi-turn 长上下文很常用。
- `model.strategy=fsdp|fsdp2`：FSDP 包装策略。默认 `fsdp2`，一般不需要改。
- `model.lora_rank>0`：开启 LoRA（只训练 adapter），显著省显存/更快迭代；但需要你理解“导出 adapter/合并”的流程。

**C. 优化器相关（`optim.*`）**

- `optim.lr`：学习率。SFT 常用范围随模型大小/是否 LoRA 而变；小模型全参可从 `1e-5~2e-5` 起步，LoRA 常用更大（如 `1e-4`）。
- `optim.lr_warmup_steps_ratio`：warmup 比例（默认 0.1）。新手建议保留默认，避免一上来 loss 抖动过大。
- `optim.clip_grad`：梯度裁剪。避免偶发梯度爆炸导致训练中断。

**D. 训练器/Checkpoint（`trainer.*`）**

- `trainer.default_local_dir`：checkpoint 输出根目录。最终会得到 `.../global_step_<N>/`。
- `trainer.total_epochs` / `trainer.total_training_steps`：
  - `total_epochs`：按数据集完整遍历的轮数
  - `total_training_steps`：强制训练步数（常用于 smoke test 或固定步数实验）
- `trainer.save_freq`：多少 step 保存一次（`>0` 才会周期性保存）。即使设成 `-1`，最后一步也会保存一次，但**中途断电/抢占就无法恢复到中间**，所以建议设一个正数。
- `trainer.test_freq`：多少 step 跑一次验证（`>0` 才会周期性验证）。即使设成 `-1`，FSDP Trainer 最后一步也会做一次验证。
- `trainer.max_ckpt_to_keep`：最多保留多少个 checkpoint（避免磁盘爆炸）。
- `trainer.resume_mode=auto|disable|resume_path`：断点恢复模式。新手建议 `auto`，让它自动找 `default_local_dir` 下最新的 `global_step_*`。

#### 3.2.5 训练过程中你需要做的所有工作（按时间顺序）

1) **先跑 smoke test（强烈推荐）**

- 目标：确认数据能读、tokenizer 的 chat template 正常、模型能 forward/backward、checkpoint 能写入
- 做法：加 `trainer.total_training_steps=1` 或 10

2) **根据显存调参**

- OOM：先降 `data.micro_batch_size_per_gpu` → 再降 `data.max_length` → 再考虑 LoRA
- loss 震荡大：适当降低 `optim.lr`，或增加 warmup（`optim.lr_warmup_steps_ratio`）

3) **关注 checkpoint 产物**

- 确认 `trainer.default_local_dir/global_step_<N>/` 按预期生成
- 多卡训练每个 step 目录里会有多份分片文件，属于正常现象

4) **训练完成后导出 HuggingFace 模型（用于推理/用于 PPO actor）**

- 见本文第 4 节（`verl.model_merger`）

5) **做一次“人工可读”的质量检查（必做）**

- 随机抽 20 条真实咨询问题，用导出的模型跑推理，确认风格、边界与安全性符合预期
- `val/loss` 只能反映拟合程度，不等于“咨询质量”

### 3.3 常用性能/功能开关（可选）

- Sequence Parallel（Ulysses）与 remove padding：
  - `ulysses_sequence_parallel_size=2`
  - `use_remove_padding=true`
- LoRA：
  - `model.lora_rank=32`
  - `model.lora_alpha=16`
  - `model.target_modules=all-linear`

---

## 4. 产物、恢复与导出（用于 PPO 的 Policy）

### 4.1 checkpoint 目录结构（FSDP SFT）

FSDP SFT 默认输出目录：

- `${trainer.default_local_dir}/global_step_<N>/`

内容包含：

- 每 rank 的分片模型/优化器/额外状态（由 `FSDPCheckpointManager` 保存）
- `data.pt`：`StatefulDataLoader` 的断点状态（用于 resume）

### 4.2 恢复训练（resume）

FSDP SFT Trainer 支持：

- `trainer.resume_mode=auto|disable|resume_path`
- `trainer.resume_from_path=<.../global_step_N>`

示例：

```bash
conda activate p_verl

torchrun --standalone --nnodes=1 --nproc_per_node=<GPU数> \
  -m verl.trainer.fsdp_sft_trainer \
  trainer.default_local_dir=<同一个输出目录> \
  trainer.resume_mode=resume_path \
  trainer.resume_from_path=<输出目录>/global_step_<N> \
  <其余训练参数保持一致>
```

### 4.3 PPO 侧通常需要 HuggingFace 格式模型

PPO 配置里通常用的是 HuggingFace 模型路径（例如 `actor_rollout_ref.model.path=...`），因此你一般需要把 SFT 产物导出为 HuggingFace 格式（`config.json + tokenizer + model.safetensors/...`）。

#### 方案 A：训练时就额外保存 HuggingFace 模型（体积更大）

在 SFT 启动命令中加入：

- `trainer.checkpoint.save_contents=[model,optimizer,extra,hf_model]`

这样 rank0 会在每个 `global_step_<N>/huggingface/` 下额外保存 HuggingFace 模型。

#### 方案 B：训练后用合并工具导出 HuggingFace 模型（推荐）

工具：`verl/model_merger`（详见 `docs/advance/checkpoint.rst`）

```bash
conda activate p_verl

python -m verl.model_merger merge \
  --backend fsdp \
  --local_dir <trainer.default_local_dir>/global_step_<N> \
  --target_dir <导出的HF模型目录>
```

说明：

- 如果你用了 LoRA，`model_merger` 会尝试把 LoRA adapter 导出到 `<target_dir>/lora_adapter/`
- 目前 adapter 的 `lora_alpha` 无法从 checkpoint 可靠推断，导出的 `adapter_config.json` 会把 `lora_alpha` 置为 0，需要你手动改成训练时使用的值

#### 把导出的模型用于 PPO

在 PPO 启动脚本里把 actor 的模型路径指向导出的 HF 模型目录，例如：

- `actor_rollout_ref.model.path=<导出的HF模型目录>`

参考：

- PPO 入口：`verl/trainer/main_ppo.py`
- SFT→PPO 衔接示例：`docs/examples/gsm8k_example.rst`

### 4.4 导出后如何做推理 sanity check（强烈建议做）

`val/loss` 只能说明“拟合程度”，无法保证“咨询质量/边界/安全”。SFT 跑完后，建议你至少做一次快速人工验收：

1) 准备 10～20 条真实的来访者问题（最好覆盖：情绪低落、焦虑、睡眠、亲密关系、危机等边界场景）。
2) 用导出的 HuggingFace 模型做推理，看看：
   - 是否共情、是否非评判
   - 是否避免不当医疗建议
   - 是否在高风险场景提示寻求线下专业帮助

下面是一个最小推理脚本（直接用 transformers）：

```bash
conda activate p_verl

python - << 'PY'
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

model_path = "path/to/your_exported_hf_model"  # 例如 scheme B 的 --target_dir

tok = AutoTokenizer.from_pretrained(model_path, trust_remote_code=False)
model = AutoModelForCausalLM.from_pretrained(
    model_path,
    torch_dtype=torch.bfloat16,
    device_map="auto",
)

messages = [
    {"role": "system", "content": "你是一名专业的心理咨询师。保持共情、非评判，必要时建议寻求线下专业帮助。"},
    {"role": "user", "content": "我最近总是睡不着，脑子停不下来。"},
]

inputs = tok.apply_chat_template(
    messages,
    add_generation_prompt=True,
    tokenize=True,
    return_tensors="pt",
    return_dict=True,
)
inputs = {k: v.to(model.device) for k, v in inputs.items()}

with torch.no_grad():
    output = model.generate(
        **inputs,
        max_new_tokens=256,
        do_sample=True,
        temperature=0.7,
        top_p=0.9,
    )

prompt_len = inputs["input_ids"].shape[1]
response_ids = output[0][prompt_len:]
print(tok.decode(response_ids, skip_special_tokens=True))
PY
```

---

## 5. 常见问题（按代码真实行为总结）

1) **`data.micro_batch_size` 不生效（FSDP Trainer）**

- `fsdp_sft_trainer.py` 使用的是 `data.micro_batch_size_per_gpu`
- 建议统一只设置 `data.micro_batch_size_per_gpu`

2) **`truncation=error` 报错**

- 当 token 总长 `> data.max_length` 时会报错（单轮数据集实现里显式 raise）
- 处理方式：调大 `data.max_length` 或改为 `data.truncation=left|right`

3) **多轮 messages 的 input_ids mismatch**

- 可设：`+data.ignore_input_ids_mismatch=true`
- 或检查 tokenizer 的 chat template 是否会对“最后一轮”做特殊处理（thinking tags 等）

4) **单轮数据不适合你的对话格式**

- 单轮数据集会强制把 prompt 当 user role 并自动加 generation prompt
- 需要 system/多轮对话训练时，请使用 messages 格式（多轮数据集）

---

## 6. 直接复用仓库脚本（最小改动上手）

- 单轮（GSM8K）：`examples/sft/gsm8k/run_gemma_2b.sh`、`examples/sft/gsm8k/run_qwen_05_sp2.sh`
- 多轮：`examples/sft/multiturn/run_qwen_05_sp2.sh`
- 多模态（Engine 版）：`examples/sft/vlm/run_qwen3_vl_2b.sh`
