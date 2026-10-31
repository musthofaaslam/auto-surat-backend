# apps/surat/services/tte_service.py
import hashlib
import uuid
from ..models import TteSignature

def create_tte_signature(surat_request, signer=None):
    """
    Membuat sidik jari SHA-256 dan token verifikasi QR Code untuk TTE.
    """
    student = surat_request.student
    
    # Merangkai string unik untuk di-hash
    raw_string = f"{student.nim}-{surat_request.kode_surat.kode_surat}-{uuid.uuid4()}"
    document_hash = hashlib.sha256(raw_string.encode('utf-8')).hexdigest()

    # Token unik untuk verifikasi publik via QR Code
    token = str(uuid.uuid4())

    # Simpan ke database
    tte_instance = TteSignature.objects.create(
        surat_request=surat_request,
        signer=signer, # Bernilai None jika auto-approval sistem
        hash_document=document_hash,
        token=token
    )

    qr_code_url = f"https://auto-surat-backend.onrender.com/surat/verify/{token}/"

    return {
        "instance": tte_instance,
        "token": token,
        "hash_document": document_hash,
        "qr_code_url": qr_code_url
    }