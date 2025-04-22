import os
import sys

# Projenin kök dizinine erişebilmek için path ayarlaması
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.get_file_list_from_sharepoint import get_access_token
from modules.rag_agent import rag_query
from modules.upload_to_blob import upload_sharepoint_file_to_blob_stream
from modules.utils import embed_query
from config.settings import (
    SITE_ID, 
    AZURE_SEARCH_ENDPOINT,
    AZURE_SEARCH_KEY,
    AZURE_SEARCH_INDEX_NAME,
    AZURE_SEARCH_API_VERSION,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
    AZURE_OPENAI_API_VERSION
)
import json
import logging

# Loglama yapılandırması
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("api_test")

# API isteklerini detaylı görmek için requests kütüphanesinin loglamasını açalım
import http.client as http_client
http_client.HTTPConnection.debuglevel = 1
requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.DEBUG)
requests_log.propagate = True

def check_config():
    """Konfigürasyon değerlerini kontrol eder"""
    logger.info("Konfigürasyon kontrol ediliyor...")
    
    config_values = {
        "AZURE_SEARCH_ENDPOINT": AZURE_SEARCH_ENDPOINT,
        "AZURE_SEARCH_KEY": AZURE_SEARCH_KEY[:5] + "..." if AZURE_SEARCH_KEY else "",
        "AZURE_SEARCH_INDEX_NAME": AZURE_SEARCH_INDEX_NAME,
        "AZURE_SEARCH_API_VERSION": AZURE_SEARCH_API_VERSION,
        "AZURE_OPENAI_ENDPOINT": AZURE_OPENAI_ENDPOINT,
        "AZURE_OPENAI_API_KEY": AZURE_OPENAI_API_KEY[:5] + "..." if AZURE_OPENAI_API_KEY else "",
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
        "AZURE_OPENAI_API_VERSION": AZURE_OPENAI_API_VERSION
    }
    
    all_good = True
    missing_values = []
    
    for key, value in config_values.items():
        if not value or value == "...":
            logger.error(f"❌ {key} eksik veya boş!")
            missing_values.append(key)
            all_good = False
        else:
            logger.info(f"✅ {key}: {value}")
    
    if not all_good:
        logger.error(f"Eksik konfigürasyon değerleri bulundu: {', '.join(missing_values)}")
    
    return all_good

def test_embedding():
    """Embedding API'sini test eder"""
    # Utils modülünden import edilen fonksiyonu kullan
    # Artık embed_query asenkron fonksiyonu çağıracak şekilde düzenlendi
    logger.info("Embedding API test ediliyor...")
    test_text = "Bu bir test metnidir."
    
    try:
        embedding = embed_query(test_text)
        logger.info(f"✅ Embedding başarılı! Vektör boyutu: {len(embedding)}")
        logger.info(f"Vektör örneği (ilk 5 değer): {embedding[:5]}")
        return True
    except Exception as e:
        logger.error(f"❌ Embedding hatası: {str(e)}", exc_info=True)
        return False

def test_search():
    """Search API'sini test eder"""
    from modules.vector_search import vector_search
    
    logger.info("Search API test ediliyor...")
    test_query = "test"
    
    try:
        results = vector_search(test_query, top_k=1)
        logger.info(f"✅ Arama başarılı! Sonuç sayısı: {len(results)}")
        if results:
            logger.info(f"İlk sonuç: {json.dumps(results[0], ensure_ascii=False, indent=2)}")
        else:
            logger.info("Sonuç bulunamadı, ancak API çalışıyor")
        return True
    except Exception as e:
        logger.error(f"❌ Arama hatası: {str(e)}", exc_info=True)
        return False

def test_rag():
    try:
        # Önce konfigürasyonu kontrol et
        if not check_config():
            print("❌ Konfigürasyon değerlerinde eksiklik var. Lütfen .env dosyasını kontrol edin.")
            return
        
        # Embedding API'sini test et
        if not test_embedding():
            print("❌ Embedding API'si çalışmıyor. Diğer testlere devam edilemiyor.")
            return
        
        # Search API'sini test et
        if not test_search():
            print("❌ Search API'si çalışmıyor. Diğer testlere devam edilemiyor.")
            return
        
        soru = input("Sorunu gir: ")
        logger.info(f"Kullanıcı sorusu: {soru}")
        
        # Önce vector_search işlemini detaylı görelim
        from modules.vector_search import vector_search
        logger.info("Vector arama işlemi başlatılıyor...")
        search_results = vector_search(soru, top_k=3)
        
        # Sonuçları inceleyelim
        logger.info(f"Vector arama sonuçları: {json.dumps(search_results, indent=2, ensure_ascii=False)[:500]}...")
        
        # RAG ile cevap alalım
        logger.info("RAG işlemi başlatılıyor...")
        sonuc = rag_query(soru, search_type="vector", top_k=3)
        
        print("\n" + "=" * 50)
        print("📝 CEVAP:")
        print(sonuc["answer"])
        
        if sonuc["sources"]:
            print("\n📚 KAYNAKLAR:")
            for kaynak in sonuc["sources"]:
                print(f"- {kaynak}")
        
        print("=" * 50)
        
    except Exception as e:
        logger.error(f"Hata oluştu: {str(e)}", exc_info=True)
        print(f"❌ Bir hata oluştu: {str(e)}")

if __name__ == "__main__":
    test_rag()
