import json
from django.core.management.base import BaseCommand
from surat.models import (
    SuratType
)

class Command(BaseCommand):
    help = 'Seeding dummy data dari JSON ke database'

    def handle(self, *args, **kwargs):
            self.stdout.write("Memuat file JSON...")
            with open('autosurat_dummy_52users.json', 'r') as f:
                data = json.load(f)
            self.stdout.write("Seeding Surat Types...")
            for st in data['surat_types']:
                SuratType.objects.update_or_create(
                    kode_surat=st['kode_surat'],
                    defaults={
                        'nama_surat': st['nama_surat'],
                        'kategori': st['kategori'],
                        'is_auto_approval': st['is_auto_approval'],
                        'template_path': st['template_path']
                    }
                )
