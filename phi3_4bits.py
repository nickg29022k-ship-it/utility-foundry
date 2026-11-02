import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

from model_paths import phi3_mini_dir

MODEL_DIR = str(phi3_mini_dir())

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",          # best default for LLMs
    bnb_4bit_compute_dtype=torch.float16, # compute in fp16 on GPU
    bnb_4bit_use_double_quant=True      # usually helps quality
)

print("Loading tokenizer...")
tok = AutoTokenizer.from_pretrained(MODEL_DIR, use_fast=True)

# stop_ids = [tok.eos_token_id]
# end_id = tok.convert_tokens_to_ids("<|end|>")
# if end_id is not None and end_id != tok.unk_token_id:
#     stop_ids.append(end_id)
# print("Stop ids:", stop_ids)

print("Loading model (4-bit)...")
model = AutoModelForCausalLM.from_pretrained(
    MODEL_DIR,
    quantization_config=bnb_config,
    device_map="auto",
    torch_dtype=torch.float16,
)

print("Loaded. Device map:", model.hf_device_map)

def generate(prompt: str, max_new_tokens: int = 80):
    print("EOS token:", tok.eos_token)
    print("EOS token id:", tok.eos_token_id)
    print("Special tokens:", tok.special_tokens_map)
    messages = [
        {"role": "system", "content": "Keep it under 200 words."},
        {"role": "system", "content": "you are a mechanical engineer."},
        {"role": "user", "content": prompt}
    ]

    # 🔑 THIS is the fix
    formatted = tok.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )

    inputs = tok(formatted, return_tensors="pt").to(model.device)
    print("\n--- Chat template preview ---")
    print(formatted)

    with torch.inference_mode():
        out = model.generate(
            **inputs,
            max_new_tokens=1024,
            do_sample=False,              # 👈 turn this off for sanity
            temperature=None,
            top_p=None,
            repetition_penalty=1.1,
            eos_token_id=tok.eos_token_id,
            # eos_token_id=stop_ids,
            pad_token_id=tok.eos_token_id,
        )

    # Decode ONLY the newly generated tokens
    gen_tokens = out[0][inputs["input_ids"].shape[1]:]
    return tok.decode(gen_tokens, skip_special_tokens=True).strip()


while True:
    p = input("\nYou: ").strip()
    if p.lower() in {"q", "quit", "exit"}:
        break
    print("\nModel:", generate(p))
