"""
SharePoint-RAG Agent Configuration
"""
import os
import sys
from dotenv import load_dotenv

# .env dosyasını yeniden yükle
load_dotenv(override=True)

# Proje dizinleri
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
FILE_LIST_PATH = os.path.join(DATA_DIR, "files.json")

# SharePoint Site ID
SITE_ID = os.getenv("SITE_ID", "")

# Tenant, Client ID ve Secret
TENANT_ID = os.getenv("TENANT_ID", "")
CLIENT_ID = os.getenv("CLIENT_ID", "")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")

# Azure Blob Storage
BLOB_CONNECTION_STRING = os.getenv("BLOB_CONNECTION_STRING", "")
BLOB_CONTAINER_NAME = os.getenv("BLOB_CONTAINER_NAME", "")

# Azure OpenAI
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2023-05-15")

# GPT-4o Model
AZURE_GPT4O_ENDPOINT = os.getenv("AZURE_GPT4O_ENDPOINT", "")
AZURE_GPT4O_API_KEY = os.getenv("AZURE_GPT4O_API_KEY", "")
AZURE_GPT4O_DEPLOYMENT = os.getenv("AZURE_GPT4O_DEPLOYMENT", "")
AZURE_GPT4O_API_VERSION = os.getenv("AZURE_GPT4O_API_VERSION", "2023-05-15")

# Azure Search
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT", "")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY", "")
AZURE_SEARCH_INDEX_NAME = os.getenv("AZURE_SEARCH_INDEX_NAME", "index-sharepoint")
AZURE_SEARCH_API_VERSION = os.getenv("AZURE_SEARCH_API_VERSION", "2024-07-01")
