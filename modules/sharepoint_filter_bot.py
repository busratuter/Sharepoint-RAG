"""
SharePoint Dosya Filtreleme Botu

Bu modül, kullanıcı sorgusu ve benzerlik skoru üzerinden 
SharePoint belgelerini bulup filtrelemeyi sağlar.
"""
import os
import sys
import json
import asyncio
from typing import List, Dict, Any, Optional, Tuple, Union

# Projenin kök dizinine erişebilmek için path ayarlaması
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import (
    AZURE_SEARCH_ENDPOINT,
    AZURE_SEARCH_KEY,
    AZURE_SEARCH_INDEX_NAME
)

# Sadece hybrid search kullanacağız
from modules.vector_search import hybrid_search
from modules.get_file_list_from_sharepoint import get_access_token, get_file_list

class SharePointFilterBot:
    """
    SharePoint belgeleri için filtreleme botu.
    
    Kullanıcının verdiği sorguya göre, belgeler bulur ve 
    bu belgelerin ait olduğu dosyaları SharePoint'ten getirir.
    """
    
    def __init__(self, min_similarity_score: float = 0.3, min_search_score: float = 0.2):
        """
        Bot sınıfını başlatır
        
        Parameters:
        -----------
        min_similarity_score: float
            Kabul edilecek minimum benzerlik skoru (0-1 arası)
        min_search_score: float
            AI Search sonuçları için minimum benzerlik skoru (0-1 arası)
        """
        self.min_similarity_score = min_similarity_score
        self.min_search_score = min_search_score
        self.filtered_results = []  # Eşleştirme için kullanılan ara sonuçlar
        print(f"🤖 SharePoint Filtre Botu başlatıldı")
    
    async def process_query(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        Kullanıcı sorgusunu işler ve ilgili dosyaları döndürür
        
        Parameters:
        -----------
        query: str
            Kullanıcı sorgusu
        top_k: int
            Dönecek maksimum sonuç sayısı
            
        Returns:
        --------
        List[Dict[str, Any]]
            Filtrelenmiş dosyaların detayları
        """
        print(f"🔍 '{query}' sorgusuyla arama yapılıyor...")
        
        # Hybrid arama yap (hem metin hem vektör tabanlı) - Top_K değerini biraz artırarak daha fazla sonuç alalım
        search_results = await hybrid_search(query, top_k=top_k*2)
        
        # AI Search sonuçlarını min_search_score değerine göre filtrele
        filtered_search_results = self._filter_search_results(search_results)
        search_results = filtered_search_results[:top_k]  # En yüksek skorlu top_k sonucu al
        
        # Sonuçları logla
        print(f"  📊 Toplam {len(search_results)} sonuç işlenecek")
        
        if not search_results:
            print("❌ Arama sonuçları bulunamadı veya minimum skoru geçemediler")
            return []
        
        # Hata ayıklama: Sonuçların yapısını göster
        if search_results:
            self._log_first_result(search_results[0])
        
        # AI Search sonuçlarından dosya adlarını topla
        unique_filenames, filtered_results = self._extract_filenames(search_results)
        self.filtered_results = filtered_results  # Sınıf üyesi olarak sakla
        
        print(f"  📑 Benzersiz dosya adları: {list(unique_filenames)}")
        
        # Dosya adı bulunamadı mı?
        if not unique_filenames:
            print("⚠️ Arama sonuçlarında tanımlı dosya adı bulunamadı!")
            print("  🔍 ID'lerden dosya adı çıkarmayı deniyorum...")
            
            # ID üzerinden dosya adı çıkarma (daha agresif)
            unique_filenames, filtered_results = self._extract_filenames_from_ids(search_results)
            self.filtered_results = filtered_results
            
            print(f"  📑 ID'lerden çıkarılan dosya adları: {list(unique_filenames)}")
        
        # Yine bulunamadı mı?
        if not unique_filenames:
            print("⚠️ Hiçbir şekilde dosya adı bulunamadı")
            return []
        
        # SharePoint'ten dosya listesi al ve eşleştir
        try:
            access_token = get_access_token()
            sharepoint_files = get_file_list(access_token)
            print(f"  📂 SharePoint'ten {len(sharepoint_files)} dosya alındı")
            
            # Bulunan dosya adlarını SharePoint dosyalarıyla eşleştir
            matched_files = self._match_filenames_with_sharepoint(list(unique_filenames), sharepoint_files)
            
            if not matched_files:
                print("⚠️ Bulunan dosyaların hiçbiri SharePoint'te eşleştirilemedi")
                return []
            
            return matched_files
            
        except Exception as e:
            print(f"❌ SharePoint dosya listesi alınırken hata: {str(e)}")
            return []

    def _filter_search_results(self, search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """AI Search sonuçlarını min_search_score değerine göre filtreler"""
        filtered_results = []
        if not search_results:
            return filtered_results
            
        print(f"  📊 Toplam {len(search_results)} arama sonucu alındı")
        print(f"  🔍 Minimum arama skoru {self.min_search_score} ile filtreleniyor...")
        
        for result in search_results:
            score = result.get('@search.score', 0)
            if score >= self.min_search_score:
                filtered_results.append(result)
                print(f"    ✅ Sonuç dahil edildi: {result.get('id', 'Bilinmeyen ID')} (Score: {score:.4f})")
            else:
                print(f"    ❌ Sonuç filtrelendi: {result.get('id', 'Bilinmeyen ID')} (Score: {score:.4f} < {self.min_search_score})")
        
        print(f"  🔢 AI Search: {len(filtered_results)}/{len(search_results)} sonuç filtreleme sonrası kaldı")
        return filtered_results
        
    def _log_first_result(self, result: Dict[str, Any]) -> None:
        """Hata ayıklama için ilk sonucu loglar"""
        print(f"  🔍 İlk sonuç anahtarları: {list(result.keys())}")
        print(f"  🔍 İlk sonuç örneği: {json.dumps(result)[:200]}...")
    
    def _extract_filenames(self, results: List[Dict[str, Any]]) -> Tuple[set, List[Dict[str, Any]]]:
        """Arama sonuçlarından dosya adlarını çıkarır"""
        unique_filenames = set()
        filtered_results = []
        
        for result in results:
            score = result.get('@search.score', 0)
            
            # Dosya adı alanını farklı biçimlerde kontrol et
            file_name = self._get_filename_from_result(result)
            
            if file_name and file_name not in unique_filenames:
                unique_filenames.add(file_name)
                filtered_results.append({
                    'file_name': file_name,
                    'score': score,
                    'content_preview': result.get('content', '')[:100] + '...' if result.get('content') else '',
                    'chunk_id': result.get('chunk_id', '') or result.get('id', '')
                })
        
        return unique_filenames, filtered_results
    
    def _get_filename_from_result(self, result: Dict[str, Any]) -> Optional[str]:
        """Sonuç içindeki olası dosya adı alanlarını kontrol eder"""
        if 'file_name' in result:
            return result['file_name']
        elif 'filename' in result:
            return result['filename']
        elif 'fileName' in result:
            return result['fileName'] 
        elif 'metadata_storage_name' in result:
            return result['metadata_storage_name']
        elif 'id' in result:
            # ID'den dosya adını çıkarmaya çalış
            id_parts = result['id'].split('_')
            if len(id_parts) >= 2:
                # ID genellikle dosyaAdı_chunkNo şeklinde olur
                possible_name = '_'.join(id_parts[:-1])
                if '.' in possible_name:  # Bir uzantı içeriyorsa
                    return possible_name
        return None
    
    def _extract_filenames_from_ids(self, results: List[Dict[str, Any]]) -> Tuple[set, List[Dict[str, Any]]]:
        """ID değerlerinden dosya adlarını çıkarır (agresif yöntem)"""
        unique_filenames = set()
        filtered_results = []
        
        for result in results:
            id_value = result.get('id', '')
            if id_value:
                # Dosya adı_chunk_id biçimindeki ID'lerden adı ayıkla
                id_parts = id_value.split('_')
                # Son kısmı (muhtemelen chunk ID) at
                possible_name = '_'.join(id_parts[:-1])
                if possible_name and possible_name not in unique_filenames:
                    unique_filenames.add(possible_name)
                    filtered_results.append({
                        'file_name': possible_name,
                        'score': result.get('@search.score', 0),
                        'content_preview': result.get('content', '')[:100] + '...' if result.get('content') else '',
                        'chunk_id': id_value
                    })
        
        return unique_filenames, filtered_results
    
    async def _get_all_sharepoint_files(self) -> List[Dict[str, Any]]:
        """Dosya adı bulunamadığında SharePoint dosyalarını döndürür"""
        print("⚠️ Hiçbir şekilde dosya adı bulunamadı, SharePoint'ten dosyaların listesi alınıyor")
        
        try:
            access_token = get_access_token()
            sharepoint_files = get_file_list(access_token)
            print(f"  📂 SharePoint'ten {len(sharepoint_files)} dosya alındı")
            
            # Tüm dosyaların eşleşmediğini belirt
            for file in sharepoint_files:
                file['is_sharepoint_match'] = False
                file['score'] = 0.0  # Skor olmadığını belirt
            
            return sharepoint_files
        except Exception as e:
            print(f"❌ SharePoint dosya listesi alınırken hata: {str(e)}")
            return []
    
    def _match_filenames_with_sharepoint(self, filenames: List[str], sharepoint_files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        AI Search'ten gelen dosya adlarını SharePoint dosyalarıyla eşleştirir
        """
        # Dosya adları ve bilgilerini bir sözlük yapısında tut
        filenames_info = {}
        for result in self.filtered_results:
            file_name = result.get('file_name')
            if file_name:
                filenames_info[file_name] = result
        
        # Dosya adlarını normalleştir
        normalized_filenames = {self._normalize_filename(f): f for f in filenames}
        print(f"  🔍 Normalleştirilmiş dosya adları: {list(normalized_filenames.keys())}")
        
        # SharePoint dosyalarını normalleştirilmiş adlarıyla hazırla
        name_to_sharepoint = {}
        for file in sharepoint_files:
            name = file.get('name', '')
            if name:
                normalized = self._normalize_filename(name)
                name_to_sharepoint[normalized] = file
                # Uzantısız ismi de ekle
                if '.' in normalized:
                    base_name = normalized.rsplit('.', 1)[0]
                    name_to_sharepoint[base_name] = file
        
        print(f"  🔍 SharePoint dosya adları: {list(name_to_sharepoint.keys())}")
        
        # Eşleşmeleri bul
        matched_files = []
        matched_count = 0
        
        for norm_name, original_name in normalized_filenames.items():
            # İlgili dosyanın diğer bilgilerini al (skor vb.)
            file_info = filenames_info.get(original_name, {})
            score = file_info.get('score', 0)
            
            # Tam eşleşme ara
            if norm_name in name_to_sharepoint:
                sp_file = name_to_sharepoint[norm_name].copy()  # Orijinal dosyayı kopyalayarak değiştir
                sp_file['is_sharepoint_match'] = True
                sp_file['score'] = score  # Skoru ekle
                matched_files.append(sp_file)
                matched_count += 1
                print(f"  ✅ Eşleşme bulundu: {original_name} -> {sp_file.get('name')} (Skor: {score:.2f})")
                continue
                
            # Uzantısız isimle ara
            if '.' in norm_name:
                base_name = norm_name.rsplit('.', 1)[0]
                if base_name in name_to_sharepoint:
                    sp_file = name_to_sharepoint[base_name].copy()
                    sp_file['is_sharepoint_match'] = True
                    sp_file['score'] = score
                    matched_files.append(sp_file)
                    matched_count += 1
                    print(f"  ✅ Uzantısız eşleşme: {original_name} -> {sp_file.get('name')} (Skor: {score:.2f})")
                    continue
            
            # Kısmi eşleşme ara
            found = False
            for sp_norm_name, sp_file in name_to_sharepoint.items():
                if norm_name in sp_norm_name or sp_norm_name in norm_name:
                    sp_file_copy = sp_file.copy()
                    sp_file_copy['is_sharepoint_match'] = True
                    sp_file_copy['score'] = score
                    matched_files.append(sp_file_copy)
                    matched_count += 1
                    print(f"  ✅ Kısmi eşleşme: {original_name} -> {sp_file_copy.get('name')} (Skor: {score:.2f})")
                    found = True
                    break
            
            if not found:
                print(f"  ❌ Eşleşme bulunamadı: {original_name}")
                # Eşleşmeyen dosyaları listeye eklemiyoruz
        
        print(f"  🔢 Toplam {matched_count}/{len(filenames)} dosya SharePoint'te eşleştirildi")
        return matched_files
    
    def _normalize_filename(self, filename: str) -> str:
        """
        Dosya adlarını normalleştirir (küçük harfe çevirir, özel karakterleri kaldırır)
        """
        # Küçük harfe çevir
        normalized = filename.lower()
        
        # Yaygın özel karakterleri kaldır
        normalized = normalized.replace(' ', '_')
        normalized = ''.join(c for c in normalized if c.isalnum() or c in ['_', '.', '-'])
        
        return normalized

    def format_results(self, file_details: List[Dict[str, Any]]) -> str:
        """
        Dosya detaylarını okunabilir formatta döndürür
        """
        if not file_details:
            return "Filtrelenmiş sonuç bulunamadı."
        
        # Sonuçları skora göre sırala (yüksekten düşüğe)
        sorted_files = sorted(
            file_details, 
            key=lambda x: float(x.get("score", 0)) if isinstance(x.get("score"), (int, float, str)) else 0, 
            reverse=True
        )
        
        output = f"\n📄 Bulunan Dosyalar:\n"
        output += f"🔍 Filtreleme ayarları: AI Search min. skor: {self.min_search_score}, Benzerlik min. skor: {self.min_similarity_score}\n"
        
        for i, file in enumerate(sorted_files, 1):
            name = file.get("name", "Bilinmeyen Dosya")
            file_type = file.get("file_type", "")
            size = file.get("size", 0)
            web_url = file.get("web_url", "")
            score = file.get("score", 0)
            
            # Boyutu uygun birime çevir (KB, MB)
            size_str = self._format_file_size(size)
            
            score_str = f" (Benzerlik: {score:.2f})" if score else ""
            output += f"\n{i}. {name}{score_str}\n"
            output += f"   Dosya tipi: {file_type}\n" if file_type else ""
            output += f"   Boyut: {size_str}\n"
            output += f"   URL: {web_url}\n" if web_url else ""
        
        return output
    
    def _format_file_size(self, size: int) -> str:
        """Dosya boyutunu okunaklı formata dönüştürür"""
        if size > 1024*1024:
            return f"{size/(1024*1024):.2f} MB"
        elif size > 1024:
            return f"{size/1024:.2f} KB"
        return f"{size} bayt"

    def save_results_to_json(self, file_details: List[Dict[str, Any]], 
                           output_path: str = "data/filtered_files.json") -> str:
        """
        Dosya detaylarını JSON dosyasına kaydeder
        """
        if not file_details:
            return "Kaydedilecek dosya bulunamadı."
        
        try:
            # Dosya dizinini oluştur (yoksa)
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # JSON formatında kaydet
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(file_details, f, indent=4, ensure_ascii=False)
            
            return f"✅ {len(file_details)} dosya '{output_path}' konumuna kaydedildi."
        except Exception as e:
            return f"❌ Dosya kaydedilirken hata: {str(e)}"

async def interactive_filter_bot():
    """
    Komut satırı üzerinden interaktif filtre botu deneyimi
    """
    print("=" * 50)
    print("SharePoint Filtre Botu")
    print("=" * 50)
    print("Sorgunuza göre SharePoint belgelerini filtreleyebilirsiniz.")
    print("Çıkmak için 'q' veya 'exit' yazın.")
    
    # Varsayılan benzerlik skoru değerlerini ayarla
    default_score = 0.2
    default_search_score = 0.03  # AI search eşik değeri - düşük puanlı sonuçları da göstermek için
    
    # Bot örneği oluştur
    bot = SharePointFilterBot(min_similarity_score=default_score, min_search_score=default_search_score)
    print(f"🤖 SharePoint Filtre Botu başlatıldı")
    
    while True:
        query = input("\n🔍 Ne arıyorsunuz? ")
        
        if query.lower() in ['q', 'exit', 'quit']:
            print("Filtre botu kapatılıyor...")
            break
        
        if not query.strip():
            continue
        
        # Sorguyu işle ve ilgili dosyaları al
        file_details = await bot.process_query(query)
        
        # Sonuçları göster
        print("\n" + "=" * 50)
        print(bot.format_results(file_details))
        print("=" * 50)

if __name__ == "__main__":
    # asyncio.run kullanarak asenkron main fonksiyonu çalıştır
    asyncio.run(interactive_filter_bot()) 