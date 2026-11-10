import hashlib
import uuid
from ..models import TteSignature

def create_tte_signature(surat_request, signer=None):
    """
    Membuat sidik jari kriptografis SHA-256 yang mengikat isi naskah surat,
    nomor surat resmi, identitas mahasiswa, serta penandatangan, beserta token QR Code TTE.
    """
    student = surat_request.student
    
    # Ambil isi naskah surat final yang disetujui untuk diikat ke dalam hash SHA-256
    letter_content = (
        getattr(surat_request, "final_approved_content", None)
        or getattr(surat_request, "ai_original_draft", None)
        or ""
    ).strip()
    content_digest = hashlib.sha256(letter_content.encode("utf-8")).hexdigest()
    signer_id = getattr(signer, "id", "AUTO") if signer else "AUTO"
    nomor_resmi = getattr(surat_request, "nomor_surat_resmi", "") or ""

    # Token unik untuk verifikasi publik via QR Code
    token = str(uuid.uuid4())

    # Merangkai string integritas dokumen untuk di-hash
    raw_string = (
        f"{student.nim}|{surat_request.kode_surat.kode_surat}|{nomor_resmi}|"
        f"{signer_id}|{content_digest}|{token}"
    )
    document_hash = hashlib.sha256(raw_string.encode("utf-8")).hexdigest()

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
