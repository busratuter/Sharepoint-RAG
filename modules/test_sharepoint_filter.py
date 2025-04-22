"""
SharePoint Filtre Botu için test script'i

Bu modül, SharePoint Filtre Botu'nun işlevlerini test eder.
"""
import sys
import os
import asyncio

# Modüller dizinini import yoluna ekle
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.sharepoint_filter_bot import SharePointFilterBot

async def test_filter_bot():
    """
    SharePoint filtreleme botunu test eder
    """
    print("=" * 70)
    print("SharePoint Filtre Botu Test")
    print("=" * 70)
    
    # Test için benzerlik skoru ayarla (daha fazla sonuç görmek için düşük olabilir)
    min_score = 0.5
    print(f"🔢 Test için minimum benzerlik skoru: {min_score}")
    
    # Botu başlat
    bot = SharePointFilterBot(min_similarity_score=min_score)
    
    # Test sorguları
    test_queries = [
        "Finansal raporlar hakkında bilgi",
        "Proje planı 2023",
        "İnsan kaynakları politikaları"
    ]
    
    for query in test_queries:
        print("\n" + "-" * 70)
        print(f"🔍 Test sorgusu: '{query}'")
        print("-" * 70)
        
        # Vector search ile test
        print("\n📊 Vector arama sonuçları:")
        sharepoint_ids, file_details = await bot.search_and_filter(
            query=query, 
            search_type="vector",
            top_k=5
        )
        
        print(f"  🔢 Bulunan SharePoint ID'leri: {len(sharepoint_ids)}")
        print(f"  🔢 Bulunan dosya detayları: {len(file_details)}")
        
        # Sonuçları formatlı şekilde göster
        if file_details:
            print(bot.format_results(file_details))
            
            # Sonuçları JSON dosyasına kaydet
            output_path = f"data/test_{query.replace(' ', '_')[:10]}.json"
            result = bot.save_results_to_json(file_details, output_path)
            print(result)
        else:
            print("❌ Bu sorgu için sonuç bulunamadı.")
        
        # Biraz bekle (rate limit vb. için)
        await asyncio.sleep(1)
        
        # Hybrid search ile test
        print("\n📊 Hybrid arama sonuçları:")
        sharepoint_ids, file_details = await bot.search_and_filter(
            query=query, 
            search_type="hybrid",
            top_k=5
        )
        
        print(f"  🔢 Bulunan SharePoint ID'leri: {len(sharepoint_ids)}")
        print(f"  🔢 Bulunan dosya detayları: {len(file_details)}")
        
        # Sonuçları formatlı şekilde göster
        if file_details:
            print(bot.format_results(file_details))
        else:
            print("❌ Bu sorgu için hybrid aramada sonuç bulunamadı.")
        
        # İki sorgu arasında biraz bekle
        await asyncio.sleep(2)
    
    print("\n" + "=" * 70)
    print("✅ Test tamamlandı!")
    print("=" * 70)

def main():
    """
    Asenkron test fonksiyonunu çalıştır
    """
    try:
        asyncio.run(test_filter_bot())
    except KeyboardInterrupt:
        print("\n⚠️ Test kullanıcı tarafından sonlandırıldı.")
    except Exception as e:
        print(f"\n❌ Test sırasında hata oluştu: {str(e)}")

if __name__ == "__main__":
    main() 