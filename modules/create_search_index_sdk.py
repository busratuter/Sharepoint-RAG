"""
Azure AI Search indeksi oluşturma ve blob içeriğini indeksleme modülü (SDK kullanarak)
"""
import os
import sys
import time
import requests
import tempfile
from typing import List, Dict, Any, Optional
import io
from pathlib import Path
import random
import asyncio
import aiohttp
import re
from datetime import datetime

from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchFieldDataType,
    SimpleField,
    SearchableField,
    SearchField,
    VectorSearch,
    HnswAlgorithmConfiguration,
    ExhaustiveKnnAlgorithmConfiguration,
    VectorSearchAlgorithmMetric,
    VectorSearchProfile
)
from azure.storage.blob import BlobServiceClient
from azure.search.documents import SearchClient
# Vector import'u kaldırıldı çünkü yüklü SDK sürümünde bulunmuyor
# from azure.search.documents.models import Vector

# Dosya formatlarını okumak için kütüphaneler
import docx  # python-docx kütüphanesi
from pypdf import PdfReader

# Projenin kök dizinine erişebilmek için path ayarlaması
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import (
    AZURE_SEARCH_ENDPOINT,
    AZURE_SEARCH_KEY,
    AZURE_SEARCH_INDEX_NAME,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
    AZURE_OPENAI_API_VERSION,
    BLOB_CONNECTION_STRING,
    BLOB_CONTAINER_NAME
)

# Utils modülünden ortak fonksiyonları import et
from modules.utils import (
    sanitize_key,
    async_embed_query,
    batch_embed_chunks,
    embed_chunks_parallel,
    retry_with_backoff,
    chunk_text,
    chunk_text_async
)

def create_search_index(index_name: str = AZURE_SEARCH_INDEX_NAME) -> SearchIndex:
    """
    SDK kullanarak Azure AI Search indeksi oluşturur
    """
    print(f"🔧 '{index_name}' indeksi oluşturuluyor (SDK)...")
    
    # İndeks istemcisi oluştur
    index_client = SearchIndexClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY)
    )
    
    # İndeksin mevcut olup olmadığını kontrol et
    try:
        existing_index = index_client.get_index(name=index_name)
        if existing_index:
            print(f"ℹ️ '{index_name}' indeksi zaten mevcut. İndeks tekrar oluşturulmayacak.")
            return existing_index
    except Exception:
        # İndeks bulunamadı, yeni oluşturulacak
        pass
        
    # İndeks alanlarını oluştur
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, 
                   filterable=True, sortable=True, facetable=True),
        SearchableField(name="file_name", type=SearchFieldDataType.String, 
                       filterable=True, sortable=True),
        SimpleField(name="chunk_id", type=SearchFieldDataType.String, 
                   filterable=True),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=3072,
            vector_search_profile_name="myHnswProfile"
        ),
        SimpleField(name="file_type", type=SearchFieldDataType.String, 
                  filterable=True, sortable=True),
        SimpleField(name="last_updated", type=SearchFieldDataType.DateTimeOffset, 
                  filterable=True, sortable=True)
    ]
    
    # Vektör arama konfigürasyonu oluştur
    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name="myHnsw",
                kind="hnsw",
                parameters={
                    "m": 4,
                    "efConstruction": 400,
                    "efSearch": 500,
                    "metric": "cosine"
                }
            ),
            ExhaustiveKnnAlgorithmConfiguration(
                name="myExhaustiveKnn",
                kind="exhaustiveKnn",
                parameters={
                    "metric": "cosine"
                }
            )
        ],
        profiles=[
            VectorSearchProfile(
                name="myHnswProfile",
                algorithm_configuration_name="myHnsw"
            ),
            VectorSearchProfile(
                name="myExhaustiveKnnProfile",
                algorithm_configuration_name="myExhaustiveKnn"
            )
        ]
    )
    
    # İndeksi oluştur
    index = SearchIndex(
        name=index_name,
        fields=fields,
        vector_search=vector_search
    )
    
    try:
        result = index_client.create_or_update_index(index)
        print(f"✅ '{index_name}' indeksi başarıyla oluşturuldu!")
        return result
    except Exception as e:
        print(f"❌ İndeks oluşturma hatası: {str(e)}")
        raise e

def get_index_statistics(index_name: str = AZURE_SEARCH_INDEX_NAME) -> Dict[str, Any]:
    """
    İndeksin durumunu ve istatistiklerini getirir
    """
    print(f"ℹ️ '{index_name}' indeks istatistikleri alınıyor...")
    
    # İndeks istemcisi oluştur
    index_client = SearchIndexClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY)
    )
    
    try:
        # İndeksin varlığını kontrol et
        try:
            index = index_client.get_index(name=index_name)
            print(f"ℹ️ '{index_name}' indeksi bulundu.")
        except Exception as e:
            print(f"❌ İndeks bulunamadı: {str(e)}")
            return {"error": f"İndeks bulunamadı: {str(e)}"}
        
        # İndeks istatistiklerini al
        statistics = index_client.get_index_statistics(index_name)
        
        stats = {
            "document_count": statistics.document_count,
            "storage_size": statistics.storage_size,
            "vector_index_size": getattr(statistics, "vector_index_size", None),
            "index_name": index_name,
            "fields": [field.name for field in index.fields],
            "vector_search": bool(index.vector_search),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        print(f"📊 İndeks İstatistikleri:")
        print(f"  - Belge sayısı: {stats['document_count']}")
        print(f"  - Depolama boyutu: {stats['storage_size']} bayt")
        if stats['vector_index_size']:
            print(f"  - Vektör indeks boyutu: {stats['vector_index_size']} bayt")
        print(f"  - İndeks alanları: {', '.join(stats['fields'])}")
        
        return stats
    except Exception as e:
        print(f"❌ İndeks istatistikleri alınırken hata: {str(e)}")
        return {"error": str(e)}

def delete_search_index(index_name: str = AZURE_SEARCH_INDEX_NAME) -> bool:
    """
    SDK kullanarak indeksi siler
    """
    print(f"🗑️ '{index_name}' indeksi siliniyor...")
    
    # İndeks istemcisi oluştur
    index_client = SearchIndexClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY)
    )
    
    try:
        index_client.delete_index(index_name)
        print(f"✅ '{index_name}' indeksi başarıyla silindi.")
        return True
    except Exception as e:
        print(f"❌ İndeks silme hatası: {str(e)}")
        return False

