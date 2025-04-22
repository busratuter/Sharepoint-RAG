"""
SharePoint dosyaları için benzerlik arama ajanı
Bu ajan, Azure AI Projects SDK ve CodeInterpreterTool kullanarak SharePoint dosyalarında benzerlik araması yapar
"""
import os
import sys
import json
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import CodeInterpreterTool
from azure.identity import DefaultAzureCredential
from typing import Any, List, Dict
from pathlib import Path

# Modüllerimizi import ediyoruz
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config.settings import DATA_DIR, FILE_LIST_PATH

# AI Projects SDK için connection string (Azure AI Foundry projenizden alınmalı)
CONNECTION_STRING = "eastus2.api.azureml.ms;7f32a24d-4de5-4811-bd27-d57dfe21f8e4;rg-busra-works;sharepoint-project"

# Python kodunda vektör arama yapacak bir fonksiyon oluşturacağız
# Bu kod, CodeInterpreter tarafından çalıştırılacak
VECTOR_SEARCH_CODE = '''
import os
import sys
import json
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def load_file_list(file_path="/mnt/data/files.json"):
    """SharePoint'ten alınmış dosya listesini yükler"""
    try:
        print(f"Dosya listesi yükleme deneniyor: {file_path}")
        if not os.path.exists(file_path):
            print(f"Dosya bulunamadı: {file_path}")
            # Alternatif dosya yollarını dene
            alt_paths = [
                "./files.json",
                "/mnt/files.json",
                "./data/files.json"
            ]
            for alt_path in alt_paths:
                print(f"Alternatif dosya yolu deneniyor: {alt_path}")
                if os.path.exists(alt_path):
                    print(f"Dosya bulundu: {alt_path}")
                    file_path = alt_path
                    break
            else:
                print("Hiçbir dosya bulunamadı!")
                return []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            file_list = json.load(f)
            print(f"Yüklenen dosya sayısı: {len(file_list)}")
            for file in file_list[:5]:  # İlk 5 dosyayı göster
                print(f"- {file.get('name')}")
            return file_list
    except Exception as e:
        print(f"Dosya yükleme hatası: {str(e)}")
        return []

def calculate_similarity(file_names, query, threshold=0.1):
    """Dosya isimleri ve sorgu arasındaki benzerliği hesaplar"""
    if not file_names:
        return []
    
    print(f"Benzerlik hesaplanıyor. Dosya sayısı: {len(file_names)}, Sorgu: '{query}', Eşik: {threshold}")
    
    # Tüm metinleri birleştir
    all_texts = file_names + [query]
    
    # TF-IDF vektörleştirici
    vectorizer = TfidfVectorizer(analyzer='word', lowercase=True)
    tfidf_matrix = vectorizer.fit_transform(all_texts)
    
    # Cosine similarity hesapla
    cosine_sim = cosine_similarity(tfidf_matrix[-1:], tfidf_matrix[:-1]).flatten()
    
    # Benzerlik sonuçlarını oluştur
    results = []
    for idx, score in enumerate(cosine_sim):
        print(f"Dosya: {file_names[idx]}, Benzerlik: {score:.4f}")
        if score >= threshold:
            results.append({
                "file_name": file_names[idx],
                "similarity_score": float(score)
            })
    
    # Benzerlik puanına göre azalan sıralama
    results.sort(key=lambda x: x['similarity_score'], reverse=True)
    return results

def search_files(query, threshold=0.1, top_k=None):
    """SharePoint dosyaları içinde benzerlik araması yapar"""
    # Dosya listesini yükle
    files = load_file_list()
    
    # Dosya listesi boşsa uyarı mesajı döndür
    if not files:
        return f"⚠️ Dosya listesi bulunamadı veya boş. Lütfen aşağıdaki adımları takip edin:\\n\\n" + \
               f"1. Önce 'python azure_code_interpreter_agent.py --update-files' komutunu çalıştırın\\n" + \
               f"2. Ardından 'python azure_code_interpreter_agent.py --create' ile yeni bir ajan oluşturun\\n" + \
               f"3. Son olarak 'python azure_code_interpreter_agent.py --agent-id <ID> --thread-id <ID> --query \"{query}\"' komutunu çalıştırın"
    
    # Sadece dosya isimlerini al
    file_names = [file.get("name", "") for file in files if file.get("name")]
    print(f"Benzerlik araması için {len(file_names)} dosya adı kullanılıyor:")
    for name in file_names:
        print(f"- {name}")
    
    # Benzerlik hesapla
    similarity_results = calculate_similarity(file_names, query, threshold)
    
    # Sonuçları top_k ile sınırlandır
    if top_k and isinstance(top_k, int) and top_k > 0:
        similarity_results = similarity_results[:top_k]
    
    # Sonuçlara ek bilgiler ekle
    enriched_results = []
    for result in similarity_results:
        file_name = result["file_name"]
        # Dosyanın tam bilgilerini bul
        file_info = next((f for f in files if f.get("name") == file_name), None)
        if file_info:
            enriched_results.append({
                "file_name": file_name,
                "similarity_score": result["similarity_score"],
                "web_url": file_info.get("web_url", ""),
                "created_date": file_info.get("created_date", ""),
                "last_modified": file_info.get("last_modified", "")
            })
        else:
            # Dosya bilgisi bulunamazsa sadece isim ve benzerlik puanını ekle
            enriched_results.append({
                "file_name": file_name,
                "similarity_score": result["similarity_score"]
            })
    
    # Sonuçları güzel bir formatta göster
    if not enriched_results:
        return f"\\'{query}\\' sorgusu için sonuç bulunamadı (Eşik değeri: {threshold})"
    
    results_text = f"## \\'{query}\\' sorgusu için {len(enriched_results)} sonuç bulundu (Eşik değeri: {threshold})\\n\\n"
    
    for idx, result in enumerate(enriched_results, 1):
        score_percent = round(result["similarity_score"] * 100, 2)
        results_text += f"{idx}. {result['file_name']} (Benzerlik: %{score_percent})\\n"
        if "web_url" in result:
            results_text += f"   URL: {result.get('web_url', 'Belirtilmemiş')}\\n"
        if "last_modified" in result:
            results_text += f"   Son Değişiklik: {result.get('last_modified', 'Belirtilmemiş')}\\n"
        results_text += "\\n"
    
    return results_text

# Sorguyu çalıştır
query = "{query}"
threshold = {threshold}
top_k = {top_k}

results = search_files(query, threshold, top_k)
print(results)
'''

