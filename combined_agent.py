import os
import sys
import json
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import Tool, ToolParam, ToolParamSchema
from azure.identity import DefaultAzureCredential
from typing import Any, List, Dict, Optional
from pathlib import Path
from pydantic import BaseModel, Field

# Modüllerimizi import ediyoruz
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from modules.semantic_search import find_most_similar_files

# Connection string olarak kullanacağımız değeri çevre değişkeni olarak ayarlayalım
os.environ["PROJECT_CONNECTION_STRING"] = "eastus2.api.azureml.ms;7f32a24d-4de5-4811-bd27-d57dfe21f8e4;rg-busra-works;sharepoint-project"

# Structured Output için Pydantic modeli
class FileResult(BaseModel):
    """Eşik değeri üstündeki dosya sonuçları için model"""
    name: str = Field(..., description="Dosyanın adı")
    web_url: str = Field(..., description="Dosyanın SharePoint URL'si")
    similarity: float = Field(..., description="Benzerlik skoru (0-1 arası)")
    file_type: Optional[str] = Field(None, description="Dosya tipi (örn. docx, pdf, xlsx)")
    created_date: Optional[str] = Field(None, description="Oluşturulma tarihi")
    
class SearchResults(BaseModel):
    """Arama sonuçları için ana model"""
    filtered_files: List[FileResult] = Field(..., description="Eşik değeri üzerindeki dosya sonuçları")
    threshold: float = Field(..., description="Kullanılan eşik değeri")
    query: str = Field(..., description="Aranan sorgu")
    total_results: int = Field(..., description="Toplam sonuç sayısı")
    recommendation: Optional[str] = Field(None, description="Daha iyi arama yapmak için öneri")

# Similarity search aracını tanımlayalım
similarity_search_tool = Tool(
    name="similarity_search",
    description="Sharepoint üzerindeki dosyalarda benzerlik araması yapar",
    parameters=[
        ToolParam(
            name="query",
            description="Kullanıcının arama yapmak istediği metin sorgusu",
            schema=ToolParamSchema(
                type="string",
                description="Arama için kullanılacak sorgu metni"
            ),
            required=True
        ),
        ToolParam(
            name="top_k",
            description="En fazla kaç sonuç döndürüleceği",
            schema=ToolParamSchema(
                type="integer",
                description="Döndürülecek benzer dosya sayısı",
                default=5
            ),
            required=False
        ),
        ToolParam(
            name="threshold",
            description="Benzerlik eşik değeri (0-1 arası)",
            schema=ToolParamSchema(
                type="number",
                description="Minimum benzerlik skoru, bu değerin altındaki sonuçlar filtrelenir",
                default=0.3
            ),
            required=False
        )
    ],
    code="""
    def similarity_search(query, top_k=5, threshold=0.3):
        from modules.semantic_search import find_most_similar_files
        similar_files = find_most_similar_files(query, top_k=top_k, threshold=threshold)
        
        # Eşik değeri üzerindeki sonuçları filtrele
        filtered_results = [result for result in similar_files if result.get("similarity", 0) > threshold]
        
        return {
            "filtered_files": filtered_results,
            "threshold": threshold,
            "query": query,
            "total_results": len(filtered_results),
            "recommendation": None if len(filtered_results) > 0 else "Arama sorgunuzu daha detaylı yapın veya eşik değerini düşürmeyi deneyin."
        }
    """
)