def list_blobs() -> List[Dict[str, Any]]:
    """
    Azure Blob Storage'daki tüm dosyaları listeler
    """
    try:
        # Blob service client oluştur
        blob_service_client = BlobServiceClient.from_connection_string(BLOB_CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(BLOB_CONTAINER_NAME)
        
        # Blob listesini al
        blobs = []
        for blob in container_client.list_blobs():
            blobs.append({
                "name": blob.name,
                "size": blob.size,
                "content_type": blob.content_settings.content_type,
                "last_modified": blob.last_modified
            })
        
        return blobs
    except Exception as e:
        print(f"❌ Blob listesi alma hatası: {str(e)}")
        return []

def extract_text_from_blob(blob_name: str) -> str:
    """
    Blob'dan metin içeriğini çıkarır. Desteklenen formatlar:
    - .txt, .json, .md vb. metin dosyaları
    - .docx (Word dosyaları)
    - .pdf (PDF dosyaları)
    """
    try:
        # Blob service client oluştur
        blob_service_client = BlobServiceClient.from_connection_string(BLOB_CONNECTION_STRING)
        blob_client = blob_service_client.get_blob_client(container=BLOB_CONTAINER_NAME, blob=blob_name)
        
        # Dosya uzantısını al
        file_extension = Path(blob_name).suffix.lower()
        
        # Blob'u indir
        download_stream = blob_client.download_blob()
        blob_data = download_stream.readall()
        
        # Dosya tipine göre metin çıkarma işlemini yap
        if file_extension in ['.docx', '.doc']:
            # DOCX dosyası işleme
            try:
                doc = docx.Document(io.BytesIO(blob_data))
                paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
                return '\n'.join(paragraphs)
            except Exception as docx_error:
                print(f"⚠️ DOCX işleme hatası: {str(docx_error)}")
                return ""
        
        elif file_extension == '.pdf':
            # PDF dosyası işleme
            try:
                pdf_file = io.BytesIO(blob_data)
                pdf_reader = PdfReader(pdf_file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text
            except Exception as pdf_error:
                print(f"⚠️ PDF işleme hatası: {str(pdf_error)}")
                return ""
        
        else:
            # Metin dosyası olarak varsay
            return blob_data.decode('utf-8', errors='ignore')
            
    except Exception as e:
        print(f"❌ Blob içeriğini çıkarma hatası: {str(e)}")
        return ""

def index_with_parallel_embeddings(blob_list: List[Dict[str, Any]], 
                                  index_name: str = AZURE_SEARCH_INDEX_NAME,
                                  chunk_size: int = 200,
                                  overlap: int = 20,
                                  batch_size: int = 5,
                                  max_concurrent_embeddings: int = 5,
                                  process_only_changed: bool = True) -> Dict[str, Any]:
    """
    Blob içeriklerini paralel embeddings ile indeksler
    
    Parameters:
    -----------
    blob_list: List[Dict[str, Any]]
        İndekslenecek blob listesi
    index_name: str
        İndeks adı
    chunk_size: int
        Bir parçanın maximum karakter sayısı
    overlap: int
        Parçalar arasındaki örtüşme miktarı
    batch_size: int
        Her upload batch'inde kaç belge yükleneceği
    max_concurrent_embeddings: int
        Eşzamanlı embedding işlemi sayısı
    process_only_changed: bool
        Sadece değişen veya yeni dosyaları işleyip işlememe durumu. 
        True olursa, yalnızca değişen veya yeni dosyalar indekslenir.
    """
    print(f"🔄 {len(blob_list)} dosya paralel embeddings ile indeksleniyor...")
    print(f"📊 Ayarlar: chunk_size={chunk_size}, overlap={overlap}, batch_size={batch_size}, max_concurrent_embeddings={max_concurrent_embeddings}")
    print(f"🔄 {'Sadece değişen dosyalar' if process_only_changed else 'Tüm dosyalar'} işlenecek.")
    
    # Arama istemcisi oluştur
    search_client = SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        index_name=index_name,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY)
    )
    
    # İndekslenmiş belge sayıları
    stats = {
        "total_blobs": len(blob_list),
        "successful": 0,
        "failed": 0,
        "skipped": 0,  # Değişiklik olmadığı için atlanan dosyalar
        "total_chunks": 0,
        "indexed_chunks": 0,
        "total_batches": 0,
        "successful_batches": 0
    }

    # İndeksteki bir dosyanın son güncellenme zamanını kontrol eden fonksiyon
    async def check_file_in_index(file_name: str) -> Optional[datetime]:
        """
        Verilen dosya adının indeksteki son güncellenme zamanını kontrol eder.
        Eğer dosya indekste yoksa None döner.
        """
        try:
            # İndekste arama yap - sadece ilk chunk'ı bulmaya çalışıyoruz
            sanitized_name = sanitize_key(file_name)
            search_results = search_client.search(
                search_text=f"file_name:{file_name}",
                select=["file_name", "last_updated"],
                top=1
            )
            
            # Sonuçları kontrol et
            for result in search_results:
                if result.get("last_updated"):
                    # ISO formatındaki date string'i datetime'a çevir
                    return datetime.fromisoformat(result["last_updated"])
            
            # Dosya bulunamadı
            return None
            
        except Exception as e:
            print(f"  ⚠️ Dosya indeks kontrolü sırasında hata: {str(e)}")
            return None

    async def process_blob(blob, blob_index):
        try:
            blob_name = blob["name"]
            blob_size = blob["size"]
            blob_modified = blob["last_modified"]
            
            # Eğer sadece değişenler işlenecekse, indeksteki durumu kontrol et
            if process_only_changed:
                index_last_updated = await check_file_in_index(blob_name)
                
                if index_last_updated is not None:
                    # Dosya indekste var, güncellenme zamanlarını karşılaştır
                    if blob_modified <= index_last_updated:
                        print(f"\n⏩ Değişiklik yok, atlanıyor: {blob_name}")
                        stats["skipped"] += 1
                        return {"success": True, "skipped": True, "chunks": 0, "indexed": 0, "batches": 0}
                    else:
                        print(f"\n🔄 Dosya güncellenmiş, yeniden indeksleniyor: {blob_name}")
                        print(f"   Blob son değişiklik: {blob_modified}")
                        print(f"   İndeks son güncelleme: {index_last_updated}")
                else:
                    print(f"\n📄 Yeni dosya indeksleniyor: {blob_name}")
            
            print(f"\n📄 Dosya {blob_index+1}/{len(blob_list)}: '{blob_name}' indeksleniyor... ({blob_size} bayt)")
            
            # Geri kalan işlem aynı...
            # Dosya işlem zamanını ölç
            blob_start_time = time.time()
            
            # Dosya içeriğini çıkar
            extract_start = time.time()
            content = extract_text_from_blob(blob_name)
            extract_duration = time.time() - extract_start
            
            print(f"  ⏱️ İçerik çıkarma süresi: {extract_duration:.2f}s")
            
            # İçeriğin boş olmadığından emin ol
            if not content.strip():
                print(f"⚠️ '{blob_name}' için içerik çıkarılamadı veya boş.")
                return {"success": False, "skipped": False, "chunks": 0, "indexed": 0, "batches": 0}
            
            # Çıkarılan içerik hakkında bilgi
            content_len = len(content)
            content_preview = content[:100].replace("\n", " ")
            print(f"  📝 Çıkarılan içerik: {content_len} karakter")
            print(f"     İlk 100 karakter: \"{content_preview}...\"")
                
            # İçeriği daha küçük parçalara asenkron olarak ayır
            chunk_start = time.time()
            chunks = await chunk_text_async(content, chunk_size, overlap)
            chunk_duration = time.time() - chunk_start
            
            print(f"  ⏱️ Parçalama süresi: {chunk_duration:.2f}s")
            
            # İçerik artık kullanılmayacak, belleği temizle
            del content
            import gc
            gc.collect()
            
            # Parça sayısını kaydet
            chunk_count = len(chunks)
            print(f"  📊 {chunk_count} parça oluşturuldu.")
            
            if chunk_count == 0:
                print(f"  ⚠️ '{blob_name}' için parça oluşturulamadı.")
                return {"success": False, "skipped": False, "chunks": 0, "indexed": 0, "batches": 0}
            
            # Geri kalan işlem aynı...
            # PARALEL: Tüm parçalar için embedding'leri eşzamanlı oluştur
            embed_start = time.time()
            print(f"  🔄 Embeddings paralel olarak oluşturuluyor (max {max_concurrent_embeddings} eşzamanlı istek)...")
            embeddings = await batch_embed_chunks(chunks, max_concurrent_embeddings)
            embed_duration = time.time() - embed_start
            
            print(f"  ⏱️ Embedding toplam süresi: {embed_duration:.2f}s (parça başına ortalama: {embed_duration/chunk_count:.2f}s)")
            
            # İşleme süreleri hakkında bilgi
            blob_current_duration = time.time() - blob_start_time
            print(f"  ⏱️ Şimdiye kadarki toplam işlem süresi: {blob_current_duration:.2f}s")
            
            # Yükleme için belge listesi
            documents = []
            successful_chunks = 0
            failed_chunks = 0
            batch_number = 0
            successful_batches = 0
            
            # Blob adını geçerli bir isim haline dönüştür
            sanitized_blob_name = sanitize_key(blob_name)
            
            # Her bir chunk ve embedding'i işle
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                try:
                    # Embedding başarılı mı kontrol et
                    if embedding is None:
                        print(f"  ⚠️ Parça {i+1}/{chunk_count} için embedding oluşturulamadı.")
                        failed_chunks += 1
                        continue
                    
                    # Belge oluştur - geçerli bir ID ile
                    chunk_id = f"{sanitized_blob_name}_{i}"
                    document = {
                        "id": chunk_id,
                        "file_name": blob_name,
                        "chunk_id": str(i),
                        "content": chunk,
                        "content_vector": embedding,
                        "file_type": blob_name.split(".")[-1] if "." in blob_name else "unknown",
                        "last_updated": blob["last_modified"].isoformat() if blob["last_modified"] else None
                    }
                    
                    # Belgeyi listeye ekle
                    documents.append(document)
                    successful_chunks += 1
                    
                    # Batch dolduysa veya son parçaysa indeksleme yap
                    if len(documents) >= batch_size or i+1 == chunk_count:
                        if documents:
                            batch_number += 1
                            
                            print(f"  📦 Batch {batch_number}: {len(documents)} belge indeksleniyor...")
                            
                            # Batch yükleme fonksiyonu
                            def upload_batch():
                                return search_client.upload_documents(documents=documents)
                            
                            # Retry mekanizması ile yükle
                            try:
                                upload_start = time.time()
                                results = retry_with_backoff(upload_batch)
                                upload_duration = time.time() - upload_start
                                
                                success_count = sum(1 for r in results if r.succeeded)
                                
                                if success_count == len(documents):
                                    print(f"  ✅ Batch {batch_number}: Tüm belgeler başarıyla indekslendi. ({upload_duration:.2f}s)")
                                    successful_batches += 1
                                else:
                                    print(f"  ⚠️ Batch {batch_number}: {success_count}/{len(documents)} belge başarıyla indekslendi. ({upload_duration:.2f}s)")
                                
                                # Yükleme tamamlandı, belgeyi temizle
                                documents.clear()
                                
                                # Belleği temizle
                                gc.collect()
                                
                                # Kısa bir bekleme
                                await asyncio.sleep(0.1)
                                
                            except Exception as e:
                                print(f"  ❌ Batch {batch_number} yükleme hatası: {str(e)}")
                                failed_chunks += len(documents)
                                # Başarısız batch'i temizle
                                documents.clear()
                    
                except Exception as chunk_error:
                    print(f"  ❌ Parça {i+1} işleme hatası: {str(chunk_error)}")
                    failed_chunks += 1
            
            # İşlem tamamlanma süresi
            blob_total_duration = time.time() - blob_start_time
            print(f"  ⏱️ Toplam işlem süresi: {blob_total_duration:.2f}s")

            # Dosya başarı durumunu raporla
            if successful_chunks > 0:
                print(f"  ✅ '{blob_name}' için {successful_chunks}/{chunk_count} parça işlendi, indeksleme tamamlandı.")
                return {
                    "success": True, 
                    "skipped": False,
                    "chunks": chunk_count, 
                    "indexed": successful_chunks,
                    "batches": successful_batches
                }
            else:
                print(f"  ❌ '{blob_name}' için hiçbir parça indekslenemedi.")
                return {"success": False, "skipped": False, "chunks": chunk_count, "indexed": 0, "batches": 0}
            
        except Exception as e:
            print(f"❌ '{blob['name']}' indeksleme hatası: {str(e)}")
            return {"success": False, "skipped": False, "chunks": 0, "indexed": 0, "batches": 0}
    
    # Ana asenkron işleme fonksiyonu
    async def main_async_processing():
        # İşlem zamanını ölç
        total_start_time = time.time()
        
        # Blobları birer birer işle (paralel işleme ileride eklenebilir)
        for blob_index, blob in enumerate(blob_list):
            result = await process_blob(blob, blob_index)
            
            # İstatistikleri güncelle
            if result.get("skipped", False):
                # Atlanan dosyalar için ayrı istatistik
                continue
            elif result["success"]:
                stats["successful"] += 1
            else:
                stats["failed"] += 1
                
            stats["total_chunks"] += result["chunks"]
            stats["indexed_chunks"] += result["indexed"]
            stats["total_batches"] += result["batches"]
            stats["successful_batches"] += result["batches"]
        
        # Toplam işlem süresi
        total_duration = time.time() - total_start_time
        print(f"\n⏱️ Toplam işlem süresi: {total_duration:.2f}s")
    
    # Event loop oluştur ve ana asenkron işlemi çalıştır
    try:
        # Python 3.7+ için
        asyncio.run(main_async_processing())
    except AttributeError:
        # Eski Python sürümleri için
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main_async_processing())
    
    print(f"\n✅ İndeksleme tamamlandı!")
    print(f"📊 İstatistikler:")
    print(f"  - Toplam dosya: {stats['total_blobs']}")
    print(f"  - Başarılı dosya: {stats['successful']}")
    print(f"  - Atlanan dosya: {stats['skipped']}")
    print(f"  - Başarısız dosya: {stats['failed']}")
    print(f"  - Toplam parça: {stats['total_chunks']}")
    print(f"  - İndekslenen parça: {stats['indexed_chunks']}")
    print(f"  - Toplam batch: {stats['total_batches']}")
    print(f"  - Başarılı batch: {stats['successful_batches']}")
    
    return stats

