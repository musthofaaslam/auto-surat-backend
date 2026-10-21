# accounts/authentication.py
from rest_framework_simplejwt.authentication import JWTAuthentication
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from .models import User

# SARAN PERBAIKAN ARSITEKTURAL:
# Pastikan modul `accounts.authentication` dimuat saat inisialisasi aplikasi
# (misalnya melalui `AccountsConfig.ready()` pada `accounts/apps.py`) agar
# `CustomJWTAuthenticationScheme` selalu terdaftar di registry drf-spectacular
# sebelum perintah `python manage.py spectacular --validate` dieksekusi.


class CustomJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        try:
            user_id = validated_token.get('user_id')
            if not user_id:
                return None

            user = User.objects.get(pk=user_id)

            # Tambahkan atribut dinamis agar DRF mengenalinya sebagai user yang terautentikasi
            user.is_authenticated = True
            return user
        except User.DoesNotExist:
            return None


class CustomJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "accounts.authentication.CustomJWTAuthentication"
    name = "jwtAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
