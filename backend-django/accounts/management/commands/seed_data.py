import json
from django.core.management.base import BaseCommand
from surat.models import (
    User, Faculty, Department, Course, Lecturer, Student, StudentCourse
)

class Command(BaseCommand):
    help = 'Seeding dummy data dari JSON ke database'

    def handle(self, *args, **kwargs):
        self.stdout.write("Memuat file JSON...")
        with open('autosurat_dummy_52users.json', 'r') as f:
            data = json.load(f)

        # 1. Seed Users (Tanpa signature_url)
        self.stdout.write("Seeding Users...")
        for u in data['users']:
            User.objects.update_or_create(
                id=u['id'],
                defaults={
                    'nama': u['nama'],
                    'nip_nim': u['nip_nim'],
                    'role': u['role'],
                    'password': u['password']
                }
            )

        # 3. Seed Faculties & Departments
        self.stdout.write("Seeding Faculties & Departments...")
        for fac in data['faculties']:
            Faculty.objects.update_or_create(
                id=fac['id'],
                defaults={'nama_fakultas': fac['nama_fakultas']}
            )

        for dept in data['departments']:
            Department.objects.update_or_create(
                id=dept['id'],
                defaults={
                    'nama_prodi': dept['nama_prodi'],
                    'fakultas_id': dept['fakultas_id']
                }
            )

        # 4. Seed Lecturers
        self.stdout.write("Seeding Lecturers...")
        for lec in data['lecturers']:
            Lecturer.objects.update_or_create(
                id=lec['id'],
                defaults={
                    'user_id': lec['user_id'],
                    'fakultas_id': lec['fakultas_id'],
                    'prodi_id': lec['prodi_id'],
                    'jabatan_struktural': lec['jabatan_struktural']
                }
            )

        # Update Jabatan Pejabat di Faculty & Department
        for fac in data['faculties']:
            Faculty.objects.filter(id=fac['id']).update(
                dekan_id=fac['dekan_id'],
                wadek_1_id=fac['wadek_1_id'],
                wadek_3_id=fac['wadek_3_id']
            )

        for dept in data['departments']:
            Department.objects.filter(id=dept['id']).update(
                kaprodi_id=dept['kaprodi_id']
            )

        # 5. Seed Courses
        self.stdout.write("Seeding Courses...")
        for c in data['courses']:
            Course.objects.update_or_create(
                kode_matkul=c['kode_matkul'],
                defaults={
                    'nama_matkul': c['nama_matkul'],
                    'sks': c['sks'],
                    'prodi_id': c['prodi_id']
                }
            )

        # 6. Seed Students
        self.stdout.write("Seeding Students...")
        for std in data['students']:
            Student.objects.update_or_create(
                nim=std['nim'],
                defaults={
                    'user_id': std['user_id'],
                    'fakultas_id': std['fakultas_id'],
                    'prodi_id': std['prodi_id'],
                    'semester_aktif': std['semester_aktif'],
                    'tahun_akademik': std['tahun_akademik'],
                    'status_akademik': std['status_akademik'],
                    'tahun_masuk': std['tahun_masuk'],
                    'status_pembayaran_ukt': std['status_pembayaran_ukt'],
                    'nama_ortu': std['nama_ortu'],
                    'pekerjaan_ortu': std['pekerjaan_ortu'],
                    'ipk_kumulatif': std['ipk_kumulatif'],
                    'total_sks': std['total_sks'],
                    'total_sks_lulus': std['total_sks_lulus'],
                    'catatan_pelanggaran_etik': std['catatan_pelanggaran_etik'],
                    'status_disiplin_kampus': std['status_disiplin_kampus'],
                    'dosen_pembimbing_akademik_id': std['dosen_pembimbing_akademik_id']
                }
            )

        # 7. Seed Student Courses
        self.stdout.write("Seeding Student Courses...")
        for sc in data['student_courses']:
            StudentCourse.objects.update_or_create(
                id=sc['id'],
                defaults={
                    'student_id': sc['student_id'],
                    'course_id': sc['course_id'],
                    'lecturer_id': sc['lecturer_id'],
                    'semester_taken': sc['semester_taken'],
                    'tahun_akademik': sc['tahun_akademik'],
                    'status_krs': sc['status_krs'],
                    'ip': sc['ip']
                }
            )

        self.stdout.write(self.style.SUCCESS("Berhasil memasukkan seluruh data dummy ke database!"))
