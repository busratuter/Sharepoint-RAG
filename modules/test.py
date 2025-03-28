from modules.get_file_list_from_sharepoint import get_access_token
from modules.semantic_search import find_most_similar_files
from modules.upload_to_blob import upload_sharepoint_file_to_blob_stream
from config.settings import SITE_ID

prompt = input("Prompt gir: ")
top_files = find_most_similar_files(prompt, top_k=2, threshold=0.5)

if top_files:
    token = get_access_token()
    for file in top_files:
        upload_sharepoint_file_to_blob_stream(token, SITE_ID, file)
else:
    print("Eşleşen dosya bulunamadı.")
