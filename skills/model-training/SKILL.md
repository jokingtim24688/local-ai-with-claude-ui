---
name: model-training
description: Train models: LoRA/QLoRA fine-tune with Unsloth, or a small LLM from scratch.
---

# model-training

Fine-tune (LoRA/QLoRA, low VRAM): `pip install unsloth`
```python
from unsloth import FastLanguageModel
model,tok = FastLanguageModel.from_pretrained("unsloth/llama-3-8b-bnb-4bit",
    max_seq_length=2048, load_in_4bit=True)
model = FastLanguageModel.get_peft_model(model, r=16,
    target_modules=["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"],
    lora_alpha=16, use_gradient_checkpointing="unsloth")
# SFTTrainer on a jsonl {"text":...} dataset, then model.save_pretrained("out")
```
Point `model_name` at a local folder to fine-tune a downloaded model. Merge:
`save_pretrained_merged(..., save_method="merged_16bit")`.

From scratch (learn): PyTorch — tokenizer, a small transformer (embed → N decoder
blocks → LM head), cross-entropy next-token loss, AdamW, sample with temperature.
Start tiny, overfit one batch first, then scale.
