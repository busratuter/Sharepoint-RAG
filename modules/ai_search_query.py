# modules/ai_search_query.py

import os
import sys
import requests
from typing import List, Dict, Any
from dotenv import load_dotenv
from config.settings import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
    AZURE_OPENAI_API_VERSION,
    AZURE_SEARCH_ENDPOINT,
    AZURE_SEARCH_KEY,
    AZURE_SEARCH_INDEX_NAME,
    AZURE_SEARCH_API_VERSION
)

load_dotenv(override=True)

def embed_prompt(prompt: str) -> List[float]:
    """OpenAI API'sini kullanarak metni vektöre dönüştür"""
    url = f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{AZURE_OPENAI_EMBEDDING_DEPLOYMENT}/embeddings?api-version={AZURE_OPENAI_API_VERSION}"
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_OPENAI_API_KEY
    }
    data = {
        "input": prompt
    }
    
    print(f"\nOpenAI URL: {url}")
    print(f"OpenAI Headers: {headers}")
    print(f"OpenAI Data: {data}")
    
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]

def vector_search(prompt: str, top: int = 3) -> List[Dict[str, Any]]:
    """Vector arama yapar"""
    embedding = embed_prompt(prompt)

    api_version = AZURE_SEARCH_API_VERSION
    print(f"Using API version: {api_version}")
    
    url = f"{AZURE_SEARCH_ENDPOINT}/indexes/{AZURE_SEARCH_INDEX_NAME}/docs/search?api-version={api_version}"
    headers = {
        "Content-Type": "application/json", 
        "api-key": AZURE_SEARCH_KEY
    }
    
    # Payload hazırla (Basit arama için, vektör özellikleri olmadığından)
    # Yeni API olmadan vektör arama yerine basit metin araması kullanacağız
    payload = {
        "search": "*",  # Tüm dökümanları getir
        "select": "metadata_storage_name, metadata_storage_path, content",
        "top": top
    }
    
    print(f"\nAzure Search URL: {url}")
    print(f"Azure Search Headers: {headers}")
    print(f"Azure Search Payload: {payload}")
    
    # API isteğini gönder
    response = requests.post(url, headers=headers, json=payload)
    print(f"Azure Search Response Status: {response.status_code}")
    
    # Response kontrol et
    if response.status_code != 200:
        print(f"Azure Search Response Text: {response.text}")
        response.raise_for_status()
    
    # Not: Bu gerçek bir vektör araması değil, şu an sadece dökümanların alınabildiğini göstermek için
    # basit bir metin araması yapıyoruz. Gerçek vektör araması için Azure Search API sürümünü
    # 2023-07-01-Preview veya daha yüksek bir sürüme yükseltmek gerekiyor.
    print("⚠️ Bu gerçek bir vektör araması değil. API sürümü vektör aramasını desteklemiyor.")
    print("⚠️ Basit metin araması sonuçlarını getiriyoruz.")
    
    results = response.json()
    return results.get("value", [])

def simple_search(query: str, top: int = 3) -> List[Dict[str, Any]]:
    """Basit metin araması yapar"""
    # API version'u doğrudan .env'den oku
    api_version = AZURE_SEARCH_API_VERSION
    print(f"Using API version: {api_version}")
    
    # Azure Search API URL ve headers hazırla
    url = f"{AZURE_SEARCH_ENDPOINT}/indexes/{AZURE_SEARCH_INDEX_NAME}/docs/search?api-version={api_version}"
    headers = {
        "Content-Type": "application/json", 
        "api-key": AZURE_SEARCH_KEY
    }
    
    # Payload hazırla (Basit arama için)
    payload = {
        "search": query,
        "select": "metadata_storage_name, metadata_storage_path, content",
        "top": top
    }
    
    print(f"\nSimple Search URL: {url}")
    print(f"Simple Search Headers: {headers}")
    print(f"Simple Search Payload: {payload}")
    
    # API isteğini gönder
    response = requests.post(url, headers=headers, json=payload)
    print(f"Simple Search Response Status: {response.status_code}")
    
    # Response kontrol et
    if response.status_code != 200:
        print(f"Simple Search Response Text: {response.text}")
        response.raise_for_status()
    
    results = response.json()
    return results.get("value", [])
