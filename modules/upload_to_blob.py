import requests
from azure.storage.blob import BlobServiceClient
from config.settings import (
    BLOB_CONNECTION_STRING,
    BLOB_CONTAINER_NAME
)

def upload_sharepoint_file_to_blob_stream(access_token: str, site_id: str, file_metadata: dict):
    """
    SharePoint dosyasını bellekte indir ve doğrudan Azure Blob Storage'a yükle.
    Diskte geçici dosya oluşturulmaz.
    """
    file_id = file_metadata["sharepoint_id"]
    file_name = file_metadata["name"]

    headers = {'Authorization': f'Bearer {access_token}'}
    download_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/items/{file_id}/content"
    response = requests.get(download_url, headers=headers, stream=True) # sharepoint dosyası stream olarak aliniyor

    if response.status_code != 200:
        raise Exception(f"SharePoint dosyası alınamadı: {response.text}")

    blob_service_client = BlobServiceClient.from_connection_string(BLOB_CONNECTION_STRING)
    blob_client = blob_service_client.get_blob_client(container=BLOB_CONTAINER_NAME, blob=file_name)

    blob_client.upload_blob(response.raw, overwrite=True) # sharepointteki inen dosyayı blob'a yükle
    print(f"'{file_name}' başarıyla Azure Blob Storage'a yüklendi")
