#!/usr/bin/env python
"""
Azure OpenAI Embedding modeli kullanarak benzerlik araması yapan ajan

Bu script, Azure OpenAI Embedding modeli kullanarak SharePoint dosyaları için
benzerlik araması yapar.
"""
import os
import sys
import json
import argparse
import time
import numpy as np
import asyncio
from typing import List, Dict, Any, Optional, Tuple

# Projenin kök dizinine erişebilmek için path ayarlaması
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Gerekli modülleri import et
from modules.get_file_list_from_sharepoint import get_access_token, get_file_list, save_file_list_to_json
from modules.utils import async_embed_query
from config.settings import (
    DATA_DIR, 
    FILE_LIST_PATH,
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
    AZURE_OPENAI_API_VERSION
)

def load_file_list(file_path=FILE_LIST_PATH) -> List[Dict[str, Any]]:
    """
    SharePoint dosya listesini yükler
    
    Parameters:
    -----------
    file_path: str
        Dosya listesinin bulunduğu JSON dosyasının yolu
        
    Returns:
    --------
    List[Dict[str, Any]]
        SharePoint dosya listesi
    """
    try:
        if not os.path.exists(file_path):
            print(f"⚠️ Dosya listesi bulunamadı: {file_path}")
            print("Lütfen 'python similarity_agent_embedding.py --update-files' komutunu çalıştırın.")
            return []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            file_list = json.load(f)
            print(f"✅ {len(file_list)} dosya yüklendi.")
            return file_list
    except Exception as e:
        print(f"❌ Dosya listesi yüklenirken hata: {str(e)}")
        return []

def update_file_list():
    """SharePoint'ten dosya listesini günceller"""
    try:
        # SharePoint'ten dosya listesini al
        token = get_access_token()
        files = get_file_list(token)
        
        # Dosya listesini kaydet
        save_file_list_to_json(files)
        print(f"✅ {len(files)} dosya listelendi ve '{FILE_LIST_PATH}' dosyasına kaydedildi.")
        
        return True
    except Exception as e:
        print(f"❌ Dosya listesi güncellenirken hata: {str(e)}")
        return False

def cosine_similarity(vec1, vec2):
    """İki vektör arasında kosinüs benzerliği hesaplar"""
    dot_product = np.dot(vec1, vec2)
    norm_vec1 = np.linalg.norm(vec1)
    norm_vec2 = np.linalg.norm(vec2)
    
    # Sıfıra bölünmeyi önle
    if norm_vec1 == 0 or norm_vec2 == 0:
        return 0
    
    similarity = dot_product / (norm_vec1 * norm_vec2)
    return similarity

def determine_threshold(similarity_scores: List[float]) -> float:
    """
    Benzerlik skorlarına bakarak otomatik eşik değeri belirler
    
    Parameters:
    -----------
    similarity_scores: List[float]
        Benzerlik skorları listesi
    
    Returns:
    --------
    float
        Otomatik belirlenen eşik değeri
    """
    # Skorlar boşsa varsayılan değer döndür
    if not similarity_scores:
        return 0.3  # Varsayılan değeri düşürdük
    
    # Skorları büyükten küçüğe sırala
    sorted_scores = sorted(similarity_scores, reverse=True)
    score_count = len(sorted_scores)
    
    # Az sayıda sonuç varsa
    if score_count <= 2:
        return max(0.2, sorted_scores[-1] * 0.9)
    
    # En yüksek iki skor arasında büyük fark varsa
    top_diff = sorted_scores[0] - sorted_scores[1]
    if top_diff > 0.2:  # Embedding modeli için daha düşük fark eşiği
        return sorted_scores[1] * 0.9
    
    # İstatistiksel hesaplama
    mean = np.mean(similarity_scores)
    stdev = np.std(similarity_scores) if score_count > 1 else 0.1
    
    # Eşik değerini hesapla ve sınırlandır
    threshold = mean - (0.5 * stdev)
    
    # Minimum eşik değerini düşürdük (0.5 -> 0.2)
    return max(0.2, min(threshold, 0.85))

