import os
import sys
import json
import time
import schedule
import argparse
import logging
from datetime import datetime
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from typing import Any, List, Dict, Optional
from pathlib import Path

# Azure Core loglama seviyesini ERROR'a ayarla
logging.getLogger('azure.core').setLevel(logging.ERROR)

# Loglama ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("sync_agent.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("sync_agent")

# Modüllerimizi import ediyoruz
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from modules.get_file_list_from_sharepoint import get_access_token, get_file_list, save_file_list_to_json
from modules.upload_to_blob import upload_sharepoint_file_to_blob_stream
from config.settings import SITE_ID, BLOB_CONNECTION_STRING, BLOB_CONTAINER_NAME, DATA_DIR, FILE_LIST_PATH

# Dosyaların son durumunu kaydetmek için kullanacağımız dosya
LAST_SYNC_FILE = os.path.join(DATA_DIR, "last_sync.json")

def get_blob_list():
    """Blob Storage'daki dosyaların listesini ve son değiştirilme tarihlerini alır"""
    try:
        # Blob Storage bağlantısı oluştur
        blob_service_client = BlobServiceClient.from_connection_string(BLOB_CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(BLOB_CONTAINER_NAME)
        
        # Blob'ları listele
        blobs = {}
        for blob in container_client.list_blobs():
            blobs[blob.name] = {
                "last_modified": blob.last_modified.isoformat() if blob.last_modified else None
            }
        return blobs
    except Exception as e:
        logger.error(f"Blob listesi alınamadı: {str(e)}")
        return {}

def load_last_sync_info():
    """Son senkronizasyon bilgilerini yükler"""
    if os.path.exists(LAST_SYNC_FILE):
        try:
            with open(LAST_SYNC_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Son senkronizasyon bilgileri yüklenemedi: {str(e)}")
    return {"files": {}, "last_sync_time": None}

def save_last_sync_info(sync_info):
    """Son senkronizasyon bilgilerini kaydeder"""
    os.makedirs(os.path.dirname(LAST_SYNC_FILE), exist_ok=True)
    try:
        with open(LAST_SYNC_FILE, 'w', encoding='utf-8') as f:
            json.dump(sync_info, f, indent=4)
    except Exception as e:
        logger.error(f"Son senkronizasyon bilgileri kaydedilemedi: {str(e)}")

# SharePoint -> Blob Storage senkronizasyon işlevi
def sync_sharepoint_to_blob(force_sync=False):
    """
    SharePoint'teki değişen veya yeni dosyaları Azure Blob Storage'a senkronize eden işlev
    """
    logger.info(f"SharePoint -> Blob senkronizasyonu başlatılıyor (Force sync: {force_sync})...")
    
    # SharePoint'ten dosya listesi al
    try:
        token = get_access_token()
        sharepoint_files = get_file_list(token)
        save_file_list_to_json(sharepoint_files)
    except Exception as e:
        logger.error(f"SharePoint dosya listesi alınamadı: {str(e)}")
        return {"error": f"SharePoint dosya listesi alınamadı: {str(e)}"}
    
    # Son senkronizasyon bilgilerini yükle (eğer force_sync değilse)
    last_sync_info = {} if force_sync else load_last_sync_info()
    last_sync_files = last_sync_info.get("files", {})
    
    # Blob Storage'daki mevcut dosyaları kontrol et
    blob_files = {} if force_sync else get_blob_list()
    
    results = {
        "success": 0,
        "failed": 0,
        "total": len(sharepoint_files),
        "new_files": 0,
        "updated_files": 0,
        "unchanged_files": 0,
        "files_synced": [],
        "files_failed": [],
        "sync_time": datetime.now().isoformat()
    }
    
    # Yeni senkronizasyon bilgisi oluştur
    new_sync_info = {
        "files": {},
        "last_sync_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    
    for file in sharepoint_files:
        file_name = file["name"]
        last_modified = file.get("last_modified")
        
        # Dosya değiştirilmiş, yeni eklenmiş veya zorla senkronizasyon istenmiş mi kontrol et
        is_new = file_name not in blob_files
        is_changed = False if is_new else (last_modified != last_sync_files.get(file_name, {}).get("last_modified"))
        
        # Yeni veya değişmiş dosyaları ya da force_sync durumunda tüm dosyaları işle
        if force_sync or is_new or is_changed:
            try:
                upload_sharepoint_file_to_blob_stream(token, SITE_ID, file)
                
                # Sonuçları güncelle
                results["success"] += 1
                if is_new:
                    results["new_files"] += 1
                    status = "Yeni dosya yüklendi"
                    print(f"✅ {status}: {file_name}")
                elif is_changed:
                    results["updated_files"] += 1
                    status = "Değişen dosya güncellendi"
                    print(f"✅ {status}: {file_name}")
                else:  # force_sync
                    status = "Dosya yeniden yüklendi"
                    print(f"✅ {status}: {file_name}")
                
                results["files_synced"].append({
                    "name": file_name,
                    "status": status,
                    "destination": f"azure-blob://{BLOB_CONTAINER_NAME}/{file_name}"
                })
                
                # Son senkronizasyon bilgilerini güncelle
                new_sync_info["files"][file_name] = {
                    "last_modified": last_modified,
                    "sharepoint_id": file.get("sharepoint_id")
                }
                
                # Kısa bir bekleme
                time.sleep(0.5)
                
            except Exception as e:
                results["failed"] += 1
                results["files_failed"].append({
                    "name": file_name,
                    "error": str(e)
                })
                print(f"❌ Dosya yükleme hatası: {file_name} - {str(e)}")
        else:
            # Değişmemiş dosyaları kaydet
            results["unchanged_files"] += 1
            print(f"⏩ Değişiklik yok, atlanıyor: {file_name}")
            
            # Değişmeyen dosyaların bilgilerini de yeni senkronizasyon bilgisine ekle
            new_sync_info["files"][file_name] = {
                "last_modified": last_modified,
                "sharepoint_id": file.get("sharepoint_id")
            }
    
    # Senkronizasyon bilgilerini kaydet
    save_last_sync_info(new_sync_info)
    
    # Senkronizasyon sonuçlarını raporla
    logger.info(f"\nSenkronizasyon tamamlandı!")
    logger.info(f"Toplam dosya: {results['total']}")
    logger.info(f"Yeni yüklenen: {results['new_files']}")
    logger.info(f"Güncellenen: {results['updated_files']}")
    logger.info(f"Değişmeyen (atlandı): {results['unchanged_files']}")
    logger.info(f"Başarısız: {results['failed']}")
    
    # Özet bilgisini son senkronizasyon raporu olarak kaydet
    results_file = os.path.join(DATA_DIR, "last_sync_results.json")
    try:
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=4)
    except Exception as e:
        logger.error(f"Senkronizasyon sonuçları kaydedilemedi: {str(e)}")
    
    return results

def scheduled_sync_job():
    """Zamanlanmış senkronizasyon işi"""
    logger.info(f"Zamanlanmış senkronizasyon işi başlatılıyor - {datetime.now()}")
    try:
        sync_sharepoint_to_blob(force_sync=False)
        logger.info(f"Zamanlanmış senkronizasyon işi tamamlandı - {datetime.now()}")
    except Exception as e:
        logger.error(f"Zamanlanmış senkronizasyon sırasında hata: {str(e)}")

def run_agent(interval_minutes=1, run_once=False):
    """Agent'ı çalıştır"""
    logger.info(f"Sync Agent başlatılıyor. Senkronizasyon aralığı: {interval_minutes} dakika")
    
    if run_once:
        logger.info("Tek seferlik çalışma modu seçildi")
        sync_sharepoint_to_blob(force_sync=False)
        return
    
    # İlk çalıştırma
    sync_sharepoint_to_blob(force_sync=False)
    
    # Schedule'ı ayarla
    schedule.every(interval_minutes).minutes.do(scheduled_sync_job)
    
    logger.info(f"Sync Agent arka planda çalışıyor. Senkronizasyon aralığı: {interval_minutes} dakika")
    
    # Sürekli çalışma döngüsü
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)  # 1 saniyede bir kontrol et (daha hızlı tepki için)
    except KeyboardInterrupt:
        logger.info("Sync Agent kullanıcı tarafından durduruldu")
    except Exception as e:
        logger.error(f"Sync Agent çalışırken hata oluştu: {str(e)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='SharePoint-Blob Sync Agent')
    parser.add_argument('--interval', type=int, default=1, help='Senkronizasyon aralığı (dakika)')
    parser.add_argument('--once', action='store_true', help='Sadece bir kez çalıştır')
    parser.add_argument('--force', action='store_true', help='Force sync yap')
    args = parser.parse_args()
    
    if args.force:
        logger.info("Force sync işlemi başlatılıyor")
        sync_sharepoint_to_blob(force_sync=True)
    else:
        run_agent(interval_minutes=args.interval, run_once=args.once) 