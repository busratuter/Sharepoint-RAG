"""
Streamlit Web Arayüzü - SharePoint Filtre Botu

Bu modül, SharePoint Filtre Botu için Streamlit kullanarak
basit bir web arayüzü sağlar.
"""
import os
import sys
import asyncio
import streamlit as st
from typing import List, Dict, Any, Optional

# Projenin kök dizinine erişebilmek için path ayarlaması
module_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(module_dir)
sys.path.append(project_dir)

# SharePointFilterBot'u import et
from modules.sharepoint_filter_bot import SharePointFilterBot

# Sayfa yapılandırması
st.set_page_config(
    page_title="SharePoint Filtre Botu",
    page_icon="📑",
    layout="wide"
)

# Başlık ve açıklama
st.title("📑 SharePoint Filtre Botu")
st.markdown("""
Bu uygulama, doğal dil sorguları kullanarak SharePoint belgelerinizi aramanızı sağlar.
Sorgunuzu girin ve ilgili belgeleri bulun.
""")

# Yan menü ayarları
with st.sidebar:
    st.header("Filtre Ayarları")
    min_search_score = st.slider(
        "AI Search Minimum Skoru",
        min_value=0.01,
        max_value=0.2,
        value=0.03,
        step=0.01,
        help="AI Search sonuçlarının minimum benzerlik skoru. Daha düşük değerler daha fazla sonuç getirir."
    )
    
    min_similarity_score = st.slider(
        "Benzerlik Minimum Skoru",
        min_value=0.1,
        max_value=0.5,
        value=0.2,
        step=0.05,
        help="Sonuçların minimum benzerlik skoru. Daha düşük değerler daha fazla sonuç getirir."
    )
    
    st.divider()
    st.markdown("© 2023 SharePoint RAG Projesi")

# Bot örneğini oluştur - Asenkron fonksiyonları çalıştırmak için bir yardımcı fonksiyon
@st.cache_resource
def create_bot(min_similarity: float, min_search: float) -> SharePointFilterBot:
    return SharePointFilterBot(min_similarity_score=min_similarity, min_search_score=min_search)

# Asenkron sorgu işlemini yürütmek için bir yardımcı fonksiyon
def run_async_query(query: str, bot: SharePointFilterBot) -> List[Dict[str, Any]]:
    async_result = asyncio.run(bot.process_query(query))
    return async_result

# Kullanıcı sorgusu için giriş kutusu
query = st.text_input("🔍 Arama Sorgusu", placeholder="Ne arıyorsunuz? (örn: liderlik özellikleri nelerdir)")

# Arama butonu
search_button = st.button("🔎 Ara", type="primary")

# Bot örneğini oluştur
bot = create_bot(min_similarity_score, min_search_score)

# Sonuçları göstermek için bir alan
if "search_results" not in st.session_state:
    st.session_state.search_results = None

# Arama yapıldıysa
if search_button and query:
    with st.spinner("Arama yapılıyor..."):
        try:
            # Aramayı yap ve sonuçları sakla
            results = run_async_query(query, bot)
            st.session_state.search_results = results
        except Exception as e:
            st.error(f"Arama sırasında bir hata oluştu: {str(e)}")

# Sonuçları göster
if st.session_state.search_results is not None:
    results = st.session_state.search_results
    
    if not results:
        st.warning("Arama kriterlerinize uyan sonuç bulunamadı.")
    else:
        st.success(f"{len(results)} dosya bulundu.")
        
        # Sonuçları skora göre sırala
        sorted_results = sorted(
            results, 
            key=lambda x: float(x.get("score", 0)) if isinstance(x.get("score"), (int, float, str)) else 0, 
            reverse=True
        )
        
        # Sonuçları göster
        for i, result in enumerate(sorted_results, 1):
            with st.expander(f"{i}. {result.get('name', 'Bilinmeyen Dosya')} (Benzerlik: {result.get('score', 0):.2f})"):
                cols = st.columns(3)
                
                with cols[0]:
                    st.write("**Dosya Tipi:**")
                    st.write(result.get("file_type", "Bilinmiyor"))
                
                with cols[1]:
                    st.write("**Boyut:**")
                    size = result.get("size", 0)
                    if size > 1024*1024:
                        st.write(f"{size/(1024*1024):.2f} MB")
                    elif size > 1024:
                        st.write(f"{size/1024:.2f} KB")
                    else:
                        st.write(f"{size} bayt")
                
                with cols[2]:
                    if result.get("web_url"):
                        st.write("**Dosya Bağlantısı:**")
                        st.markdown(f"[Dosyayı Aç]({result.get('web_url')})")
                
                # Önizleme veya içerik varsa göster
                if "content_preview" in result and result["content_preview"]:
                    st.write("**İçerik Önizleme:**")
                    st.text(result["content_preview"])

# Uygulama hakkında bilgi
st.divider()
st.markdown("""
### Nasıl Kullanılır
1. Aramak istediğiniz sorguyu giriş kutusuna yazın
2. "Ara" butonuna tıklayın
3. Bulunan belgeleri görmek için sonuçları inceleyin
4. Her belgenin detaylarını görmek için belge başlığına tıklayın
5. Arama hassasiyetini değiştirmek için soldaki kaydırıcıları kullanın
""")

if __name__ == "__main__":
    # Streamlit doğrudan bu dosyayı çalıştırdığında herhangi bir şey yapmaya gerek yok
    # Streamlit zaten bu dosyayı çalıştırıyor olacak
    pass 