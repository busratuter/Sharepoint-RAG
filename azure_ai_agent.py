"""
SharePoint dosyaları için benzerlik arama ajanı
Bu ajan, Azure AI Projects SDK kullanarak SharePoint dosyalarında benzerlik araması yapar
"""
import os
import sys
import json
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    FunctionToolDefinition, 
    FunctionDefinition,
    OpenAIPageableListOfThreadMessage,
    ThreadMessage
)
from azure.identity import DefaultAzureCredential
from typing import Any, List, Dict
from pathlib import Path

# Modüllerimizi import ediyoruz
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from modules.vector_search import sync_vector_search, format_search_results
from modules.get_file_list_from_sharepoint import get_access_token, get_file_list, save_file_list_to_json

# AI Projects SDK için connection string
CONNECTION_STRING = "eastus2.api.azureml.ms;7f32a24d-4de5-4811-bd27-d57dfe21f8e4;rg-busra-works;sharepoint-project"

# Bu bilgi doğru değilse, settings'ten veya çevre değişkenlerinden alarak güncellenmelidir
os.environ["PROJECT_CONNECTION_STRING"] = CONNECTION_STRING

# Benzerlik arama aracını tanımlayalım
vector_search_tool = FunctionToolDefinition(
    function=FunctionDefinition(
        name="vector_search",
        description="SharePoint dosyalarında vektör tabanlı benzerlik araması yapar",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Arama için kullanılacak sorgu metni"
                },
                "top_k": {
                    "type": "integer",
                    "description": "Döndürülecek benzer dosya sayısı",
                    "default": 5
                },
                "filter_condition": {
                    "type": "string",
                    "description": "Filtreleme için kullanılacak koşul (örn: \"file_type eq 'pdf'\")"
                }
            },
            "required": ["query"]
        },
        code="""
        def vector_search(query, top_k=5, filter_condition=None):
            from modules.vector_search import sync_vector_search
            results = sync_vector_search(query, top_k=top_k, filter_condition=filter_condition)
            return results
        """
    )
)

# Dosya listesini güncelleme aracı
update_file_list_tool = FunctionToolDefinition(
    function=FunctionDefinition(
        name="update_file_list",
        description="SharePoint'ten dosya listesini günceller",
        parameters={
            "type": "object",
            "properties": {}
        },
        code="""
        def update_file_list():
            from modules.get_file_list_from_sharepoint import get_access_token, get_file_list, save_file_list_to_json
            token = get_access_token()
            files = get_file_list(token)
            save_file_list_to_json(files)
            return {"updated_files": len(files)}
        """
    )
)

# SharePoint benzerlik arama ajanını oluşturalım
def create_similarity_agent():
    """Yeni bir Azure AI Projects benzerlik arama ajanı oluşturur"""
    project_client = AIProjectClient.from_connection_string(
        credential=DefaultAzureCredential(), conn_str=os.environ["PROJECT_CONNECTION_STRING"]
    )

    with project_client:
        # Agent'ı oluştur
        agent = project_client.agents.create_agent(
            model="gpt-4o",  # veya "gpt-35-turbo" gibi başka bir model
            name="sharepoint-similarity-agent",
            instructions="""
            Sen bir dosya arama asistanısın. Kullanıcının sorguladığı metne göre SharePoint üzerinde en benzer
            dosyaları bulabilirsin. Kullanıcının sorularını dikkatli bir şekilde analiz et ve en iyi sonuçları
            döndürmek için vector_search aracını kullan.
            
            Kullanıcı Türkçe konuşacaktır, sen de Türkçe cevap vermelisin.
            
            Sonuçları aşağıdaki formatta döndür:
            
            ## Arama Sonuçları
            
            1. [Dosya Adı](URL) - Benzerlik: %XX
               - Son Güncelleme: [tarih]
               - İçerik: [ilk 200 karakter...]
            
            2. [Dosya Adı](URL) - Benzerlik: %XX
               - Son Güncelleme: [tarih]
               - İçerik: [ilk 200 karakter...]
            
            Önce update_file_list aracını kullanarak dosya listesini güncellemelisin, daha sonra vector_search aracını kullanarak arama yapmalısın.
            """,
            tools=[vector_search_tool, update_file_list_tool],
        )
        print(f"Created similarity agent, agent ID: {agent.id}")
        return agent

