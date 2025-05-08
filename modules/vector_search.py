"""
Vector Search Module

Bu modül, Azure AI Search kullanarak hibrit arama işlemlerini gerçekleştirir.
"""
import os
import sys
import json
import requests
import argparse
import asyncio
from typing import List, Dict, Any, Optional, Union
import aiohttp

# Projenin kök dizinine erişebilmek için path ayarlaması
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import (
    AZURE_SEARCH_ENDPOINT,
    AZURE_SEARCH_KEY,
    AZURE_SEARCH_INDEX_NAME,
    AZURE_SEARCH_API_VERSION,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
    AZURE_OPENAI_API_VERSION
)

# Utilities ve SDK fonksiyonlarını import et
from modules.utils import async_embed_query
from modules.create_search_index_sdk import (
    create_search_index,
    delete_search_index,
    get_index_statistics as get_index_status
)

# Azure Search yapılandırması
SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT").strip('"')  # Remove quotes
SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY").strip('"')  # Remove quotes
SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX_NAME").strip('"')  # Remove quotes
API_VERSION = os.getenv("AZURE_SEARCH_API_VERSION", "2024-07-01").strip('"')  # Remove quotes

async def vector_search(query: str, top_k: int = 5, filter_condition: str = None, 
                 use_exhaustive: bool = False) -> List[Dict[str, Any]]:
    """
    Azure AI Search'te vektör tabanlı arama yapar
    
    Parameters:
    -----------
    query: str
        Arama sorgusu
    top_k: int
        Döndürülecek sonuç sayısı
    filter_condition: str
        Filtre koşulu (ör: "file_type eq 'pdf'")
    use_exhaustive: bool
        True ise Exhaustive KNN algoritması kullanılır, 
        False ise HNSW algoritması (varsayılan)
    """
    print(f"🔍 '{query}' için vektör araması yapılıyor...")
    
    try:
        # Sorguyu embed et - asenkron fonksiyon çağrısı
        query_vector = await async_embed_query(query)
        
        # AI Search URL
        url = f"{AZURE_SEARCH_ENDPOINT}/indexes/{AZURE_SEARCH_INDEX_NAME}/docs/search?api-version={AZURE_SEARCH_API_VERSION}"
        
        # API headers
        headers = {
            "Content-Type": "application/json",
            "api-key": AZURE_SEARCH_KEY
        }
        
        # Arama sorgusu - API yapısına göre "vectors" parametresi kullanılmalı
        search_query = {
            "search": "*",  # Tüm belgelerde ara
            "select": "id,file_name,chunk_id,content,file_type,last_updated",
            "top": top_k,
            "vectorQueries": [
                {
                    "vector": query_vector,
                    "fields": "content_vector",
                    "k": top_k,
                    "kind": "vector",
                    "exhaustive": use_exhaustive
                }
            ]
        }
        
        # Eğer filtre belirtilmişse ekle
        if filter_condition:
            search_query["filter"] = filter_condition
        
        # İstek ve cevabı debug için logla
        print(f"📋 API request: {json.dumps(search_query)[:500]}...")
        
        # Aramayı gerçekleştir
        response = requests.post(url, headers=headers, json=search_query)
        
        # Yanıt durumunu kontrol et
        if response.status_code != 200:
            print(f"❌ API yanıt kodu: {response.status_code}")
            print(f"❌ API yanıt içeriği: {response.text}")
            response.raise_for_status()
        
        results = response.json()
        
        # Debug: Sonuçların yapısını incele
        if results.get("value") and len(results.get("value")) > 0:
            first_result = results.get("value")[0]
            print(f"🔍 DEBUG - İlk sonuç anahtarları: {list(first_result.keys())}")
            print(f"🔍 DEBUG - İlk sonuç içeriği: {json.dumps(first_result)[:500]}...")
        else:
            print("❌ Sonuç bulunamadı")
            
        return results.get("value", [])
    
    except Exception as e:
        print(f"❌ Vektör arama hatası: {str(e)}")
        if hasattr(e, 'response') and e.response:
            print(f"❌ HTTP Status: {e.response.status_code}")
            print(f"❌ Response: {e.response.text}")
        return []