def index_blob_content(blob_list: List[Dict[str, Any]], 
                      index_name: str = AZURE_SEARCH_INDEX_NAME,
                      chunk_size: int = 300,
                      overlap: int = 30,
                      batch_size: int = 10) -> Dict[str, Any]:
    """
    Blob içeriklerini indeksler (SDK kullanarak) - Optimize edilmiş versiyon
    
    Parameters:
    -----------
    blob_list: List[Dict[str, Any]]
        İndekslenecek blob listesi
    index_name: str
        İndeks adı
    chunk_size: int
        Bir parçanın maximum karakter sayısı (varsayılan: 300)
    overlap: int
        Parçalar arasındaki örtüşme miktarı (varsayılan: 30)
    batch_size: int
        Her batch'te kaç belge yükleneceği (varsayılan: 10)
    """
    print(f"🔄 {len(blob_list)} dosya indeksleniyor...")
    print(f"📊 Ayarlar: chunk_size={chunk_size}, overlap={overlap}, batch_size={batch_size}")
    
    # Arama istemcisi oluştur
    search_client = SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        index_name=index_name,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY)
    )
    
    # İndekslenmiş belge sayıları
    stats = {
        "total_blobs": len(blob_list),
        "successful": 0,
        "failed": 0,
        "total_chunks": 0,
        "indexed_chunks": 0,
        "total_batches": 0,
        "successful_batches": 0
    }
    
    # Her bir blob için ayrı ayrı işlem yap
    for blob_index, blob in enumerate(blob_list):
        try:
            blob_name = blob["name"]
            print(f"\n📄 Dosya {blob_index+1}/{len(blob_list)}: '{blob_name}' indeksleniyor...")
            
            # Dosya içeriğini çıkar
            content = extract_text_from_blob(blob_name)
            
            # İçeriğin boş olmadığından emin ol
            if not content.strip():
                print(f"⚠️ '{blob_name}' için içerik çıkarılamadı veya boş.")
                stats["failed"] += 1
                continue
                
            # İçeriği daha küçük parçalara ayır
            chunks = chunk_text(content, chunk_size, overlap)
            
            # İçerik artık kullanılmayacak, belleği temizle
            del content
            import gc
            gc.collect()
            
            # Parça sayısını kaydet
            chunk_count = len(chunks)
            stats["total_chunks"] += chunk_count
            print(f"  📊 {chunk_count} parça oluşturuldu.")
            
            # Yükleme için belge listesi
            documents = []
            successful_chunks = 0
            failed_chunks = 0
            batch_number = 0
            
            # Blob adını geçerli bir isim haline dönüştür
            sanitized_blob_name = sanitize_key(blob_name)
            
            # Her bir parçayı işle
            for i, chunk in enumerate(chunks):
                try:
                    # Embeddingi oluştur (retry mekanizması ile)
                    def create_embedding():
                        # async_embed_query asenkron bir fonksiyon olduğundan
                        # doğrudan çağrılamaz, bir wrapper kullanmalıyız
                        try:
                            loop = asyncio.get_event_loop()
                        except RuntimeError:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                        return loop.run_until_complete(async_embed_query(chunk))
                    
                    # Retry mekanizması ile embedding oluştur
                    try:
                        embedding = retry_with_backoff(create_embedding)
                    except Exception as e:
                        print(f"  ⚠️ Parça {i+1}/{chunk_count} için embedding oluşturulamadı: {str(e)}")
                        failed_chunks += 1
                        continue
                    
                    # Belge oluştur - geçerli bir ID ile
                    chunk_id = f"{sanitized_blob_name}_{i}"
                    document = {
                        "id": chunk_id,
                        "file_name": blob_name,
                        "chunk_id": str(i),
                        "content": chunk,
                        "content_vector": embedding,
                        "file_type": blob_name.split(".")[-1] if "." in blob_name else "unknown",
                        "last_updated": blob["last_modified"].isoformat() if blob["last_modified"] else None
                    }
                    
                    # Belgeyi listeye ekle
                    documents.append(document)
                    successful_chunks += 1
                    
                    # Her 5 belge ve son parçada ilerleme göster
                    if (i+1) % 5 == 0 or i+1 == chunk_count:
                        print(f"  🔄 Parça {i+1}/{chunk_count} işleniyor... ({successful_chunks} başarılı, {failed_chunks} başarısız)")
                    
                    # Batch dolduysa veya son parçaysa indeksleme yap
                    if len(documents) >= batch_size or i+1 == chunk_count:
                        if documents:
                            batch_number += 1
                            stats["total_batches"] += 1
                            
                            print(f"  📦 Batch {batch_number}: {len(documents)} belge indeksleniyor...")
                            
                            # Batch yükleme fonksiyonu
                            def upload_batch():
                                return search_client.upload_documents(documents=documents)
                            
                            # Retry mekanizması ile yükle
                            try:
                                results = retry_with_backoff(upload_batch)
                                success_count = sum(1 for r in results if r.succeeded)
                                
                                if success_count == len(documents):
                                    print(f"  ✅ Batch {batch_number}: Tüm belgeler başarıyla indekslendi.")
                                    stats["successful_batches"] += 1
                                else:
                                    print(f"  ⚠️ Batch {batch_number}: {success_count}/{len(documents)} belge başarıyla indekslendi.")
                                
                                stats["indexed_chunks"] += success_count
                                
                                # Yükleme tamamlandı, belgeyi temizle
                                documents.clear()
                                
                                # Belleği temizle
                                gc.collect()
                                
                                # Kısa bir bekleme
                                time.sleep(0.1)
                                
                            except Exception as e:
                                print(f"  ❌ Batch {batch_number} yükleme hatası: {str(e)}")
                                failed_chunks += len(documents)
                                # Başarısız batch'i temizle
                                documents.clear()
                    
                except Exception as chunk_error:
                    print(f"  ❌ Parça {i+1} işleme hatası: {str(chunk_error)}")
                    failed_chunks += 1
            
            # Dosya başarı durumunu güncelle
            if successful_chunks > 0:
                stats["successful"] += 1
                print(f"  ✅ '{blob_name}' için {successful_chunks}/{chunk_count} parça işlendi, indeksleme tamamlandı.")
            else:
                stats["failed"] += 1
            
        except Exception as e:
            print(f"❌ '{blob_name}' indeksleme hatası: {str(e)}")
            stats["failed"] += 1
    
    print(f"\n✅ İndeksleme tamamlandı!")
    print(f"📊 İstatistikler:")
    print(f"  - Toplam dosya: {stats['total_blobs']}")
    print(f"  - Başarılı dosya: {stats['successful']}")
    print(f"  - Başarısız dosya: {stats['failed']}")
    print(f"  - Toplam parça: {stats['total_chunks']}")
    print(f"  - İndekslenen parça: {stats['indexed_chunks']}")
    print(f"  - Toplam batch: {stats['total_batches']}")
    print(f"  - Başarılı batch: {stats['successful_batches']}")
    
    return stats