def async_to_sync(async_func, *args, **kwargs):
    """
    Asenkron bir fonksiyonu senkron olarak çalıştırır
    """
    try:
        # Python 3.7+ için
        return asyncio.run(async_func(*args, **kwargs))
    except (AttributeError, RuntimeError):
        # Eski Python sürümleri veya mevcut bir event loop varsa
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(async_func(*args, **kwargs))
        loop.close()
        return result

def get_embedding_similarity(query: str, file_names: List[str]) -> List[Dict[str, Any]]:
    """
    Embedding modeli kullanarak benzerlik skorlarını hesaplar
    
    Parameters:
    -----------
    query: str
        Arama sorgusu
    file_names: List[str]
        Dosya adları listesi
        
    Returns:
    --------
    List[Dict[str, Any]]
        Benzerlik skorları ile birlikte dosya bilgileri
    """
    try:
        print(f"🔄 '{query}' sorgusu için embedding oluşturuluyor...")
        # Sorgu embeddingini hesapla
        query_embedding = async_to_sync(async_embed_query, query)
        
        print(f"🔄 Dosya adları için embeddingler oluşturuluyor...")
        # Her dosya adı için embedding hesapla
        similarity_results = []
        
        for i, file_name in enumerate(file_names):
            # Dosya adı embeddingini hesapla
            file_embedding = async_to_sync(async_embed_query, file_name)
            
            # Benzerlik skorunu hesapla
            similarity = cosine_similarity(query_embedding, file_embedding)
            similarity_results.append({
                "file_name": file_name,
                "similarity_score": float(similarity)
            })
            
            # İlerleme göster
            if (i + 1) % 5 == 0 or i == len(file_names) - 1:
                print(f"  ⏳ İlerleme: {i+1}/{len(file_names)}")
        
        # Benzerlik puanına göre azalan sıralama yap
        similarity_results.sort(key=lambda x: x["similarity_score"], reverse=True)
        
        return similarity_results
    
    except Exception as e:
        print(f"❌ Embedding benzerlik hesaplama hatası: {str(e)}")
        return []

def similarity_search(query: str, threshold: float = None, top_k: int = 5, auto_threshold: bool = True) -> List[Dict[str, Any]]:
    """
    Embedding modeli kullanarak dosya isimlerinde benzerlik araması yapar
    
    Parameters:
    -----------
    query: str
        Arama sorgusu
    threshold: float
        Benzerlik eşik değeri (0-1 arası). None ise otomatik belirlenir.
    top_k: int
        Dönecek maksimum sonuç sayısı
    auto_threshold: bool
        Eşik değerinin otomatik belirlenip belirlenmeyeceği
        
    Returns:
    --------
    List[Dict[str, Any]]
        Benzerlik skorlarına göre sıralanmış sonuç listesi
    """
    # Dosya listesini yükle
    files = load_file_list()
    if not files:
        return []
    
    # Sadece dosya adlarını al
    file_names = [file.get("name", "") for file in files if file.get("name")]
    print(f"🔍 '{query}' sorgusu için {len(file_names)} dosya adı üzerinde benzerlik araması yapılıyor...")
    
    # Embedding ile benzerlik skorlarını hesapla
    similarity_results = get_embedding_similarity(query, file_names)
    
    # Sonuç yoksa boş liste döndür
    if not similarity_results:
        return []
    
    # Eşik değerini belirle
    similarity_scores = [item["similarity_score"] for item in similarity_results]
    actual_threshold = threshold
    
    if auto_threshold or threshold is None:
        actual_threshold = determine_threshold(similarity_scores)
        print(f"🔍 Otomatik eşik değeri: {actual_threshold:.3f}")
    else:
        print(f"🔍 Kullanılan eşik değeri: {actual_threshold:.3f}")
    
    # Eşik değerinden yüksek sonuçları filtrele
    filtered_results = []
    for result in similarity_results:
        if result["similarity_score"] >= actual_threshold:
            # Eşleşen dosyanın tam bilgilerini bul
            file_info = next((f for f in files if f.get("name") == result["file_name"]), None)
            if file_info:
                filtered_results.append({
                    "file_name": result["file_name"],
                    "similarity_score": result["similarity_score"],
                    "web_url": file_info.get("web_url", ""),
                    "created_date": file_info.get("created_date", ""),
                    "last_modified": file_info.get("last_modified", "")
                })
    
    # En fazla top_k kadar sonuç döndür
    return filtered_results[:top_k]