async def hybrid_search(query: str, top_k: int = 5, filter_condition: str = None,
                 use_exhaustive: bool = False, semantic_config: str = None) -> List[Dict[str, Any]]:
    """
    Metin ve vektör tabanlı hibrit arama yapar
    
    Parameters:
    -----------
    query: str
        Arama sorgusu
    top_k: int
        Döndürülecek sonuç sayısı
    filter_condition: str
        Filtre koşulu (ör: "file_type eq 'pdf'")
    use_exhaustive: bool
        True ise Exhaustive KNN algoritması kullanılır, 
        False ise HNSW algoritması (varsayılan)
    semantic_config: str
        Semantik arama konfigürasyonu (varsa)
    """
    print(f"🔍 '{query}' için hibrit arama yapılıyor...")
    
    try:
        # AI Search URL
        url = f"{AZURE_SEARCH_ENDPOINT}/indexes/{AZURE_SEARCH_INDEX_NAME}/docs/search?api-version={AZURE_SEARCH_API_VERSION}"
        
        # API headers
        headers = {
            "Content-Type": "application/json",
            "api-key": AZURE_SEARCH_KEY
        }
        
        # Arama sorgusu (metin araması)
        search_query = {
            "search": query,
            "queryType": "full",
            "searchMode": "all",
            "select": "id,file_name,chunk_id,content,file_type,last_updated",
            "top": top_k
        }
        
        # Eğer filtre belirtilmişse ekle
        if filter_condition:
            search_query["filter"] = filter_condition
        
        # İstek ve cevabı debug için logla
        print(f"📋 API request: {json.dumps(search_query)[:500]}...")
        
        # Aramayı gerçekleştir
        response = requests.post(url, headers=headers, json=search_query)
        
        # Yanıt durumunu kontrol et
        if response.status_code != 200:
            print(f"❌ API yanıt kodu: {response.status_code}")
            print(f"❌ API yanıt içeriği: {response.text}")
            response.raise_for_status()
        
        results = response.json()
        return results.get("value", [])
    
    except Exception as e:
        print(f"❌ Hibrit arama hatası: {str(e)}")
        if hasattr(e, 'response') and e.response:
            print(f"❌ HTTP Status: {e.response.status_code}")
            print(f"❌ Response: {e.response.text}")
        return []

# Senkron kullanım için yardımcı fonksiyonlar
def sync_vector_search(query: str, top_k: int = 5, filter_condition: str = None, 
                      use_exhaustive: bool = False) -> List[Dict[str, Any]]:
    """Senkron vektör arama wrapper fonksiyonu"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(vector_search(query, top_k, filter_condition, use_exhaustive))

def sync_hybrid_search(query: str, top_k: int = 5, filter_condition: str = None,
                     use_exhaustive: bool = False, semantic_config: str = None) -> List[Dict[str, Any]]:
    """Senkron hibrit arama wrapper fonksiyonu"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(hybrid_search(query, top_k, filter_condition, use_exhaustive, semantic_config))

def format_search_results(results: List[Dict[str, Any]]) -> str:
    """
    Arama sonuçlarını okunabilir bir formatta döndürür
    """
    if not results:
        return "Sonuç bulunamadı."
    
    output = "\n📄 Bulunan Dökümanlar:\n"
    for i, result in enumerate(results, 1):
        file_name = result.get("file_name", "Bilinmeyen Dosya")
        content = result.get("content", "")
        file_type = result.get("file_type", "")
        last_updated = result.get("last_updated", "")
        
        preview = content[:300] + "..." if len(content) > 300 else content
        
        output += f"\n{i}. {file_name}\n"
        output += f"   Dosya tipi: {file_type}\n" if file_type else ""
        output += f"   Son güncelleme: {last_updated}\n" if last_updated else ""
        output += f"   İçerik: {preview}\n"
        
    return output

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Azure AI Search vektör işlemleri")
    parser.add_argument("--action", type=str, choices=["search", "hybrid", "create-index", "delete-index", "status"], 
                        default="search", help="Yapılacak işlem")
    parser.add_argument("--query", type=str, help="Arama sorgusu")
    parser.add_argument("--top", type=int, default=5, help="Döndürülecek sonuç sayısı")
    parser.add_argument("--filter", type=str, help="Filtre koşulu (ör: file_type eq 'pdf')")
    parser.add_argument("--exhaustive", action="store_true", help="Exhaustive KNN algoritmasını kullan")
    parser.add_argument("--index-name", type=str, default=AZURE_SEARCH_INDEX_NAME, help="İndeks adı")
    
    args = parser.parse_args()
    
    if args.action == "create-index":
        create_search_index(args.index_name)
    elif args.action == "delete-index":
        delete_search_index(args.index_name)
    elif args.action == "status":
        get_index_status(args.index_name)
    elif args.action in ["search", "hybrid"]:
        if not args.query:
            args.query = input("Arama sorgusu girin: ")
        
        if args.action == "hybrid":
            results = sync_hybrid_search(args.query, args.top, args.filter, args.exhaustive)
        else:
            results = sync_vector_search(args.query, args.top, args.filter, args.exhaustive)
        
        print(format_search_results(results))
    else:
        print("❌ Geçersiz işlem.") 