def index_blob_content_async(blob_list: List[Dict[str, Any]], 
                            index_name: str = AZURE_SEARCH_INDEX_NAME,
                            chunk_size: int = 300,
                            overlap: int = 30,
                            batch_size: int = 10,
                            embedding_batch_size: int = 5) -> Dict[str, Any]:
    """
    Blob içeriklerini asenkron işlemlerle indeksler - Asenkron optimizasyonlu versiyon
    
    Parameters:
    -----------
    blob_list: List[Dict[str, Any]]
        İndekslenecek blob listesi
    index_name: str
        İndeks adı
    chunk_size: int
        Bir parçanın maximum karakter sayısı
    overlap: int
        Parçalar arasındaki örtüşme miktarı
    batch_size: int
        Her upload batch'inde kaç belge yükleneceği
    embedding_batch_size: int
        Her seferde paralel yapılacak embedding işlemi sayısı
    """
    print(f"🔄 {len(blob_list)} dosya asenkron indeksleniyor...")
    print(f"📊 Ayarlar: chunk_size={chunk_size}, overlap={overlap}, batch_size={batch_size}, embedding_batch_size={embedding_batch_size}")
    
    # Arama istemcisi oluştur
    search_client = SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        index_name=index_name,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY)
    )
    
    # İndekslenmiş belge sayıları
    stats = {
        "total_blobs": len(blob_list),
        "successful": 0,
        "failed": 0,
        "total_chunks": 0,
        "indexed_chunks": 0,
        "total_batches": 0,
        "successful_batches": 0
    }
    
    async def process_blob(blob, blob_index):
        """
        Bir blob'u asenkron olarak işleyen iç fonksiyon
        """
        try:
            blob_name = blob["name"]
            print(f"\n📄 Dosya {blob_index+1}/{len(blob_list)}: '{blob_name}' indeksleniyor...")
            
            # Dosya içeriğini çıkar
            content = extract_text_from_blob(blob_name)
            
            # İçeriğin boş olmadığından emin ol
            if not content.strip():
                print(f"⚠️ '{blob_name}' için içerik çıkarılamadı veya boş.")
                return {"success": False, "chunks": 0, "indexed": 0, "batches": 0}
                
            # İçeriği daha küçük parçalara ayır
            chunks = chunk_text(content, chunk_size, overlap)
            
            # İçerik artık kullanılmayacak, belleği temizle
            del content
            import gc
            gc.collect()
            
            # Parça sayısını kaydet
            chunk_count = len(chunks)
            print(f"  📊 {chunk_count} parça oluşturuldu.")
            
            # Asenkron olarak tüm chunklarin embedding'lerini oluştur
            embeddings = await batch_embed_chunks(chunks, embedding_batch_size)
            
            # Yükleme için belge listesi
            documents = []
            successful_chunks = 0
            failed_chunks = 0
            successful_batches = 0
            batch_number = 0
            
            # Blob adını geçerli bir isim haline dönüştür
            sanitized_blob_name = sanitize_key(blob_name)
            
            # Her bir chunk ve embedding'i işle
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                try:
                    # Embedding başarılı mı kontrol et
                    if embedding is None:
                        print(f"  ⚠️ Parça {i+1}/{chunk_count} için embedding oluşturulamadı.")
                        failed_chunks += 1
                        continue
                    
                    # Belge oluştur - geçerli bir ID ile
                    chunk_id = f"{sanitized_blob_name}_{i}"
                    document = {
                        "id": chunk_id,
                        "file_name": blob_name,
                        "chunk_id": str(i),
                        "content": chunk,
                        "content_vector": embedding,
                        "file_type": blob_name.split(".")[-1] if "." in blob_name else "unknown",
                        "last_updated": blob["last_modified"].isoformat() if blob["last_modified"] else None
                    }
                    
                    # Belgeyi listeye ekle
                    documents.append(document)
                    successful_chunks += 1
                    
                    # Her 5 belge ve son parçada ilerleme göster
                    if (i+1) % 5 == 0 or i+1 == chunk_count:
                        print(f"  🔄 Parça {i+1}/{chunk_count} belge hazırlanıyor... ({successful_chunks} başarılı, {failed_chunks} başarısız)")
                    
                    # Batch dolduysa veya son parçaysa indeksleme yap
                    if len(documents) >= batch_size or i+1 == chunk_count:
                        if documents:
                            batch_number += 1
                            
                            print(f"  📦 Batch {batch_number}: {len(documents)} belge indeksleniyor...")
                            
                            # Batch yükleme fonksiyonu
                            def upload_batch():
                                return search_client.upload_documents(documents=documents)
                            
                            # Retry mekanizması ile yükle
                            try:
                                results = retry_with_backoff(upload_batch)
                                success_count = sum(1 for r in results if r.succeeded)
                                
                                if success_count == len(documents):
                                    print(f"  ✅ Batch {batch_number}: Tüm belgeler başarıyla indekslendi.")
                                    successful_batches += 1
                                else:
                                    print(f"  ⚠️ Batch {batch_number}: {success_count}/{len(documents)} belge başarıyla indekslendi.")
                                
                                # Yükleme tamamlandı, belgeyi temizle
                                documents.clear()
                                
                                # Belleği temizle
                                gc.collect()
                                
                                # Kısa bir bekleme
                                await asyncio.sleep(0.1)
                                
                            except Exception as e:
                                print(f"  ❌ Batch {batch_number} yükleme hatası: {str(e)}")
                                failed_chunks += len(documents)
                                # Başarısız batch'i temizle
                                documents.clear()
                    
                except Exception as chunk_error:
                    print(f"  ❌ Parça {i+1} işleme hatası: {str(chunk_error)}")
                    failed_chunks += 1
            
            # Dosya başarı durumunu raporla
            if successful_chunks > 0:
                print(f"  ✅ '{blob_name}' için {successful_chunks}/{chunk_count} parça işlendi, indeksleme tamamlandı.")
                return {
                    "success": True, 
                    "chunks": chunk_count, 
                    "indexed": successful_chunks,
                    "batches": successful_batches
                }
            else:
                print(f"  ❌ '{blob_name}' için hiçbir parça indekslenemedi.")
                return {"success": False, "chunks": chunk_count, "indexed": 0, "batches": 0}
            
        except Exception as e:
            print(f"❌ '{blob['name']}' indeksleme hatası: {str(e)}")
            return {"success": False, "chunks": 0, "indexed": 0, "batches": 0}
    
    # Ana asenkron işleme fonksiyonu
    async def main_async_processing():
        # İşlem zamanını ölç
        total_start_time = time.time()
        
        # Blobları birer birer işle (paralel işleme ileride eklenebilir)
        for blob_index, blob in enumerate(blob_list):
            result = await process_blob(blob, blob_index)
            
            # İstatistikleri güncelle
            if result["success"]:
                stats["successful"] += 1
            else:
                stats["failed"] += 1
                
            stats["total_chunks"] += result["chunks"]
            stats["indexed_chunks"] += result["indexed"]
            stats["total_batches"] += result["batches"]
            stats["successful_batches"] += result["batches"]
        
        # Toplam işlem süresi
        total_duration = time.time() - total_start_time
        print(f"\n⏱️ Toplam işlem süresi: {total_duration:.2f}s")
    
    # Event loop oluştur ve ana asenkron işlemi çalıştır
    try:
        # Python 3.7+ için
        asyncio.run(main_async_processing())
    except AttributeError:
        # Eski Python sürümleri için
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main_async_processing())
    
    print(f"\n✅ İndeksleme tamamlandı!")
    print(f"📊 İstatistikler:")
    print(f"  - Toplam dosya: {stats['total_blobs']}")
    print(f"  - Başarılı dosya: {stats['successful']}")
    print(f"  - Başarısız dosya: {stats['failed']}")
    print(f"  - Toplam parça: {stats['total_chunks']}")
    print(f"  - İndekslenen parça: {stats['indexed_chunks']}")
    print(f"  - Toplam batch: {stats['total_batches']}")
    print(f"  - Başarılı batch: {stats['successful_batches']}")
    
    return stats

