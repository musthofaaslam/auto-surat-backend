import ipaddress
import os
import re
import tempfile
from urllib.parse import urlparse

import cloudinary.uploader
from django.template.loader import render_to_string
from weasyprint import HTML

try:
    from weasyprint import default_url_fetcher
except ImportError:
    try:
        from weasyprint.urls import default_url_fetcher
    except ImportError:
        from weasyprint.urls import URLFetcher
        default_url_fetcher = URLFetcher()


def _sanitize_html_for_pdf(raw_html: str) -> str:
    """
    Membersihkan konten HTML surat dari tag dan atribut berbahaya (XSS / SSRF via WeasyPrint)
    namun tetap mempertahankan tag pemformatan surat resmi (<p>, <table>, <tr>, <td>, <b>, <u>, <i>, <br>, dll).
    """
    if not raw_html or not isinstance(raw_html, str):
        return ""

    cleaned = re.sub(
        r"<\s*(script|iframe|object|embed|applet|form|input|button|link|meta|base|style)\b[^>]*>.*?<\s*/\s*\1\s*>",
        "",
        raw_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(
        r"<\s*(script|iframe|object|embed|applet|form|input|button|link|meta|base)\b[^>]*/?\s*>",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\s+on[a-z]+\s*=\s*(['\"].*?['\"]|[^\s>]+)",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(
        r"(href|src)\s*=\s*['\"]\s*(javascript:|file:|vbscript:)[^'\"]*['\"]",
        r'\1="#"',
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned


def _safe_weasyprint_url_fetcher(url: str, *args, **kwargs):
    """
    URL fetcher aman untuk WeasyPrint guna mencegah Server-Side Request Forgery (SSRF)
    dan pembacaan file lokal server (`file://`).
    Mengizinkan `data:image/...` (untuk QR Code TTE Base64) dan HTTPS publik yang aman.
    """
    if url.startswith("data:image/"):
        return default_url_fetcher(url, *args, **kwargs)

    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"Skema URL '{scheme}' diblokir demi keamanan pada perender PDF.")

    hostname = (parsed.hostname or "").lower()
    if not hostname or hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or hostname.endswith(".local") or hostname.endswith(".internal"):
        raise ValueError(f"Host internal '{hostname}' diblokir pada perender PDF.")

    try:
        ip_obj = ipaddress.ip_address(hostname)
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved:
            raise ValueError(f"Alamat IP privat/internal '{hostname}' diblokir pada perender PDF.")
    except ValueError as exc:
        if "diblokir" in str(exc):
            raise

    return default_url_fetcher(url, *args, **kwargs)


def render_and_upload_pdf(template_path, context_data):
    """
    1. Sanitasi konten HTML dinamis dan render template HTML dengan context data.
    2. Cetak menjadi file PDF via WeasyPrint dengan URL fetcher aman (anti-SSRF).
    3. Upload file PDF ke Cloudinary secara mandiri dan kembalikan URL amannya (secure_url).
    4. Selalu hapus file PDF sementara di disk lokal pada blok finally.
    """
    if not template_path:
        template_path = "kerangka-surat/base_surat.html"

    safe_context = dict(context_data or {})
    for content_key in ("final_content", "final_approved_content", "isi_surat"):
        if content_key in safe_context and isinstance(safe_context[content_key], str):
            safe_context[content_key] = _sanitize_html_for_pdf(safe_context[content_key])

    # Render string HTML menggunakan template engine Django dengan mekanisme fallback aman
    try:
        html_string = render_to_string(template_path, safe_context)
    except Exception:
        fallback_path = "kerangka-surat/base_surat.html"
        html_string = render_to_string(fallback_path, safe_context)

    pdf_temp_path = None
    try:
        # Cetak PDF ke file temporary sistem
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as output_pdf:
            pdf_temp_path = output_pdf.name

        HTML(string=html_string, url_fetcher=_safe_weasyprint_url_fetcher).write_pdf(pdf_temp_path)

        # Bersihkan nomor surat dari garis miring
        nomor_surat_clean = str(safe_context.get("nomor_surat", "unknown")).replace("/", "_")

        # Unggah ke Cloudinary
        upload_result = cloudinary.uploader.upload(
            pdf_temp_path,
            resource_type="image",
            type="upload",
            access_mode="public",
            folder="autosurat_output",
            public_id=f"surat_{nomor_surat_clean}",
            overwrite=True,
        )
        secure_url = upload_result.get("secure_url")

        # Mengubah URL agar langsung mendownload file saat diklik
        if secure_url and "/upload/" in secure_url:
            secure_url = secure_url.replace("/upload/", "/upload/fl_attachment/")

    except Exception as e:
        raise RuntimeError(f"Gagal mengunggah PDF ke Cloudinary: {str(e)}")
    finally:
        if pdf_temp_path and os.path.exists(pdf_temp_path):
            try:
                os.remove(pdf_temp_path)
            except OSError:
                pass

    return secure_url.strip() if secure_url else None
