import io
import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from app.config_loader import CFG

SCOPES = ["https://www.googleapis.com/auth/drive"]
CLIENT_SECRET_PATH = CFG.get("credentials", {}).get("client_secret_path", "credentials/credentials.json")
TOKEN_PATH         = CFG.get("credentials", {}).get("token_path",          "credentials/token.json")


def get_drive_service():
    """
    Crée le client Google Drive via OAuth.
    Compatible local et Cloud Run.
    """
    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            CLIENT_SECRET_PATH,
            SCOPES,
        )
        creds = flow.run_local_server(port=0)

        Path("credentials").mkdir(exist_ok=True)
        with open(TOKEN_PATH, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())

    return build("drive", "v3", credentials=creds)


def list_files_in_folder(service, folder_id: str) -> list[dict]:
    """
    Liste les fichiers présents dans un dossier Drive.
    """
    query = f"'{folder_id}' in parents and trashed = false"

    response = service.files().list(
        q=query,
        fields="files(id, name, mimeType, createdTime, modifiedTime, md5Checksum)",
        orderBy="createdTime asc",
    ).execute()

    return response.get("files", [])


def find_file_in_folder_by_name(service, folder_id: str, file_name: str) -> dict | None:
    """
    Cherche un fichier exact par nom dans un dossier Drive.
    """
    safe_name = file_name.replace("'", r"\'")
    query = f"'{folder_id}' in parents and trashed = false and name = '{safe_name}'"

    response = service.files().list(
        q=query,
        fields="files(id, name, mimeType)",
        pageSize=1,
    ).execute()

    files = response.get("files", [])
    return files[0] if files else None


def download_file(service, file_id: str, destination_path: str) -> None:
    """
    Télécharge un fichier Drive en local.
    """
    request = service.files().get_media(fileId=file_id)

    with io.FileIO(destination_path, "wb") as file_handle:
        downloader = MediaIoBaseDownload(file_handle, request)
        done = False

        while not done:
            _, done = downloader.next_chunk()


def upload_file(
    service,
    file_path: str,
    file_name: str,
    folder_id: str,
    mime_type: str,
) -> str:
    """
    Upload un nouveau fichier dans un dossier Drive.
    """
    metadata = {
        "name": file_name,
        "parents": [folder_id],
    }

    media = MediaFileUpload(file_path, mimetype=mime_type)

    created = service.files().create(
        body=metadata,
        media_body=media,
        fields="id",
    ).execute()

    return created["id"]


def update_file(service, file_id: str, file_path: str, mime_type: str) -> None:
    """
    Met à jour le contenu d'un fichier existant.
    """
    media = MediaFileUpload(file_path, mimetype=mime_type)

    service.files().update(
        fileId=file_id,
        media_body=media,
    ).execute()


def upload_or_update_file(
    service,
    file_path: str,
    file_name: str,
    folder_id: str,
    mime_type: str,
) -> str:
    """
    Upload si le fichier n'existe pas, sinon update.
    """
    existing = find_file_in_folder_by_name(service, folder_id, file_name)

    if existing:
        update_file(service, existing["id"], file_path, mime_type)
        return existing["id"]

    return upload_file(service, file_path, file_name, folder_id, mime_type)