# Gelişmiş tek bir agent oluşturalım
def create_combined_agent():
    project_client = AIProjectClient.from_connection_string(
        credential=DefaultAzureCredential(), conn_str=os.environ["PROJECT_CONNECTION_STRING"]
    )

    with project_client:
        # Agent'ı oluştur
        agent = project_client.agents.create_agent(
            model="gpt-4o",
            name="sharepoint-search-agent",
            instructions="""
            Sen bir SharePoint dosya arama asistanısın. Kullanıcının sorguladığı metne göre
            SharePoint üzerinde en benzer dosyaları bulup, eşik değerine göre filtreler ve
            structured output formatında sonuçları döndürürsün.
            
            Kullanıcı Türkçe konuşabilir, sen de Türkçe cevap vermelisin.
            
            İşlevlerin:
            1. Kullanıcının sorgusunu analiz et ve uygun arama terimlerini belirle
            2. Benzerlik araması yap
            3. Sonuçları filtrele ve sırala
            4. Structured output formatında sonuçları döndür
            
            Yapmaman gerekenler:
            1. Kullanıcıya gereksiz teknik detayları anlatma
            2. Sonuçları dönüştürmek ya da değiştirmek için harici araçlar önerme
            
            Her zaman structured output formatı şu şekilde olmalıdır:
            {
                "filtered_files": [
                    {
                        "name": "dosya adı",
                        "web_url": "dosya linki",
                        "similarity": 0.xx,
                        "file_type": "dosya tipi",
                        "created_date": "oluşturulma tarihi"
                    },
                    ...
                ],
                "threshold": 0.x,
                "query": "arama sorgusu",
                "total_results": n,
                "recommendation": "eğer varsa öneri"
            }
            
            Eşik değeri belirtilmezse, varsayılan olarak 0.3 kullanılır.
            Maksimum sonuç sayısı belirtilmezse, varsayılan olarak 5 kullanılır.
            """,
            tools=[similarity_search_tool],
        )
        print(f"Created combined agent, agent ID: {agent.id}")
        return agent

# Tek bir agent kullanarak birleştirilmiş arama fonksiyonu
def search_with_combined_agent(query, threshold=0.3, top_k=5):
    """
    SharePoint'te arama yapan birleştirilmiş agent fonksiyonu
    """
    # Combined agent'ı oluştur
    combined_agent = create_combined_agent()
    
    project_client = AIProjectClient.from_connection_string(
        credential=DefaultAzureCredential(), conn_str=os.environ["PROJECT_CONNECTION_STRING"]
    )
    
    with project_client:
        # Thread oluştur
        thread = project_client.agents.create_thread()
        print(f"Created thread, ID: {thread.id}")
        
        # Mesaj oluştur ve çalıştır
        message = project_client.agents.create_message(
            thread_id=thread.id,
            role="user",
            content=f"""
            Şu konuda SharePoint üzerindeki dosyaları arayıp, eşik değeri {threshold} ve 
            maksimum sonuç sayısı {top_k} olacak şekilde sonuçları structured output 
            formatında döndür: {query}
            """
        )
        
        run = project_client.agents.create_and_process_run(
            thread_id=thread.id, 
            agent_id=combined_agent.id
        )
        
        if run.status == "failed":
            print(f"Search failed: {run.last_error}")
            return None
        
        # Ajanın cevabını al
        messages = project_client.agents.list_messages(thread_id=thread.id)
        response = messages.get_last_text_message_by_role("assistant")
        
        if not response:
            print("No response from agent")
            return None
            
        return response.text.value

# İnteraktif kullanım için CLI fonksiyonu
def interactive_search():
    """
    Kullanıcıdan girdi alan ve SharePoint aramasını yapan CLI fonksiyonu
    """
    print("=" * 50)
    print("SharePoint-RAG Combined Agent")
    print("=" * 50)
    
    while True:
        # Kullanıcıdan sorgu al
        query = input("\n🔍 Arama sorgusu (çıkmak için 'q' girin): ")
        
        if query.lower() == 'q':
            print("\nUygulama kapatılıyor...")
            break
        
        # Eşik değeri ve maksimum sonuç sayısını al
        try:
            threshold = float(input("Eşik değeri (0-1 arası, varsayılan 0.3): ") or 0.3)
            top_k = int(input("Maksimum sonuç sayısı (varsayılan 5): ") or 5)
        except ValueError:
            print("Geçersiz değer girdiniz. Varsayılan değerler kullanılacak.")
            threshold = 0.3
            top_k = 5
        
        print("\n🔄 Arama yapılıyor...")
        results = search_with_combined_agent(query, threshold=threshold, top_k=top_k)
        
        if results:
            print("\n✅ İşlem tamamlandı!")
            print(results)
        else:
            print("\n❌ Aramanız sırasında bir hata oluştu veya sonuç bulunamadı.")

# Eğer script doğrudan çalıştırılırsa
if __name__ == "__main__":
    interactive_search() 