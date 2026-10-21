from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'

    def ready(self):
        # Memastikan OpenApiAuthenticationExtension untuk CustomJWTAuthentication terdaftar
        import accounts.authentication  # noqa: F401
