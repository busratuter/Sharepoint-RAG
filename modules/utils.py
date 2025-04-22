"""
Utility functions for SharePoint-RAG

This module contains utility functions used across the project,
centralizing common functionality to avoid code duplication.
"""
import os
import sys
import json
import requests
import re
import asyncio
import aiohttp
import random
import time
from typing import List, Dict, Any, Optional

# Projenin kök dizinine erişebilmek için path ayarlaması
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
    AZURE_OPENAI_API_VERSION
)

def sanitize_key(key: str) -> str:
    """Belge anahtarını geçerli karakterlerle sınırlar (Azure AI Search için)"""
    # Dosya adındaki geçersiz karakterleri değiştir
    # Sadece harfler, rakamlar, alt çizgi (_), tire (-) ve eşittir (=) izin veriliyor
    sanitized = re.sub(r'[^\w\-=]', '_', key)
    return sanitized

async def async_embed_query(query: str) -> List[float]:
    """
    Sorgu metnini vektöre dönüştürür (embedding) - Asenkron versiyon
    """
    url = f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{AZURE_OPENAI_EMBEDDING_DEPLOYMENT}/embeddings?api-version={AZURE_OPENAI_API_VERSION}"
    
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_OPENAI_API_KEY
    }
    
    data = {
        "input": query,
        "model": AZURE_OPENAI_EMBEDDING_DEPLOYMENT
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"API hatası (status: {response.status}): {error_text}")
                
                result = await response.json()
                return result["data"][0]["embedding"]
    except Exception as e:
        print(f"❌ Asenkron embedding hatası: {str(e)}")
        raise e

def embed_query(query: str) -> List[float]:
    """
    Sorgu metnini vektöre dönüştürür (embedding) - Senkron versiyon
    Bu fonksiyon asenkron fonksiyona bir wrapper sağlar
    """
    try:
        # Python 3.7+ için
        return asyncio.run(async_embed_query(query))
    except (AttributeError, RuntimeError):
        # Eski Python sürümleri veya mevcut bir event loop varsa
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(async_embed_query(query))
        loop.close()
        return result

async def batch_embed_chunks(chunks: List[str], max_concurrent: int = 5) -> List[List[float]]:
    """
    Metin parçalarını paralel olarak embedlere dönüştürür
    
    Parameters:
    -----------
    chunks: List[str]
        Embedding'e dönüştürülecek metin parçaları
    max_concurrent: int
        Aynı anda işlenecek maksimum istek sayısı
    
    Returns:
    --------
    List[List[float]]
        Embedding'lerin listesi
    """
    embeddings = []
    total = len(chunks)
    
    print(f"🔄 Toplam {total} parça için paralel embedding başlatılıyor (max {max_concurrent} eşzamanlı)")
    # Semaphore kullanarak eşzamanlı istek sayısını sınırla
    sem = asyncio.Semaphore(max_concurrent)
    
    # İlerleme gösterim için zamanlayıcı
    start_time = time.time()
    completed = 0
    
    async def process_chunk(chunk, index):
        nonlocal completed
        """Bir metni embedding'e dönüştürür ve rate limit uygulanır"""
        async with sem:  # Semaphore ile istek sayısını sınırla
            chunk_preview = chunk[:30].replace("\n", " ")
            print(f"  🔄 Embedding oluşturuluyor: {index+1}/{total} (\"{chunk_preview}...\")")
            try:
                embedding_start = time.time()
                embedding = await async_embed_query(chunk)
                embedding_duration = time.time() - embedding_start
                
                completed += 1
                # Her 5 tamamlanan embedding veya her 10 saniyede bir ilerleme göster
                elapsed = time.time() - start_time
                if completed % 5 == 0 or (completed > 0 and elapsed > 10 and completed % max_concurrent == 0):
                    avg_time = elapsed / completed if completed > 0 else 0
                    remaining = (total - completed) * avg_time
                    print(f"  📈 İlerleme: {completed}/{total} embeddings (%{int(completed*100/total)})")
                    print(f"     Geçen süre: {elapsed:.1f}s, Tahmini kalan: {remaining:.1f}s")
                    print(f"     Ortalama embedding süresi: {avg_time:.2f}s/parça")
                
                print(f"  ✅ Embedding tamamlandı: {index+1}/{total} ({embedding_duration:.2f}s)")
                return embedding
            except Exception as e:
                print(f"  ❌ Embedding hatası ({index+1}/{total}): {str(e)}")
                return None
            finally:
                # Rate limiting için kısa bekleme
                await asyncio.sleep(0.1)
    
    # Tüm chunkslar için task'lar oluştur
    tasks = [process_chunk(chunk, i) for i, chunk in enumerate(chunks)]
    
    print(f"  🚀 {len(tasks)} embedding görevi oluşturuldu, paralel işlem başlıyor...")
    # Tüm task'ları çalıştır ve sonuçları topla
    results = await asyncio.gather(*tasks, return_exceptions=False)
    
    total_time = time.time() - start_time
    success_count = sum(1 for r in results if r is not None)
    print(f"✅ Embedding işlemi tamamlandı: {success_count}/{total} başarılı ({total_time:.1f}s)")
    
    return results

