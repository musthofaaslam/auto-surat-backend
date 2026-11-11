from django.db import models
from django.contrib.postgres.fields import ArrayField


class User(models.Model):
    id = models.CharField(max_length=100, primary_key=True)
    nama = models.CharField(max_length=255)
    password = models.CharField(max_length=255)
    nip_nim = models.CharField(max_length=50, unique=True)
    role = models.CharField(max_length=20)  # STUDENT / LECTURER / ADMIN

    class Meta:
        db_table = 'users'


class Faculty(models.Model):
    id = models.CharField(max_length=50, primary_key=True)
    nama_fakultas = models.CharField(max_length=255)
    dekan = models.ForeignKey('Lecturer', on_delete=models.SET_NULL, null=True, blank=True, related_name='dekan_faculty')
    wadek_1 = models.ForeignKey('Lecturer', on_delete=models.SET_NULL, null=True, blank=True, related_name='wadek1_faculty')
    wadek_3 = models.ForeignKey('Lecturer', on_delete=models.SET_NULL, null=True, blank=True, related_name='wadek3_faculty')

    class Meta:
        db_table = 'faculty'


class Department(models.Model):
    id = models.CharField(max_length=50, primary_key=True)
    fakultas = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name='departments')
    nama_prodi = models.CharField(max_length=255)
    kaprodi = models.ForeignKey('Lecturer', on_delete=models.SET_NULL, null=True, blank=True, related_name='kaprodi_dept')

    class Meta:
        db_table = 'departments'


class Course(models.Model):
    kode_matkul = models.CharField(max_length=50, primary_key=True)
    nama_matkul = models.CharField(max_length=255)
    sks = models.IntegerField(default=4)
    prodi = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='courses')

    class Meta:
        db_table = 'courses'


class Lecturer(models.Model):
    id = models.CharField(max_length=100, primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='lecturer_profile')
    fakultas = models.ForeignKey(Faculty, on_delete=models.CASCADE)
    prodi = models.ForeignKey(Department, on_delete=models.CASCADE)
    
    # ArrayField khusus untuk database PostgreSQL
    jabatan_struktural = ArrayField(models.CharField(max_length=100), default=list, blank=True)

    class Meta:
        db_table = 'lecturers'


class Student(models.Model):
    nim = models.CharField(max_length=50, primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    fakultas = models.ForeignKey(Faculty, on_delete=models.CASCADE)
    prodi = models.ForeignKey(Department, on_delete=models.CASCADE)
    
    semester_aktif = models.IntegerField(default=1)
    tahun_akademik = models.CharField(max_length=20)
    status_akademik = models.CharField(max_length=50, default="AKTIF")
    tahun_masuk = models.IntegerField()
    status_pembayaran_ukt = models.CharField(max_length=50, default="LUNAS")
    
    nama_ortu = models.CharField(max_length=255, null=True, blank=True)
    nip_ortu = models.CharField(max_length=50, null=True, blank=True)
    pekerjaan_ortu = models.CharField(max_length=100, null=True, blank=True)
    status_beasiswa_aktif = models.BooleanField(default=False)
    nama_beasiswa_aktif = models.CharField(max_length=255, null=True, blank=True)
    periode_beasiswa_selesai = models.CharField(max_length=50, null=True, blank=True)
    
    ipk_kumulatif = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    total_sks = models.IntegerField(default=0)
    total_sks_lulus = models.IntegerField(default=0)
    catatan_pelanggaran_etik = models.BooleanField(default=False)
    deskripsi_pelanggaran = models.TextField(null=True, blank=True)
    status_disiplin_kampus = models.BooleanField(default=True)
    
    krs_aktif_json = models.TextField(null=True, blank=True)
    status_krs_skripsi = models.BooleanField(default=False)
    judul_skripsi_acc = models.TextField(null=True, blank=True)
    
    dosen_pembimbing_akademik = models.ForeignKey(Lecturer, on_delete=models.SET_NULL, null=True, blank=True, related_name='pa_students')
    dosen_pembimbing_skripsi = models.ForeignKey(Lecturer, on_delete=models.SET_NULL, null=True, blank=True, related_name='skripsi_students')
    koordinator_magang_prodi = models.ForeignKey(Lecturer, on_delete=models.SET_NULL, null=True, blank=True, related_name='magang_students')

    class Meta:
        db_table = 'student'


class StudentCourse(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='courses_taken')
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    lecturer = models.ForeignKey(Lecturer, on_delete=models.CASCADE)
    semester_taken = models.IntegerField()
    tahun_akademik = models.CharField(max_length=20)
    status_krs = models.CharField(max_length=20, default="AMBIL")
    ip = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = 'student_courses'
