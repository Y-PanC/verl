冷启动规则作为reward训一个policy模型,跟sft模型比较

数据sft两个模型,一个是更新的reward 一个是人为设定的reward

---

## 本次实现报告（2026-02-05）：multi-turn 心理咨询 SFT 文档与脚本完善

### 1) 变更目标

- 给“多轮、纯文本、心理咨询对话”提供一份从 0 到 1 的 SFT 操作说明，让没做过 SFT 的同学也能按步骤跑通。
- 明确仓库已有 demo 脚本，并说明如何通过追加 Hydra 参数覆盖，快速替换成自己的数据/模型。

### 2) 改动点（按文件）

- `SFT_POLICY_操作说明.md`
  - 增补 multi-turn 心理咨询数据格式（messages schema）、jsonl→parquet 示例、训练前自检（结构/长度）、常见坑位说明。
  - 增补“可复制即用”的训练脚本模板与逐项参数解释（data/model/optim/trainer）。
  - 增补导出 HuggingFace 后的推理 sanity check 脚本（人工验收建议）。
- `examples/sft/multiturn/run_qwen_05_sp2.sh`
  - 将 `data.micro_batch_size` 改为 `data.micro_batch_size_per_gpu`（避免新手误用已废弃字段）。
- `verl/utils/dataset/multiturn_sft_dataset.py`
  - 兼容两类配置写法：`data.messages_key`（新结构）与 `data.multiturn.messages_key`（旧结构），同理支持 `tools_key / enable_thinking_key / ignore_input_ids_mismatch`。

### 3) 关键参数（你真正需要理解的）

- `data.multiturn.enable=true`：启用 multi-turn 数据集（否则会走单轮 SFTDataset）。
- `data.max_length` / `data.truncation`：控制长对话的长度策略（error 用于先清洗；left/right 用于接受截断训练）。
- `data.micro_batch_size_per_gpu`：显存不够时最优先调小的参数（常见先降到 1）。
- `data.train_batch_size`：全局 batch（与 DP size + 梯度累积共同决定每步更新）。
- `trainer.save_freq` / `trainer.max_ckpt_to_keep`：决定 checkpoint 频率与磁盘占用。

### 4) 建议的本地验证（最小）

```bash
conda activate p_verl
python -m compileall verl/utils/dataset/multiturn_sft_dataset.py
```