def embed_chunks_parallel(chunks: List[str], max_concurrent: int = 5) -> List[List[float]]:
    """
    Parçaların embeddinglerini paralel olarak oluşturur
    """
    try:
        # Python 3.7+
        return asyncio.run(batch_embed_chunks(chunks, max_concurrent))
    except AttributeError:
        # Eski Python sürümleri
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(batch_embed_chunks(chunks, max_concurrent))

def retry_with_backoff(func, max_retries=3, initial_backoff=1.0):
    """
    Exponential backoff ile bir fonksiyonun tekrar çalıştırılması
    """
    retries = 0
    backoff = initial_backoff
    
    while True:
        try:
            return func()
        except Exception as e:
            retries += 1
            if retries >= max_retries:
                raise e
            
            # Üstel gecikme (jitter ekleyerek)
            sleep_time = backoff * (1 + random.random() * 0.1)
            print(f"  ⚠️ Hata oluştu, {sleep_time:.2f} saniye sonra tekrar deneniyor ({retries}/{max_retries}): {str(e)}")
            time.sleep(sleep_time)
            backoff *= 2  # Üstel artış

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """
    Metni belirli boyutta parçalara ayırır
    
    Parameters:
    -----------
    text: str
        Parçalara ayrılacak metin
    chunk_size: int
        Her parçanın maksimum karakter sayısı (varsayılan: 500)
    overlap: int
        Parçalar arasındaki örtüşme miktarı (varsayılan: 50)
    """
    print(f"📊 Metin parçalanıyor (senkron): {len(text)} karakter -> chunk_size={chunk_size}, overlap={overlap}")
    chunks = []
    start = 0
    text_length = len(text)
    
    # Sonsuz döngü koruması: parçalama için maksimum sayı
    max_allowed_chunks = min(1000, text_length // 2)
    
    while start < text_length:
        # Sonsuz döngü kontrolü
        if len(chunks) > max_allowed_chunks:
            print(f"  ⚠️ Maksimum parça sayısı ({max_allowed_chunks}) aşıldı, işlem durduruluyor.")
            break
            
        end = min(start + chunk_size, text_length)
        
        # Cümle sonunda bitmeye çalış
        if end < text_length:
            # Eğer bir cümlenin ortasındaysak, sonraki nokta işaretini bul
            next_period = text.find('.', end)
            if next_period != -1 and next_period < end + 100:  # Makul bir aralıkta nokta varsa
                end = next_period + 1
        
        chunk = text[start:end]
        chunks.append(chunk)
        
        # Her 10 parçada bir loglama yap
        if len(chunks) % 10 == 0:
            print(f"  🧩 {len(chunks)}. chunk oluşturuldu: {start}-{end} (uzunluk: {len(chunk)} karakter)")
            
        # İlerleme için bir sonraki başlangıç noktasını hesapla
        # Eğer overlap chunk_size'dan büyükse, ilerleme sağlanamaz
        new_start = end - min(overlap, chunk_size // 2)
        
        # Eğer start değeri ilerlemiyorsa zorla ilerleme sağla
        if new_start <= start:
            new_start = start + max(1, chunk_size // 10)  # En az 1 karakter ilerleme
            
        start = new_start
    
    print(f"  ✅ Toplam {len(chunks)} parça oluşturuldu (senkron)")
    
    # İlk ve son parçaların önizlemesini göster
    if chunks:
        first_preview = chunks[0][:50].replace("\n", " ")
        last_preview = chunks[-1][:50].replace("\n", " ")
        print(f"  📄 İlk parça örnek: \"{first_preview}...\"")
        print(f"  📄 Son parça örnek: \"{last_preview}...\"")
    
    return chunks

async def chunk_text_async(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """
    Metni belirli boyutta parçalara asenkron olarak ayırır
    
    Parameters:
    -----------
    text: str
        Parçalara ayrılacak metin
    chunk_size: int
        Her parçanın maksimum karakter sayısı (varsayılan: 500)
    overlap: int
        Parçalar arasındaki örtüşme miktarı (varsayılan: 50)
    """
    print(f"📊 Metin parçalanıyor (asenkron): {len(text)} karakter -> chunk_size={chunk_size}, overlap={overlap}")
    chunks = []
    start = 0
    text_length = len(text)
    last_log_time = time.time()
    
    # Sonsuz döngü koruması: parçalama için maksimum sayı
    max_allowed_chunks = min(1000, text_length // 2)
    
    while start < text_length:
        # Sonsuz döngü kontrolü
        if len(chunks) > max_allowed_chunks:
            print(f"  ⚠️ Maksimum parça sayısı ({max_allowed_chunks}) aşıldı, işlem durduruluyor.")
            break
            
        # Her 10 parçada bir hafif bekleme ile CPU yükünü azalt
        if len(chunks) % 10 == 0 and len(chunks) > 0:
            await asyncio.sleep(0.01)  # Çok kısa bir bekleme
            
            # Her 10 parçada bir veya her 2 saniyede bir loglama yap
            current_time = time.time()
            if current_time - last_log_time > 2:
                print(f"  🧩 {len(chunks)}. parça işleniyor... ({start}/{text_length} karakter, %{int(start*100/text_length)} tamamlandı)")
                last_log_time = current_time
            
        end = min(start + chunk_size, text_length)
        
        # Cümle sonunda bitmeye çalış
        if end < text_length:
            # Eğer bir cümlenin ortasındaysak, sonraki nokta işaretini bul
            next_period = text.find('.', end)
            if next_period != -1 and next_period < end + 100:  # Makul bir aralıkta nokta varsa
                end = next_period + 1
        
        chunk = text[start:end]
        chunks.append(chunk)
        
        # İlerleme için bir sonraki başlangıç noktasını hesapla
        # Eğer overlap chunk_size'dan büyükse, ilerleme sağlanamaz
        new_start = end - min(overlap, chunk_size // 2)
        
        # Eğer start değeri ilerlemiyorsa zorla ilerleme sağla
        if new_start <= start:
            new_start = start + max(1, chunk_size // 10)  # En az 1 karakter ilerleme
            
        start = new_start
    
    print(f"  ✅ Toplam {len(chunks)} parça oluşturuldu (asenkron)")
    
    # İlk ve son parçaların önizlemesini göster
    if chunks:
        first_preview = chunks[0][:50].replace("\n", " ")
        last_preview = chunks[-1][:50].replace("\n", " ")
        print(f"  📄 İlk parça örnek: \"{first_preview}...\"")
        print(f"  📄 Son parça örnek: \"{last_preview}...\"")
    
    return chunks

def filter_by_similarity_score(search_results: List[Dict[str, Any]], min_score: float = 0.7) -> List[str]:
    """
    Arama sonuçlarından belirli bir similarity score'un üzerindeki SharePoint ID'lerini filtreler
    
    Parameters:
    -----------
    search_results: List[Dict[str, Any]]
        Azure AI Search'ten dönen sonuçlar
    min_score: float
        Minimum benzerlik skoru (varsayılan: 0.7)
    
    Returns:
    --------
    List[str]
        Filtrelenmiş SharePoint ID'lerinin listesi
    """
    print(f"🔍 Minimum benzerlik skoru {min_score} için sonuçlar filtreleniyor...")
    
    filtered_ids = []
    
    for result in search_results:
        # '@search.score' veya 'score' anahtarlarını kontrol et
        score = result.get('@search.score', result.get('score', 0))
        sharepoint_id = result.get('sharepoint_id', None)
        
        if sharepoint_id and score >= min_score:
            filtered_ids.append(sharepoint_id)
            print(f"  ✅ Dahil edildi: {result.get('file_name', 'Bilinmeyen dosya')} (Score: {score:.4f})")
        else:
            if sharepoint_id:
                print(f"  ❌ Dışarıda bırakıldı: {result.get('file_name', 'Bilinmeyen dosya')} (Score: {score:.4f})")
            else:
                print(f"  ⚠️ SharePoint ID bulunamadı: {result.get('file_name', 'Bilinmeyen dosya')}")
    
    print(f"  🔢 Toplam {len(filtered_ids)}/{len(search_results)} dosya filtrelendi")
    return filtered_ids

def get_sharepoint_files_by_ids(sharepoint_ids: List[str], access_token: str) -> List[Dict[str, Any]]:
    """
    Verilen SharePoint ID'lerine göre dosya bilgilerini getirir
    
    Parameters:
    -----------
    sharepoint_ids: List[str]
        SharePoint dosya ID'leri listesi
    access_token: str
        Microsoft Graph API erişim token'ı
    
    Returns:
    --------
    List[Dict[str, Any]]
        Dosya bilgilerinin listesi
    """
    if not sharepoint_ids:
        print("⚠️ Filtrelenecek SharePoint ID'si bulunamadı")
        return []
    
    print(f"📂 {len(sharepoint_ids)} SharePoint dosyası için bilgiler alınıyor...")
    
    headers = {'Authorization': f'Bearer {access_token}'}
    files_info = []
    
    from config.settings import SITE_ID
    
    for file_id in sharepoint_ids:
        try:
            url = f"https://graph.microsoft.com/v1.0/sites/{SITE_ID}/drive/items/{file_id}"
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            file_data = response.json()
            file_info = {
                "name": file_data.get("name", ""),
                "size": file_data.get("size", 0),
                "file_type": file_data.get("name", "").split(".")[-1],
                "created_date": file_data.get("createdDateTime", ""),
                "last_modified": file_data.get("lastModifiedDateTime", ""),
                "web_url": file_data.get("webUrl", ""),
                "sharepoint_id": file_data.get("id", "")
            }
            files_info.append(file_info)
            print(f"  ✅ {file_info['name']} dosya bilgileri alındı")
            
        except Exception as e:
            print(f"  ❌ {file_id} ID'li dosya bilgileri alınırken hata: {str(e)}")
            if hasattr(e, 'response') and e.response:
                print(f"  ❌ HTTP Status: {e.response.status_code}")
                print(f"  ❌ Response: {e.response.text}")
    
    return files_info
