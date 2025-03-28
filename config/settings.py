"""
SharePoint-RAG Agent Configuration
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Azure and SharePoint credentials
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
SITE_ID = os.getenv("SITE_ID")

# Azure OpenAI credentials - from environment variables
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")

BLOB_CONNECTION_STRING = os.getenv("BLOB_CONNECTION_STRING", "")
BLOB_CONTAINER_NAME = os.getenv("BLOB_CONTAINER_NAME", "sharepoint-files")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
FILE_LIST_PATH = os.path.join(DATA_DIR, "files.json")
EMBEDDINGS_PATH = os.path.join(DATA_DIR, "embeddings.pkl")

os.makedirs(DATA_DIR, exist_ok=True)
