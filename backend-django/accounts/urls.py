from django.urls import path
from .views import LoginAPIView, GetMeAPIView, LogoutAPIView

urlpatterns = [
    path('login/', LoginAPIView.as_view(), name='api-login'),
    path('logout/', LogoutAPIView.as_view(), name='api-logout'),
    path('me/', GetMeAPIView.as_view(), name='api-get-me'),
]
