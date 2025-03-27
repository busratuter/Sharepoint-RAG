import requests
import os
from dotenv import load_dotenv

load_dotenv()

tenant_id = os.getenv("TENANT_ID")
client_id = os.getenv("CLIENT_ID")
client_secret = os.getenv("CLIENT_SECRET")

site_id = os.getenv("SITE_ID")

# Access Token almak için
def get_access_token():
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    token_data = {
        'client_id': client_id,
        'scope': "https://graph.microsoft.com/.default",
        'client_secret': client_secret,
        'grant_type': 'client_credentials'
    }
    response = requests.post(token_url, data=token_data)
    if response.status_code == 200:
        token = response.json().get('access_token')
        print("Access token başarıyla alındı.")
        return token
    else:
        print("Token alınamadı:", response.text)
        exit()

# Drive ID almak için
def get_drive_id(headers):
    url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        drive_id = response.json().get("id")
        print("✅ Drive ID:", drive_id)
        return drive_id
    else:
        print("Drive ID alınamadı:", response.text)
        exit()

def list_files(headers):
    url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root/children"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        files = response.json().get("value", [])
        print("📂 SharePoint klasöründeki dosyalar:")
        for file in files:
            print("📄", file["name"])
    else:
        print("Dosyalar listelenemedi:", response.text)

def download_file(headers, file_name):
    url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root:/{file_name}:/content"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        with open(file_name, "wb") as f:
            f.write(response.content)
        print(f"✅ '{file_name}' dosyası başarıyla indirildi.")
    else:
        print("Dosya indirilemedi:", response.text)

if __name__ == "__main__":
    if not all([tenant_id, client_id, client_secret, site_id]):
        print(".env dosyasında eksik bilgiler var. Lütfen kontrol ediniz.")
        exit()
        
    access_token = get_access_token()
    headers = {'Authorization': f'Bearer {access_token}'}

    get_drive_id(headers)  # opsiyonel: ID'yi almak istiyorsan
    list_files(headers)

    secilen_dosya = input("\nİndirmek istediğin dosya adını yaz (örn: test.docx): ")
    download_file(headers, secilen_dosya)
