import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from surat.models import SuratType

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Sinkronisasi kontrak required_payload_fields pada tabel SuratType "
        "dari berkas single source of truth required_field_surat.json"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulasi proses sinkronisasi tanpa menyimpan perubahan ke basis data.",
        )
        parser.add_argument(
            "--file",
            type=str,
            default=None,
            help="Path alternatif ke berkas required_field_surat.json.",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        custom_file = options.get("file")

        if custom_file:
            json_path = Path(custom_file)
        else:
            default_path = getattr(
                settings,
                "REQUIRED_FIELD_SURAT_PATH",
                Path(settings.BASE_DIR) / "required_field_surat.json",
            )
            json_path = Path(default_path)

        if not json_path.exists():
            raise CommandError(
                f"Berkas Single Source of Truth tidak ditemukan di: {json_path}"
            )

        self.stdout.write(
            f"[INFO] Membaca kontrak data dari Single Source of Truth: {json_path}"
        )

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                contracts: Dict[str, Any] = json.load(f)
        except Exception as exc:
            raise CommandError(
                f"Gagal mem-parsing berkas JSON {json_path}: {exc}"
            ) from exc

        if not isinstance(contracts, dict):
            raise CommandError(
                f"Format berkas JSON tidak valid: diharapkan dictionary tingkat atas, "
                f"tetapi menerima {type(contracts).__name__}."
            )

        updated_count = 0
        missing_in_db: List[str] = []
        unchanged_count = 0

        prefix = "[DRY-RUN] " if dry_run else ""

        for kode_surat, fields_list in contracts.items():
            clean_kode = str(kode_surat).strip().upper()
            if clean_kode == "DEFAULT":
                continue

            if not isinstance(fields_list, list):
                self.stderr.write(
                    f"[PERINGATAN] Nilai untuk kode_surat '{clean_kode}' bukan berupa array. Dilewati."
                )
                continue

            surat_type = SuratType.objects.filter(kode_surat=clean_kode).first()
            if surat_type is None:
                missing_in_db.append(clean_kode)
                self.stdout.write(
                    f"{prefix}[LEWATI] SuratType dengan kode '{clean_kode}' belum terdaftar di basis data."
                )
                continue

            current_fields = getattr(surat_type, "required_payload_fields", None)
            if current_fields == fields_list:
                unchanged_count += 1
                self.stdout.write(
                    f"{prefix}[OK] SuratType '{clean_kode}' sudah sinkron ({len(fields_list)} field)."
                )
                continue

            if not dry_run:
                surat_type.required_payload_fields = fields_list
                surat_type.save(update_fields=["required_payload_fields"])

            updated_count += 1
            field_names = [item.get("field", "") for item in fields_list if isinstance(item, dict)]
            self.stdout.write(
                f"{prefix}[PERBARUI] SuratType '{clean_kode}' diperbarui dengan {len(fields_list)} field: "
                f"{', '.join(field_names)}"
            )

        self.stdout.write("-" * 60)
        self.stdout.write(
            f"{prefix}Hasil Sinkronisasi Kontrak Surat:\n"
            f"  - Diperbarui : {updated_count}\n"
            f"  - Sudah Sesuai: {unchanged_count}\n"
            f"  - Belum di DB : {len(missing_in_db)} ({', '.join(missing_in_db) if missing_in_db else '-'})\n"
            f"  - Status Akhir: Selesai."
        )