def create_similarity_agent():
    """Yeni bir Azure AI Projects CodeInterpreter kullanarak benzerlik arama ajanı oluşturur"""
    project_client = AIProjectClient.from_connection_string(
        credential=DefaultAzureCredential(), conn_str=CONNECTION_STRING
    )

    with project_client:
        # CodeInterpreter tool oluştur
        code_interpreter = CodeInterpreterTool()
        
        # Dosya listesini CodeInterpreter'a yükle
        if os.path.exists(FILE_LIST_PATH):
            try:
                with open(FILE_LIST_PATH, 'rb') as file_content:
                    # Güncel SDK için doğru parametre formatı
                    file_response = project_client.agents.upload_file(
                        file=file_content,
                        purpose="fine-tune"
                    )
                    print(f"Dosya yüklendi: {file_response.id}")
                    
                    # Yüklenen dosyaları listele
                    files = project_client.agents.list_files()
                    print(f"Mevcut dosyalar: {[f.id for f in files]}")
            except Exception as e:
                print(f"Dosya yüklenirken hata: {str(e)}")
                print("Uyarı: Dosya yüklenemedi. Dosya listesi bulunamazsa ajan düzgün çalışmayabilir.")
        else:
            print(f"Uyarı: Dosya listesi bulunamadı: {FILE_LIST_PATH}")
            print("Öncelikle --update-files parametresiyle dosya listesini güncelleyin.")
        
        # Agent'ı oluştur
        agent = project_client.agents.create_agent(
            model="gpt-4o",  # veya "gpt-35-turbo" gibi başka bir model
            name="sharepoint-similarity-agent",
            instructions="""
            Sen bir dosya arama asistanısın. Kullanıcının sorguladığı metne göre SharePoint üzerinde en benzer
            dosyaları bulabilirsin. Kullanıcının sorularını dikkatli bir şekilde analiz et ve Python kodu
            çalıştırarak benzerlik araması yap.
            
            Kullanıcı Türkçe konuşacaktır, sen de Türkçe cevap vermelisin.
            
            Her arama istediğinde, aşağıdaki adımları takip et:
            1. Python kodu çalıştırarak benzerlik araması yap
            2. Benzerlik eşik değeri olarak 0.1 kullan (varsayılan 0.3 değil)
            3. TF-IDF ve kosinüs benzerliği kullanarak karşılaştırma yap
            4. Sonuçları düzgün bir şekilde biçimlendir
            
            Sonuçları aşağıdaki formatta döndür:
            
            ## Arama Sonuçları
            
            1. [Dosya Adı](URL) - Benzerlik: %XX
               - Son Güncelleme: [tarih]
            
            2. [Dosya Adı](URL) - Benzerlik: %XX
               - Son Güncelleme: [tarih]
            
            Kullanıcı sana bir sorgu gönderdiğinde, onun için benzerlik araması yapacağın bir kod çalıştır.
            Eğer sonuç bulunamazsa, kullanıcıya başka bir sorgu denemesini öner.
            """,
            tools=code_interpreter.definitions,
            tool_resources=code_interpreter.resources,
        )
        print(f"Created similarity agent, agent ID: {agent.id}")
        return agent

