# test_vector_query.py

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.ai_search_query import vector_search
from config.settings import AZURE_SEARCH_INDEX_NAME

def test_search():
    prompt = input("🔍 Soru gir: ")
    print(f"⏳ '{prompt}' için arama yapılıyor...")
    
    try:
        results = vector_search(prompt)
        
        if not results:
            print("❌ Hiçbir sonuç bulunamadı.")
            return
        
        print("\n📄 Bulunan Dökümanlar:")
        for i, doc in enumerate(results, 1):
            print(f"\n{i}. {doc.get('metadata_storage_name', 'Adsız Belge')}")
            print(f"   Path: {doc.get('metadata_storage_path', 'Bilinmiyor')}")

            content = doc.get('content', '')
            if content:
                preview = content[:300] + "..." if len(content) > 300 else content
                print(f"   İçerik Önizleme:\n   {preview}")
    
    except Exception as e:
        print(f"\n❌ Hata: {str(e)}")
        
