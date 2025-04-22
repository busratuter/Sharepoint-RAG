"""
RAG (Retrieval Augmented Generation) Ajanı

Bu modül, kullanıcı sorgularını alıp Azure AI Search'te semantik arama yapar
ve sonuçları LLM ile birleştirir.
"""
import os
import sys
import json
import requests
import asyncio
from typing import List, Dict, Any, Optional

# Projenin kök dizinine erişebilmek için path ayarlaması
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_API_VERSION
)

from modules.vector_search import vector_search, hybrid_search, format_search_results, sync_vector_search, sync_hybrid_search

def generate_completion(prompt: str, model_deployment: str = "gpt-4o", 
                         temperature: float = 0.7, max_tokens: int = 1000) -> str:
    """
    Azure OpenAI API ile metin tamamlama
    """
    url = f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{model_deployment}/chat/completions?api-version={AZURE_OPENAI_API_VERSION}"
    
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_OPENAI_API_KEY
    }
    
    data = {
        "messages": [
            {"role": "system", "content": "Sen yardımcı bir asistansın."},
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": 0.95,
        "frequency_penalty": 0,
        "presence_penalty": 0
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"❌ LLM API hatası: {str(e)}")
        if hasattr(e, 'response') and e.response:
            print(f"Response: {e.response.text}")
        return f"Üzgünüm, bir hata oluştu: {str(e)}"

async def rag_query(user_query: str, search_type: str = "vector", 
              top_k: int = 5, system_prompt: Optional[str] = None) -> Dict[str, Any]:
    """
    RAG (Retrieval Augmented Generation) işlemi gerçekleştirir
    """
    print(f"🔍 '{user_query}' için RAG işlemi yapılıyor...")
    
    # 1. İlgili dökümanları ara
    if search_type == "hybrid":
        search_results = await hybrid_search(user_query, top_k)
    else:  # default: vector
        search_results = await vector_search(user_query, top_k)
    
    # 2. Bulunan dökümanları birleştir
    retrieved_context = ""
    sources = []
    
    if search_results:
        for i, result in enumerate(search_results, 1):
            file_name = result.get("file_name", "Bilinmeyen Dosya")
            content = result.get("content", "")
            
            retrieved_context += f"\n---\nBelge {i}: {file_name}\n{content}\n"
            
            # Kaynakları takip et
            if file_name not in sources:
                sources.append(file_name)
    else:
        retrieved_context = "\nHiçbir ilgili belge bulunamadı."
    
    # 3. Sistem promptunu ayarla
    if system_prompt is None:
        system_prompt = """Sen bir yardımcı asistansın. Sana şirket dökümanlarından alınan bilgiler ve bir soru verilecek.
Verilen bağlam içinde bulunan bilgileri kullanarak soruya cevap ver.
Eğer cevap bağlamda yoksa, bunu belirt ve kendi bilgine dayanarak cevap verme.
Cevabında kullandığın bilgilerin hangi belgelerden geldiğini de belirt.
"""
    
    # 4. LLM promptu oluştur
    prompt = f"""{system_prompt}

BAĞLAM:
{retrieved_context}

SORU: {user_query}

Cevabında sadece bağlamda verilen bilgileri kullan. Bağlamda olmayan bir bilgi istendiyse, bunu açıkça belirt.
"""
    
    # 5. LLM'den cevap al
    completion = generate_completion(prompt)
    
    # 6. Sonuçları döndür
    return {
        "query": user_query,
        "answer": completion,
        "sources": sources,
        "search_results": search_results
    }

# Senkron wrapper fonksiyon
def sync_rag_query(user_query: str, search_type: str = "vector", 
                top_k: int = 5, system_prompt: Optional[str] = None) -> Dict[str, Any]:
    """
    RAG işlemini senkron olarak çalıştıran wrapper fonksiyon
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(rag_query(user_query, search_type, top_k, system_prompt))

async def interactive_rag():
    """
    Komut satırı üzerinden interaktif RAG deneyimi
    """
    print("=" * 50)
    print("RAG (Retrieval Augmented Generation)")
    print("=" * 50)
    print("Blob Storage dökümanları üzerinde sorgu yapabilirsiniz.")
    print("Çıkmak için 'q' veya 'exit' yazın.\n")
    
    while True:
        user_query = input("\n🔍 Soru: ")
        
        if user_query.lower() in ['q', 'exit', 'quit']:
            print("RAG sistemi kapatılıyor...")
            break
        
        if not user_query.strip():
            continue
        
        search_type = "vector"  # varsayılan arama tipi
        if user_query.startswith("/hybrid "):
            search_type = "hybrid"
            user_query = user_query[8:]  # "/hybrid " önekini kaldır
        
        # RAG işlemini gerçekleştir
        result = await rag_query(user_query, search_type=search_type)
        
        print("\n" + "=" * 50)
        print("📝 CEVAP:")
        print(result["answer"])
        
        if result["sources"]:
            print("\n📚 KAYNAKLAR:")
            for source in result["sources"]:
                print(f"- {source}")
        
        print("=" * 50)

if __name__ == "__main__":
    # asyncio.run kullanarak asenkron main fonksiyonu çalıştır
    asyncio.run(interactive_rag()) 