def ask_agent(agent_id, thread_id, query, threshold=0.1, top_k=5):
    """Ajanla etkileşim kurarak bir sorgu gönderir ve yanıtı alır"""
    project_client = AIProjectClient.from_connection_string(
        credential=DefaultAzureCredential(), conn_str=CONNECTION_STRING
    )
    
    with project_client:
        # Kullanıcı sorgusunu doğrudan kullan - kod formatını ajan kendisi oluşturacak
        prompt = f"""
        "{query}" sorgusu için SharePoint dosyalarında benzerlik araması yapmak istiyorum.
        Aşağıdaki eşik değerini kullan: {threshold}
        En çok {top_k} sonuç göster.
        
        # ÖNEMLİ NOTLAR:
        - Eşik değeri {threshold} olarak ayarlanmıştır. Bu değerin altındaki sonuçları gösterme.
        - TF-IDF vektörleri ve kosinüs benzerliğini kullanarak sonuçları hesapla.
        - SharePoint dosya listesini files.json dosyasından yükle.
        
        Sonuçları hesaplarken tüm işlem adımlarını açıkça göster ve dosyaların benzerlik puanlarını göster.
        """
        
        message = project_client.agents.create_message(
            thread_id=thread_id,
            role="user",
            content=prompt
        )
        print(f"Created message, message ID: {message.id}")
        
        # Ajanı çalıştır
        run = project_client.agents.create_and_process_run(
            thread_id=thread_id, 
            agent_id=agent_id
        )
        print(f"Run finished with status: {run.status}")
        
        if run.status == "failed":
            print(f"Run failed: {run.last_error}")
            return None
        
        # Thread'den mesajları al
        messages = project_client.agents.list_messages(thread_id=thread_id)
        
        # Son mesajı döndür
        last_msg = messages.get_last_text_message_by_role("assistant")
        if last_msg:
            return last_msg.text.value
        return None

# Dosya listesini güncelle
def update_file_list():
    """SharePoint'ten dosya listesini günceller"""
    try:
        # Modülleri burada import ediyoruz çünkü script doğrudan çalıştırıldığında gerekli
        from modules.get_file_list_from_sharepoint import get_access_token, get_file_list, save_file_list_to_json
        
        token = get_access_token()
        files = get_file_list(token)
        save_file_list_to_json(files)
        print(f"Dosya listesi güncellendi. {len(files)} dosya bulundu.")
        return True
    except Exception as e:
        print(f"Dosya listesi güncellenirken hata oluştu: {str(e)}")
        return False

# Script doğrudan çalıştırıldığında
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='SharePoint Benzerlik Arama Ajanı (CodeInterpreter)')
    parser.add_argument('--create', action='store_true', help='Yeni bir ajan oluştur')
    parser.add_argument('--update-files', action='store_true', help='SharePoint dosya listesini güncelle')
    parser.add_argument('--agent-id', type=str, help='Mevcut bir ajanın ID\'si')
    parser.add_argument('--thread-id', type=str, help='Mevcut bir thread ID')
    parser.add_argument('--query', type=str, help='Arama sorgusu')
    parser.add_argument('--threshold', type=float, default=0.1, help='Benzerlik eşik değeri (0-1 arası)')
    parser.add_argument('--top-k', type=int, default=5, help='Maksimum sonuç sayısı')
    args = parser.parse_args()
    
    # SharePoint dosya listesini güncelle
    if args.update_files:
        update_file_list()
    
    if args.create:
        # Yeni ajan oluştur
        agent = create_similarity_agent()
        print(f"Yeni ajan oluşturuldu! Agent ID: {agent.id}")
        
        # Yeni thread oluştur
        with AIProjectClient.from_connection_string(
            credential=DefaultAzureCredential(), conn_str=CONNECTION_STRING
        ) as client:
            thread = client.agents.create_thread()
            print(f"Yeni thread oluşturuldu! Thread ID: {thread.id}")
            print("\nBu ID'leri kaydederek daha sonra kullanabilirsiniz:")
            print(f"Agent ID: {agent.id}")
            print(f"Thread ID: {thread.id}")
            
            if args.query:
                response = ask_agent(agent.id, thread.id, args.query, args.threshold, args.top_k)
                print("\nAjanın yanıtı:")
                print(response)
    
    elif args.agent_id and args.thread_id and args.query:
        # Mevcut ajan ve thread ile sorgu yap
        response = ask_agent(args.agent_id, args.thread_id, args.query, args.threshold, args.top_k)
        print("\nAjanın yanıtı:")
        print(response)
    
    elif args.query:
        print("Hata: Ajan ve thread ID'leri gerekli. Önce --create ile yeni bir ajan oluşturun veya --agent-id ve --thread-id parametrelerini kullanın.")
    
    else:
        print("Kullanım: python azure_code_interpreter_agent.py --create [--query 'sorgu']")
        print("     veya: python azure_code_interpreter_agent.py --agent-id <ID> --thread-id <ID> --query 'sorgu'")
        print("     veya: python azure_code_interpreter_agent.py --update-files")
        print("\nÖrnek:")
        print("     python azure_code_interpreter_agent.py --create")
        print("     python azure_code_interpreter_agent.py --agent-id abc123 --thread-id xyz789 --query 'finans raporları'") 