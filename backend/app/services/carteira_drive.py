from typing import Any, Dict, Optional

from app.services import google_drive

# Documentos da Carteira ficam dentro da MESMA pasta do cliente usada por
# Processos/Contratos/Procurações (resolvida por nome via sessão OAuth
# compartilhada), numa subpasta dedicada.
SUBFOLDER = "Carteira"


class CarteiraDriveService:
    """Integração da Carteira com o Google Drive.

    Reaproveita a sessão OAuth mestre já usada pelos demais menus
    (Clientes, Processos, Contratos, Procurações) em vez de um service
    account separado — não requer nenhuma pasta raiz ou credencial própria.
    """

    @staticmethod
    def criar_pasta_cliente(cliente_nome: str, pasta_pai_id: Optional[str] = None) -> Dict[str, Any]:
        link = google_drive.link_subpasta(cliente_nome, SUBFOLDER)
        if not link:
            raise ValueError("Google Drive não autenticado (sessão OAuth ausente ou expirada)")
        folder_id = google_drive.resolver_pasta_id(cliente_nome, SUBFOLDER)
        return {
            "folder_id": folder_id,
            "folder_link": link,
            "nome_pasta": f"{cliente_nome} / {SUBFOLDER}",
            "status": "criada",
        }

    @staticmethod
    def fazer_upload_documento(
        arquivo_bytes: bytes,
        nome_arquivo: str,
        cliente_nome: str,
        mime_type: str = "application/pdf",
    ) -> Dict[str, Any]:
        link = google_drive.upload_arquivo(
            arquivo_bytes, nome_arquivo, cliente_nome, SUBFOLDER, mime_type,
        )
        if not link:
            raise ValueError("Falha ao enviar ao Drive (sessão OAuth ausente ou expirada)")
        return {
            "file_id": None,
            "file_link": link,
            "nome_arquivo": nome_arquivo,
            "status": "enviado",
        }

    @staticmethod
    def listar_arquivos_pasta(cliente_nome: str) -> list:
        return google_drive.listar_arquivos(cliente_nome, SUBFOLDER)

    @staticmethod
    def buscar_pastas_similares(cliente_nome: str) -> list:
        return google_drive.buscar_pastas_cliente_similares(cliente_nome)

    @staticmethod
    def vincular_pasta_existente(cliente_nome: str, folder_id_cliente: str) -> Dict[str, Any]:
        """Registra `folder_id_cliente` como a pasta-raiz deste cliente (reuso
        confirmado pelo usuário, em vez de criar uma pasta nova) e retorna a
        subpasta "Carteira" dentro dela — mesmo formato de criar_pasta_cliente."""
        ok = google_drive.vincular_pasta_existente(cliente_nome, folder_id_cliente)
        if not ok:
            raise ValueError("Falha ao vincular pasta existente")
        return CarteiraDriveService.criar_pasta_cliente(cliente_nome)

    @staticmethod
    def compartilhar_com_email(cliente_nome: str, email: str, role: str = "reader") -> Dict[str, Any]:
        ok = google_drive.compartilhar_subpasta(cliente_nome, SUBFOLDER, email, role)
        if not ok:
            raise ValueError("Erro ao compartilhar pasta no Drive")
        return {"compartilhado": True, "email": email, "role": role}
