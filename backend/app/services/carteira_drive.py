import os
from typing import Optional, Dict, Any
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload
from io import BytesIO


class CarteiraDriveService:
    """Service para integração com Google Drive"""

    SCOPES = ['https://www.googleapis.com/auth/drive']

    @staticmethod
    def _get_service():
        """Retorna cliente autenticado do Google Drive"""
        creds_json = os.getenv("GOOGLE_DRIVE_CREDENTIALS_JSON")
        if not creds_json:
            raise ValueError("GOOGLE_DRIVE_CREDENTIALS_JSON não configurado")

        try:
            import json
            creds_dict = json.loads(creds_json)
            credentials = Credentials.from_service_account_info(
                creds_dict,
                scopes=CarteiraDriveService.SCOPES
            )
            return build('drive', 'v3', credentials=credentials)
        except Exception as e:
            raise ValueError(f"Erro ao autenticar Google Drive: {str(e)}")

    @staticmethod
    def criar_pasta_cliente(cliente_nome: str, pasta_pai_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Cria pasta no Drive para o cliente.
        Se pasta_pai_id não informado, cria na raiz.
        """
        service = CarteiraDriveService._get_service()

        nome_pasta = f"Carteira - {cliente_nome}"
        file_metadata = {
            'name': nome_pasta,
            'mimeType': 'application/vnd.google-apps.folder'
        }

        if pasta_pai_id:
            file_metadata['parents'] = [pasta_pai_id]

        try:
            folder = service.files().create(body=file_metadata, fields='id, webViewLink').execute()
            return {
                "folder_id": folder.get('id'),
                "folder_link": folder.get('webViewLink'),
                "nome_pasta": nome_pasta,
                "status": "criada",
            }
        except Exception as e:
            raise ValueError(f"Erro ao criar pasta: {str(e)}")

    @staticmethod
    def fazer_upload_documento(
        arquivo_bytes: bytes,
        nome_arquivo: str,
        pasta_id: str,
        mime_type: str = "application/pdf",
    ) -> Dict[str, Any]:
        """
        Faz upload de documento para pasta no Drive.
        """
        service = CarteiraDriveService._get_service()

        file_metadata = {
            'name': nome_arquivo,
            'parents': [pasta_id]
        }

        media = MediaIoBaseUpload(BytesIO(arquivo_bytes), mimetype=mime_type)

        try:
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink, mimeType, createdTime'
            ).execute()

            return {
                "file_id": file.get('id'),
                "file_link": file.get('webViewLink'),
                "nome_arquivo": nome_arquivo,
                "data_upload": file.get('createdTime'),
                "status": "enviado",
            }
        except Exception as e:
            raise ValueError(f"Erro ao fazer upload: {str(e)}")

    @staticmethod
    def listar_arquivos_pasta(pasta_id: str) -> list:
        """Lista todos os arquivos de uma pasta"""
        service = CarteiraDriveService._get_service()

        try:
            query = f"'{pasta_id}' in parents and trashed=false"
            results = service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name, mimeType, createdTime, webViewLink)',
                pageSize=100
            ).execute()

            return results.get('files', [])
        except Exception as e:
            raise ValueError(f"Erro ao listar arquivos: {str(e)}")

    @staticmethod
    def compartilhar_com_email(file_id: str, email: str, role: str = "reader") -> Dict[str, Any]:
        """
        Compartilha arquivo com email específico.
        role: reader, commenter, writer
        """
        service = CarteiraDriveService._get_service()

        permission = {
            'type': 'user',
            'role': role,
            'emailAddress': email
        }

        try:
            service.permissions().create(fileId=file_id, body=permission).execute()
            return {
                "compartilhado": True,
                "email": email,
                "role": role,
                "file_id": file_id
            }
        except Exception as e:
            raise ValueError(f"Erro ao compartilhar: {str(e)}")

    @staticmethod
    def deletar_arquivo(file_id: str) -> Dict[str, Any]:
        """Deleta arquivo do Drive"""
        service = CarteiraDriveService._get_service()

        try:
            service.files().delete(fileId=file_id).execute()
            return {
                "deletado": True,
                "file_id": file_id
            }
        except Exception as e:
            raise ValueError(f"Erro ao deletar: {str(e)}")
