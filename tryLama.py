import time
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

from model_paths import phi3_mini_dir

MODEL_PATH = str(phi3_mini_dir())

print("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, local_files_only=True)

print("Loading model...")
model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH,
    dtype=torch.float16,
    device_map={"": "cuda:0"},
    local_files_only=True,
).eval()

print("Loaded. Device:", next(model.parameters()).device)

@torch.no_grad()
def generate(prompt: str, max_new_tokens: int = 64) -> str:
    t0 = time.time()
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    t1 = time.time()

    out = model.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
        do_sample=True,
        temperature=0.2,
    )
    t2 = time.time()

    text = tokenizer.decode(out[0], skip_special_tokens=True)

    print(f"[timing] tokenize={t1-t0:.2f}s, generate={t2-t1:.2f}s")
    return text


# keep your old style:
print(generate("hi"))

# now keep it alive:
while True:
    p = input("You> ")
    if p.lower() in {"exit", "quit"}:
        break
    print(generate(p))