def format_results(query: str, results: List[Dict[str, Any]]) -> str:
    """
    Benzerlik sonuçlarını formatlar
    
    Parameters:
    -----------
    query: str
        Arama sorgusu
    results: List[Dict[str, Any]]
        Benzerlik sonuçları
        
    Returns:
    --------
    str
        Formatlanmış sonuç metni
    """
    if not results:
        return f"❌ '{query}' sorgusu için sonuç bulunamadı."
    
    output = f"## '{query}' sorgusu için {len(results)} sonuç bulundu:\n\n"
    
    for idx, result in enumerate(results, 1):
        score_percent = round(result["similarity_score"] * 100, 2)
        output += f"{idx}. {result['file_name']} (Benzerlik: %{score_percent})\n"
        output += f"   URL: {result.get('web_url', 'Belirtilmemiş')}\n"
        output += f"   Son Değişiklik: {result.get('last_modified', 'Belirtilmemiş')}\n\n"
    
    return output

def interactive_search():
    """
    Kullanıcıdan sorgu alıp benzerlik araması yapar
    """
    print("=" * 50)
    print("Azure OpenAI Embedding Benzerlik Arama Ajanı")
    print("=" * 50)
    print("SharePoint dosyaları üzerinde benzerlik araması yapabilirsiniz.")
    print("Çıkmak için 'q' veya 'exit' yazın.\n")
    
    while True:
        query = input("\n🔍 Arama sorgusu: ")
        
        if query.lower() in ['q', 'exit', 'quit']:
            print("Benzerlik arama ajanı kapatılıyor...")
            break
        
        if not query.strip():
            continue
        
        # Otomatik threshold ve varsayılan 5 sonuç kullan
        start_time = time.time()
        results = similarity_search(query, threshold=None, top_k=5, auto_threshold=True)
        search_time = time.time() - start_time
        
        # Sonuçları formatla ve göster
        formatted_results = format_results(query, results)
        print("\n" + "=" * 50)
        print(formatted_results)
        print(f"⏱️ Arama süresi: {search_time:.2f} saniye")
        print("=" * 50)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Azure OpenAI Embedding Benzerlik Arama Ajanı')
    parser.add_argument('--update-files', action='store_true', help='SharePoint dosya listesini güncelle')
    parser.add_argument('--query', type=str, help='Arama sorgusu')
    parser.add_argument('--threshold', type=float, help='Benzerlik eşik değeri (0-1 arası)')
    parser.add_argument('--top-k', type=int, default=5, help='Maksimum sonuç sayısı')
    parser.add_argument('--auto-threshold', action='store_true', default=True, help='Otomatik eşik değeri belirleme (varsayılan: açık)')
    parser.add_argument('--interactive', action='store_true', help='İnteraktif mod')
    args = parser.parse_args()
    
    # SharePoint dosya listesini güncelle
    if args.update_files:
        update_file_list()
    
    # İnteraktif mod
    elif args.interactive:
        interactive_search()
    
    # Tek seferlik sorgu
    elif args.query:
        results = similarity_search(args.query, args.threshold, args.top_k, args.threshold is None)
        formatted_results = format_results(args.query, results)
        print(formatted_results)
    
    # Parametre belirtilmemişse kullanım bilgisi göster
    else:
        parser.print_help() 