if __name__ == "__main__":
    print("=" * 50)
    print("Azure AI Search İndeks Oluşturma ve İndeksleme (SDK)")
    print("=" * 50)
    
    action = input("İşlem seçin:\n1. İndeks oluştur\n2. İndeksi sil\n3. Blob içeriklerini indeksle\n4. Tümünü yap (indeksi sil, yeniden oluştur ve indeksle)\n5. İndeks istatistiklerini göster\n6. Paralel embeddings ile indeksle (sadece değişenler)\n7. Paralel embeddings ile indeksle (tüm dosyalar)\nSeçiminiz: ")
    
    # Optimize edilmiş default parametreler
    chunk_size = 200    # Daha küçük chunk boyutu
    overlap = 20        # Daha az örtüşme
    batch_size = 5      # Daha küçük batch boyutu
    max_concurrent = 5  # Eşzamanlı embedding işlemi sayısı
    
    print(f"\n⚙️ Optimize Edilmiş Ayarlar:")
    print(f"  - Chunk boyutu: {chunk_size} karakter")
    print(f"  - Örtüşme: {overlap} karakter")
    print(f"  - Upload batch boyutu: {batch_size} belge")
    print(f"  - Maksimum eşzamanlı işlem: {max_concurrent}")
    
    if action == "1":
        create_search_index()
    elif action == "2":
        delete_search_index()
    elif action == "3":
        try:
            print("\n🔍 Blob listesi alınıyor...")
            blobs = list_blobs()
            
            if not blobs:
                print("❌ İndekslenecek blob bulunamadı.")
                sys.exit(0)
                
            print(f"✅ {len(blobs)} blob bulundu:")
            for i, blob in enumerate(blobs[:10]):  # İlk 10 dosyayı göster
                print(f"  {i+1}. {blob['name']} ({blob['size']} bayt)")
            
            if len(blobs) > 10:
                print(f"  ... ve {len(blobs) - 10} dosya daha.")
            
            # Doğrudan indeksleme işlemini başlat (filtreleme sorusu kaldırıldı)
            print("\n🚀 Tüm bloblar indeksleniyor...")
            index_with_parallel_embeddings(
                blobs, 
                chunk_size=chunk_size, 
                overlap=overlap,
                batch_size=batch_size,
                max_concurrent_embeddings=max_concurrent,
                process_only_changed=False  # Tüm dosyaları işle
            )
            
        except Exception as e:
            print(f"❌ İndeksleme hatası: {str(e)}")
            
    elif action == "4":
        try:
            confirm = input("\nBu işlem mevcut indeksi SİLİP yeniden oluşturacak. Devam etmek istiyor musunuz? (E/H): ").lower()
            if confirm != 'e' and confirm != 'evet':
                print("İşlem iptal edildi.")
                sys.exit(0)
                
            # İndeksi sil ve yeniden oluştur
            delete_search_index()
            create_search_index()
            
            print("\n🔍 Blob listesi alınıyor...")
            blobs = list_blobs()
            
            if not blobs:
                print("❌ İndekslenecek blob bulunamadı.")
                sys.exit(0)
                
            print(f"✅ {len(blobs)} blob bulundu:")
            for i, blob in enumerate(blobs[:10]):  # İlk 10 dosyayı göster
                print(f"  {i+1}. {blob['name']} ({blob['size']} bayt)")
            
            if len(blobs) > 10:
                print(f"  ... ve {len(blobs) - 10} dosya daha.")
            
            # Doğrudan indeksleme işlemini başlat (filtreleme sorusu kaldırıldı)
            print("\n🚀 Tüm bloblar indeksleniyor...")
            index_with_parallel_embeddings(
                blobs, 
                chunk_size=chunk_size, 
                overlap=overlap,
                batch_size=batch_size,
                max_concurrent_embeddings=max_concurrent,
                process_only_changed=False  # Bu işlemde zaten yeni indeks oluşturulduğu için tüm dosyaları işle
            )
            
        except Exception as e:
            print(f"❌ İndeksleme hatası: {str(e)}")
    elif action == "5":
        get_index_statistics()
    elif action == "6":
        try:
            print("\n🔍 Blob listesi alınıyor...")
            blobs = list_blobs()
            
            if not blobs:
                print("❌ İndekslenecek blob bulunamadı.")
                sys.exit(0)
                
            print(f"✅ {len(blobs)} blob bulundu:")
            for i, blob in enumerate(blobs[:10]):  # İlk 10 dosyayı göster
                print(f"  {i+1}. {blob['name']} ({blob['size']} bayt)")
            
            if len(blobs) > 10:
                print(f"  ... ve {len(blobs) - 10} dosya daha.")
            
            # Doğrudan indeksleme işlemini başlat (filtreleme sorusu kaldırıldı) 
            print(f"\n🚀 Paralel embeddings ile SADECE YENİ veya DEĞİŞEN bloblar indeksleniyor (maksimum {max_concurrent} eşzamanlı istek)...")
            print(f"  ℹ️ Bu seçenek sadece indekste olmayan veya değişen dosyaları işleyerek zaman kazandırır")
            index_with_parallel_embeddings(
                blobs, 
                chunk_size=chunk_size, 
                overlap=overlap,
                batch_size=batch_size,
                max_concurrent_embeddings=max_concurrent,
                process_only_changed=True  # Sadece değişen dosyaları işle
            )
            
        except Exception as e:
            print(f"❌ İndeksleme hatası: {str(e)}")
    elif action == "7":
        try:
            print("\n🔍 Blob listesi alınıyor...")
            blobs = list_blobs()
            
            if not blobs:
                print("❌ İndekslenecek blob bulunamadı.")
                sys.exit(0)
                
            print(f"✅ {len(blobs)} blob bulundu:")
            for i, blob in enumerate(blobs[:10]):  # İlk 10 dosyayı göster
                print(f"  {i+1}. {blob['name']} ({blob['size']} bayt)")
            
            if len(blobs) > 10:
                print(f"  ... ve {len(blobs) - 10} dosya daha.")
            
            # Doğrudan indeksleme işlemini başlat (filtreleme sorusu kaldırıldı) 
            print(f"\n🚀 Paralel embeddings ile TÜM bloblar indeksleniyor (maksimum {max_concurrent} eşzamanlı istek)...")
            index_with_parallel_embeddings(
                blobs, 
                chunk_size=chunk_size, 
                overlap=overlap,
                batch_size=batch_size,
                max_concurrent_embeddings=max_concurrent,
                process_only_changed=False  # Tüm dosyaları işle 
            )
            
        except Exception as e:
            print(f"❌ İndeksleme hatası: {str(e)}")
    else:
        print("❌ Geçersiz seçim.") 