# Ajanla etkileşim kurmak için yardımcı fonksiyon
def ask_agent(agent_id, thread_id, query):
    """Ajanla etkileşim kurarak bir sorgu gönderir ve yanıtı alır"""
    project_client = AIProjectClient.from_connection_string(
        credential=DefaultAzureCredential(), conn_str=os.environ["PROJECT_CONNECTION_STRING"]
    )
    
    with project_client:
        # Mesaj oluştur
        message = project_client.agents.create_message(
            thread_id=thread_id,
            role="user",
            content=query
        )
        print(f"Created message, message ID: {message.id}")
        
        # Ajanı çalıştır
        run = project_client.agents.create_and_process_run(thread_id=thread_id, agent_id=agent_id)
        print(f"Run finished with status: {run.status}")
        
        if run.status == "failed":
            print(f"Run failed: {run.last_error}")
            return None
        
        # Thread'den mesajları al
        messages = project_client.agents.list_messages(thread_id=thread_id)
        
        # Son mesajı döndür
        last_msg = None
        for msg in messages.data:
            if isinstance(msg, ThreadMessage) and msg.role == "assistant":
                last_msg = msg
                break
        
        if last_msg and hasattr(last_msg, 'content') and last_msg.content:
            for content in last_msg.content:
                if hasattr(content, 'text') and content.text:
                    return content.text.value
        return None

# Script doğrudan çalıştırıldığında
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='SharePoint Benzerlik Arama Ajanı')
    parser.add_argument('--create', action='store_true', help='Yeni bir ajan oluştur')
    parser.add_argument('--agent-id', type=str, help='Mevcut bir ajanın ID\'si')
    parser.add_argument('--thread-id', type=str, help='Mevcut bir thread ID')
    parser.add_argument('--query', type=str, help='Arama sorgusu')
    args = parser.parse_args()
    
    if args.create:
        # Yeni ajan oluştur
        agent = create_similarity_agent()
        print(f"Yeni ajan oluşturuldu! Agent ID: {agent.id}")
        
        # Yeni thread oluştur
        with AIProjectClient.from_connection_string(
            credential=DefaultAzureCredential(), conn_str=os.environ["PROJECT_CONNECTION_STRING"]
        ) as client:
            thread = client.agents.create_thread()
            print(f"Yeni thread oluşturuldu! Thread ID: {thread.id}")
            print("\nBu ID'leri kaydederek daha sonra kullanabilirsiniz:")
            print(f"Agent ID: {agent.id}")
            print(f"Thread ID: {thread.id}")
            
            if args.query:
                response = ask_agent(agent.id, thread.id, args.query)
                print("\nAjanın yanıtı:")
                print(response)
    
    elif args.agent_id and args.thread_id and args.query:
        # Mevcut ajan ve thread ile sorgu yap
        response = ask_agent(args.agent_id, args.thread_id, args.query)
        print("\nAjanın yanıtı:")
        print(response)
    
    elif args.query:
        print("Hata: Ajan ve thread ID'leri gerekli. Önce --create ile yeni bir ajan oluşturun veya --agent-id ve --thread-id parametrelerini kullanın.")
    
    else:
        print("Kullanım: python azure_ai_agent.py --create [--query 'sorgu']")
        print("     veya: python azure_ai_agent.py --agent-id <ID> --thread-id <ID> --query 'sorgu'")
        print("\nÖrnek:")
        print("     python azure_ai_agent.py --create")
        print("     python azure_ai_agent.py --agent-id abc123 --thread-id xyz789 --query 'finans raporları'") 