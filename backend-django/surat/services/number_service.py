from django.db import transaction
from django.utils import timezone
from ..models import SuratNumberCounter

def generate_surat_number(kode_surat, fakultas=None, prodi=None):
    """
    Menghasilkan nomor surat resmi secara sekuensial dan aman dari race condition.
    """
    now = timezone.now()
    year = now.year
    month = now.month

    with transaction.atomic():
        # Mengunci baris counter tabel agar aman dari request bersamaan (race condition)
        counter, created = SuratNumberCounter.objects.select_for_update().get_or_create(
            kode_surat=kode_surat,
            fakultas=fakultas,
            prodi=prodi,
            tahun=year,
            bulan=month,
            defaults={'last_number': 0}
        )

        counter.last_number += 1
        counter.save()

        # Format nomor urut menjadi 3 digit (contoh: 001)
        seq_str = str(counter.last_number).zfill(3)
        
        # Susun format akhir nomor surat kampus
        fakultas_code = fakultas.id if fakultas else "UNIV"
        nomor_resmi = f"{seq_str}/{kode_surat.kode_surat}/{fakultas_code}/{month}/{year}"
        
        return nomor_resmi
