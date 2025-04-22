import os
import sys
import json
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import Tool, ToolParam, ToolParamSchema
from azure.identity import DefaultAzureCredential
from typing import Any, List, Dict, Optional
from pathlib import Path
from pydantic import BaseModel, Field
from similarity_agent import create_similarity_agent

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
    
class FilteredResults(BaseModel):
    """Filtrelenmiş sonuçlar için ana model"""
    filtered_files: List[FileResult] = Field(..., description="Eşik değeri üzerindeki dosya sonuçları")
    threshold: float = Field(..., description="Kullanılan eşik değeri")
    query: str = Field(..., description="Aranan sorgu")
    total_results: int = Field(..., description="Toplam sonuç sayısı")

# İkinci agent için filtreleme aracını tanımlayalım
filter_results_tool = Tool(
    name="filter_similarity_results",
    description="Similarity search sonuçlarını filtreleyerek belli bir eşik değerinin üstündekileri döndürür",
    parameters=[
        ToolParam(
            name="similarity_results",
            description="İlk ajanın döndürdüğü benzerlik arama sonuçları",
            schema=ToolParamSchema(
                type="array",
                description="Dosya sonuçları listesi",
                items={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "web_url": {"type": "string"},
                        "similarity": {"type": "number"},
                        "file_type": {"type": "string"},
                        "created_date": {"type": "string"}
                    }
                }
            ),
            required=True
        ),
        ToolParam(
            name="threshold",
            description="Filtreleme için eşik değeri",
            schema=ToolParamSchema(
                type="number",
                description="Bu değerin üzerindeki benzerlik skoruna sahip dosyalar döndürülür",
                default=0.5
            ),
            required=False
        ),
        ToolParam(
            name="query",
            description="Orijinal arama sorgusu",
            schema=ToolParamSchema(
                type="string",
                description="Kullanıcının orijinal arama sorgusu"
            ),
            required=True
        )
    ],
    code="""
    def filter_similarity_results(similarity_results, threshold=0.5, query=""):
        filtered_results = [result for result in similarity_results if result.get("similarity", 0) > threshold]
        
        return {
            "filtered_files": filtered_results,
            "threshold": threshold,
            "query": query,
            "total_results": len(filtered_results)
        }
    """
)

# Agent'ı oluşturalım
def create_filter_agent():
    project_client = AIProjectClient.from_connection_string(
        credential=DefaultAzureCredential(), conn_str=os.environ["PROJECT_CONNECTION_STRING"]
    )

    with project_client:
        # Agent'ı oluştur
        agent = project_client.agents.create_agent(
            model="gpt-4o",
            name="filter-results-agent",
            instructions="""
            Sen bir sonuç filtreleme asistanısın. İlk asistandan gelen benzerlik arama sonuçlarını
            belirli bir eşik değerine göre filtreleyen ve structured output formatında sunan bir ajansın.
            Kullanıcı Türkçe konuşabilir, sen de Türkçe cevap vermelisin.
            
            Her zaman structured output formatını kullanmalısın ve döndürdüğün sonuçları okunaklı bir şekilde
            kullanıcıya sunmalısın. Structured output içinde şu bilgiler olmalıdır:
            
            - filtered_files: Eşik değeri üzerindeki dosya sonuçları
            - threshold: Kullanılan eşik değeri
            - query: Aranan sorgu
            - total_results: Toplam sonuç sayısı
            
            Filtreleme işlemi için bir sonuçtaki benzerlik skorunun belirtilen eşik değerinden yüksek olması gerekir.
            Eşik değeri belirtilmezse, varsayılan olarak 0.5 kullanılır.
            """,
            tools=[filter_results_tool],
        )
        print(f"Created filter agent, agent ID: {agent.id}")
        return agent

# İki ajanı entegre eden bir fonksiyon
def search_and_filter(query, threshold=0.5, top_k=5):
    """
    SharePoint'te arama yapan ve sonuçları filtreleyen fonksiyon
    """
    # İlk olarak similarity agent'ı oluştur
    similarity_agent = create_similarity_agent()
    
    # Sonra filter agent'ı oluştur
    filter_agent = create_filter_agent()
    
    project_client = AIProjectClient.from_connection_string(
        credential=DefaultAzureCredential(), conn_str=os.environ["PROJECT_CONNECTION_STRING"]
    )
    
    with project_client:
        # İlk ajan için thread oluştur
        similarity_thread = project_client.agents.create_thread()
        print(f"Created similarity thread, ID: {similarity_thread.id}")
        
        # İlk ajan için mesaj oluştur ve çalıştır
        similarity_message = project_client.agents.create_message(
            thread_id=similarity_thread.id,
            role="user",
            content=f"Şu konuda dökümanlar arıyorum: {query}. En alakalı {top_k} dökümanı bul."
        )
        
        similarity_run = project_client.agents.create_and_process_run(
            thread_id=similarity_thread.id, 
            agent_id=similarity_agent.id
        )
        
        if similarity_run.status == "failed":
            print(f"Similarity search failed: {similarity_run.last_error}")
            return None
        
        # İlk ajanın cevabını al
        similarity_messages = project_client.agents.list_messages(thread_id=similarity_thread.id)
        similarity_response = similarity_messages.get_last_text_message_by_role("assistant")
        
        if not similarity_response:
            print("No response from similarity agent")
            return None
            
        print(f"Similarity agent response: {similarity_response.text.value}")
        
        # Şimdi ikinci ajan için thread oluştur
        filter_thread = project_client.agents.create_thread()
        print(f"Created filter thread, ID: {filter_thread.id}")
        
        # İkinci ajan için mesaj oluştur ve çalıştır
        filter_message = project_client.agents.create_message(
            thread_id=filter_thread.id,
            role="user",
            content=f"""
            Aşağıdaki benzerlik arama sonuçlarını {threshold} eşik değerine göre filtrele ve 
            sonuçları structured output formatında döndür:
            
            SORGU: {query}
            
            ARAMA SONUÇLARI:
            {similarity_response.text.value}
            """
        )
        
        filter_run = project_client.agents.create_and_process_run(
            thread_id=filter_thread.id, 
            agent_id=filter_agent.id
        )
        
        if filter_run.status == "failed":
            print(f"Filter run failed: {filter_run.last_error}")
            return None
        
        # İkinci ajanın cevabını al
        filter_messages = project_client.agents.list_messages(thread_id=filter_thread.id)
        filter_response = filter_messages.get_last_text_message_by_role("assistant")
        
        if not filter_response:
            print("No response from filter agent")
            return None
            
        return filter_response.text.value

# Eğer script doğrudan çalıştırılırsa
if __name__ == "__main__":
    test_query = "insan kaynakları politikaları"
    results = search_and_filter(test_query, threshold=0.4, top_k=5)
    
    if results:
        print("\nFiltrelenmiş sonuçlar:")
        print(results) 