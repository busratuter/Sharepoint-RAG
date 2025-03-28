import requests
import json
import os
from config.settings import TENANT_ID, CLIENT_ID, CLIENT_SECRET, SITE_ID

def get_access_token():
    url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    data = {
        'client_id': CLIENT_ID,
        'scope': "https://graph.microsoft.com/.default",
        'client_secret': CLIENT_SECRET,
        'grant_type': 'client_credentials'
    }
    response = requests.post(url, data=data)
    response.raise_for_status()
    return response.json().get("access_token")

def get_file_list(access_token):
    headers = {'Authorization': f'Bearer {access_token}'}
    url = f"https://graph.microsoft.com/v1.0/sites/{SITE_ID}/drive/root/children"
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    items = response.json().get("value", [])
    
    files = []
    for item in items:
        if "file" in item:  # sadece dosyaları al, klasörleri geç
            file_info = {
                "name": item["name"],
                "size": item.get("size", 0),
                "file_type": item["name"].split(".")[-1],
                "created_date": item.get("createdDateTime"),
                "last_modified": item.get("lastModifiedDateTime"),
                "web_url": item.get("webUrl"),
                "sharepoint_id": item.get("id")
            }
            files.append(file_info)
    return files

#JSON dosyasına yaz
def save_file_list_to_json(file_list, output_path="data/files.json"):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(file_list, f, indent=4)
    print(f"{len(file_list)} dosya listelendi ve '{output_path}' dosyasına kaydedildi.")

if __name__ == "__main__":
    token = get_access_token()
    file_list = get_file_list(token)
    save_file_list_to_json(file_list)
