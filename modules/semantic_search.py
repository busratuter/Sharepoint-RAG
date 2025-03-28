import json
import numpy as np
import sys
import os
from typing import List, Dict
from sklearn.metrics.pairwise import cosine_similarity
import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import (
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
    AZURE_OPENAI_API_VERSION,
    DATA_DIR,
    FILE_LIST_PATH
)

# Azure OpenAI ile metni embed et
def embed_text(text: str) -> List[float]:
    url = f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{AZURE_OPENAI_EMBEDDING_DEPLOYMENT}/embeddings?api-version={AZURE_OPENAI_API_VERSION}"
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_OPENAI_API_KEY
    }
    data = {
        "input": text
    }
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]

# Dosya listesi okunuyor
def load_file_list() -> List[Dict]:
    # Check if data directory exists
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
    
    # Check if file exists, if not create it
    if not os.path.exists(FILE_LIST_PATH):
        print(f"⚠️ '{FILE_LIST_PATH}' dosyası bulunamadı. SharePoint'ten dosya listesi alınıyor...")
        try:
            from modules.get_file_list_from_sharepoint import get_access_token, get_file_list, save_file_list_to_json
            token = get_access_token()
            file_list = get_file_list(token)
            save_file_list_to_json(file_list, FILE_LIST_PATH)
        except Exception as e:
            print(f"Dosya listesi alınamadı: {str(e)}")
            return []
    
    # Now open the file
    try:
        with open(FILE_LIST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f" Dosya okunamadı: {str(e)}")
        return []

def find_most_similar_files(prompt: str, top_k=3, threshold=0.5) -> List[Dict]:
    file_list = load_file_list()
    
    if not file_list:
        print(" İşlenecek dosya bulunamadı.")
        return []
        
    file_names = [file["name"] for file in file_list]

    print("Prompt embed ediliyor...")
    prompt_embedding = embed_text(prompt)

    print("Dosya adları embed ediliyor...")
    file_embeddings = [embed_text(name) for name in file_names]

    similarities = cosine_similarity([prompt_embedding], file_embeddings)[0]

    top_indices = np.argsort(similarities)[::-1]
    top_files = []

    for idx in top_indices:
        sim_score = float(similarities[idx])
        if sim_score < threshold:
            continue
        file = file_list[idx].copy()
        file["similarity"] = sim_score
        top_files.append(file)
        if len(top_files) == top_k:
            break

    return top_files

# Test
if __name__ == "__main__":
    user_prompt = input("Prompt gir: ")
    top_matches = find_most_similar_files(user_prompt, top_k=3, threshold=0.3)

    if not top_matches:
        print(" Prompt ile eşleşen yeterli benzerlikte dosya bulunamadı.")
    else:
        print("\n🔗 En alakalı dosyalar:")
        for i, f in enumerate(top_matches, 1):
            print(f"\n{i}. {f['name']}")
            print(f"URL: {f['web_url']}")
            print(f"Benzerlik: {f['similarity']:.4f}")
