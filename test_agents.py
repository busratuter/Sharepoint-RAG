import asyncio
from modules.agents.smart_search_agents import SmartSearchRunner

async def test():
    runner = SmartSearchRunner()
    test_query = "Mindworks ve Microsoft arasınnda yapıla sözleşmelerdeki gizlilik maddelerini bul"
    
    print("\n=== Test Başlıyor ===")
    print(f"Sorgu: {test_query}")
    result = await runner.run(test_query)
    
    print("\n1. İlk Filtreleme Sonuçları:")
    print(f"İlk bağlam: {result['initial_context']}")
    print(f"Filtrelenen belge sayısı: {result['filtered_docs']}")
    
    print("\n2. İkinci Filtreleme Sonuçları:")
    print(f"İkinci bağlam: {result['secondary_context']}")
    print(f"Son arama konusu: {result['final_topic']}")
    
    print("\n3. Son Aşama Sonuçları:")
    if result["relevant_sections"]:
        print(f"İlgili bölüm sayısı: {len(result['relevant_sections'])}")
        print("\nBulunan bölümler:")
        for i, section in enumerate(result["relevant_sections"], 1):
            print(f"\nBölüm {i}:")
            print(f"Belge: {section['document_name']}")
            print(f"Dosya türü: {section['file_type']}")
            print(f"Son güncelleme: {section['last_updated']}")
            print(f"Skor: {section['score']}")
            print(f"İçerik:\n{section['section']}")
            print("-" * 80)
    else:
        print("İlgili bölüm bulunamadı")

if __name__ == "__main__":
    asyncio.run(test()) 




    