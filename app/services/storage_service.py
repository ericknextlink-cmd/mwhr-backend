import uuid
from supabase import create_client, Client
from fastapi import UploadFile, HTTPException
from app.core.config import settings

class StorageService:
    def __init__(self):
        if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
            print("Warning: Supabase credentials not set.")
            self.client = None
        else:
            self.client: Client = create_client(
                settings.SUPABASE_URL, 
                settings.SUPABASE_SERVICE_ROLE_KEY
            )
        self.bucket_name = settings.SUPABASE_BUCKET_NAME

    async def upload_file(self, file: UploadFile, application_id: int) -> str:
        """
        Uploads a file to Supabase Storage under the application folder.
        Returns the storage path (key).
        Path: applications/{application_id}/documents/{filename}
        """
        if not self.client:
            raise HTTPException(status_code=500, detail="Storage service not configured.")

        file_ext = file.filename.split(".")[-1]
        unique_id = str(uuid.uuid4())
        clean_filename = f"{unique_id}.{file_ext}"

        file_path = f"applications/{application_id}/documents/{clean_filename}"

        file_content = await file.read()
        try:
            self.client.storage.from_(self.bucket_name).upload(
                file_path,
                file_content,
                {"content-type": file.content_type or "application/octet-stream"}
            )
            await file.seek(0)
            return file_path
        except Exception as e:
            print(f"Storage Upload Error: {e}")
            raise HTTPException(status_code=500, detail="Failed to upload file to storage.")

    def upload_certificate(self, pdf_bytes: bytes, application_id: int, filename: str) -> str:
        """
        Uploads a generated certificate PDF to Supabase Storage.
        Path: applications/{application_id}/certifications/{filename}
        Returns the storage path (key).
        """
        if not self.client:
            return ""
        file_path = f"applications/{application_id}/certifications/{filename}"
        try:
            self.client.storage.from_(self.bucket_name).upload(
                file_path,
                pdf_bytes,
                {"content-type": "application/pdf"}
            )
            return file_path
        except Exception as e:
            print(f"Storage Certificate Upload Error: {e}")
            return ""

    def upload_invoice(self, pdf_bytes: bytes, application_id: int, filename: str) -> str:
        """
        Uploads generated invoice PDF (2-page letter + invoice) to Supabase Storage.
        Path: applications/{application_id}/invoices/{filename}
        Returns the storage path (key).
        """
        if not self.client:
            return ""
        file_path = f"applications/{application_id}/invoices/{filename}"
        try:
            self.client.storage.from_(self.bucket_name).upload(
                file_path,
                pdf_bytes,
                {"content-type": "application/pdf"}
            )
            return file_path
        except Exception as e:
            print(f"Storage Invoice Upload Error: {e}")
            return ""

    def get_signed_url(self, file_path: str, expiry_seconds: int = 3600) -> str:
        """
        Generates a temporary signed URL for a file.
        """
        if not self.client:
            return ""
        try:
            return self.client.storage.from_(self.bucket_name).create_signed_url(
                file_path, expiry_seconds
            )["signedURL"]
        except Exception as e:
            print(f"Storage URL Error: {e}")
            return ""

    def get_public_url(self, file_path: str) -> str:
        """
        Get public URL (if bucket is public).
        """
        if not self.client:
            return ""
        return self.client.storage.from_(self.bucket_name).get_public_url(file_path)

    def delete_file(self, file_path: str):
        if not self.client:
            return
        try:
            self.client.storage.from_(self.bucket_name).remove([file_path])
        except Exception as e:
            print(f"Storage Delete Error: {e}")

    def download_file(self, file_path: str) -> bytes | None:
        """
        Downloads a file from Supabase Storage.
        Returns the file content as bytes.
        """
        if not self.client:
            return None
        try:
            res = self.client.storage.from_(self.bucket_name).download(file_path)
            return res
        except Exception as e:
            print(f"Storage Download Error for {file_path}: {e}")
            return None

storage_service = StorageService()
