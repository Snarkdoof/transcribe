# pip install git+https://github.com/huggingface/transformers.git

import requests
from PIL import Image
import sys
import requests

from transformers import AutoProcessor, Blip2ForConditionalGeneration
import torch

processor = AutoProcessor.from_pretrained("Salesforce/blip2-opt-2.7b")
model = Blip2ForConditionalGeneration.from_pretrained("Salesforce/blip2-opt-2.7b", torch_dtype=torch.float32)
device = "cuda:1" if torch.cuda.is_available() else "cpu"
device = "cpu"
model.to(device)

def get_description(url, prompt=""):
    if url.startswith("http"):
        image = Image.open(requests.get(url, stream=True).raw).convert('RGB')  
    else:
        image = Image.open(url).convert('RGB')  # file

    inputs = processor(image, return_tensors="pt", text=prompt)
    generated_ids = model.generate(**inputs, max_new_tokens=120)
    generated_text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
    return generated_text


for url in sys.argv[1:]:
    try:
        generated_text = get_description(url)
        print(url+ ":\n ", generated_text)
    except Exception as e:
        print(url + ":\n failed!", e)
