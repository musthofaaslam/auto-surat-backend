import secrets
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.hashers import check_password, make_password
from .models import User

class CustomUserAuthBackend(BaseBackend):
    """
    Custom Backend agar Django dan SimpleJWT bisa mengenali model User biasa (bukan AbstractUser).
    Mendukung verifikasi hash password standar Django serta auto-upgrade hash untuk data seed lama.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        # 'username' di sini akan menerima nilai dari field 'nip_nim' yang dikirim saat login
        raw_identifier = username or kwargs.get('nip_nim')
        if not raw_identifier or not password:
            return None

        identifier = str(raw_identifier).strip()
        clean_password = str(password).strip()

        # Gunakan pencocokan case-insensitive dan trim agar mahasiswa/dosen yang mengetik inf24001 tetap valid
        user = User.objects.filter(nip_nim__iexact=identifier).first()
        if not user:
            return None

        stored_password = user.password or ""
        if stored_password.startswith(('pbkdf2_', 'argon2$', 'bcrypt$', 'scrypt$')):
            is_valid = check_password(password, stored_password) or check_password(clean_password, stored_password)
        else:
            # Kompatibilitas mundur dengan perbandingan waktu konstan (constant-time) untuk seed lama,
            # diikuti migrasi otomatis ke hash PBKDF2 agar tidak tersimpan sebagai plaintext.
            is_valid = (
                secrets.compare_digest(stored_password.encode('utf-8'), str(password).encode('utf-8')) or
                secrets.compare_digest(stored_password.encode('utf-8'), clean_password.encode('utf-8'))
            )
            if is_valid:
                user.password = make_password(clean_password)
                try:
                    user.save(update_fields=['password'])
                except Exception:
                    pass

        if is_valid:
            return user
        return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
