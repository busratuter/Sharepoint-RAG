import os
import sys
import json
from typing import Dict, List, Any

# Modül dizinini ekleyelim
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Modülleri import edelim
from sync_agent_updated import sync_sharepoint_to_blob
from modules.create_search_index_sdk import create_search_index, index_blob_content, list_blobs
from modules.rag_agent import interactive_rag

def main():
    """
    SharePoint-RAG uygulaması ana işlevi
    """
    print("=" * 50)
    print("SharePoint-RAG Sistemi")
    print("=" * 50)
    
    while True:
        print("\nİşlemler:")
        print("1. SharePoint Dosyalarını Azure Blob Storage'a Senkronize Et")
        print("2. AI Search İndeksi Oluştur ve İndeksle")
        print("3. RAG Sistemini Başlat (Soru-Cevap)")
        print("q. Çıkış")
        
        choice = input("\nSeçiminiz: ")
        
        if choice.lower() == 'q':
            print("\nUygulama kapatılıyor...")
            break
        
        if choice == "1":
            # SharePoint senkronizasyon menüsü
            print("\nSenkronizasyon Tipi:")
            print("1. Akıllı senkronizasyon (sadece değişen ve yeni dosyalar)")
            print("2. Zorla senkronizasyon (tüm dosyaları yeniden yükle)")
            print("q. Ana menüye dön")
            
            sync_choice = input("\nSeçiminiz (varsayılan: 1): ") or "1"
            
            if sync_choice.lower() == 'q':
                continue
            
            if sync_choice == "1":
                # Akıllı senkronizasyon
                print("\n🔄 Akıllı senkronizasyon başlatılıyor...")
                result = sync_sharepoint_to_blob(force_sync=False)
                print("\n✅ Senkronizasyon tamamlandı!")
            elif sync_choice == "2":
                # Zorla senkronizasyon
                print("\n🔄 Zorla senkronizasyon başlatılıyor...")
                result = sync_sharepoint_to_blob(force_sync=True)
                print("\n✅ Senkronizasyon tamamlandı!")
            else:
                print("Geçersiz seçim!")
                
        elif choice == "2":
            # AI Search indeks oluşturma ve indeksleme
            print("\nAI Search İşlemleri:")
            print("1. İndeks oluştur")
            print("2. Blob içeriklerini indeksle")
            print("3. Tümünü yap (indeks oluştur ve indeksle)")
            print("q. Ana menüye dön")
            
            index_choice = input("\nSeçiminiz: ")
            
            if index_choice.lower() == 'q':
                continue
                
            if index_choice == "1":
                # İndeks oluştur
                print("\n🔧 AI Search indeksi oluşturuluyor...")
                create_search_index()
                print("\n✅ İndeks oluşturma tamamlandı!")
            elif index_choice == "2":
                # İndeksle
                print("\n🔄 Blob içerikleri indeksleniyor...")
                blobs = list_blobs()
                if blobs:
                    index_blob_content(blobs)
                    print("\n✅ İndeksleme tamamlandı!")
                else:
                    print("\n❌ İndekslenecek blob bulunamadı.")
            elif index_choice == "3":
                # Tümünü yap
                print("\n🔧 AI Search indeksi oluşturuluyor...")
                create_search_index()
                print("\n🔄 Blob içerikleri indeksleniyor...")
                blobs = list_blobs()
                if blobs:
                    index_blob_content(blobs)
                    print("\n✅ İndeksleme tamamlandı!")
                else:
                    print("\n❌ İndekslenecek blob bulunamadı.")
            else:
                print("Geçersiz seçim!")
        
        elif choice == "3":
            # RAG sistemini başlat
            interactive_rag()
        
        else:
            print("Geçersiz seçim! Lütfen tekrar deneyin.")

if __name__ == "__main__":
    main()
