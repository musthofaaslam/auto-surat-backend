# apps/surat/urls.py
from django.urls import path
from .views import (
    SuratRequestRedraftAPIView,
    SuratTypeListAPIView,
    SuratRequestCreateAPIView,
    SuratRequestListAPIView,
    SuratRequestDetailAPIView,
    LecturerApprovalActionAPIView,
    SuratVerifyAPIView,
    SuratRequestRedraftAPIView,
    ChatSessionMessageAPIView
)

urlpatterns = [
    path('types/', SuratTypeListAPIView.as_view(), name='surat-type-list'),
    path('request/', SuratRequestCreateAPIView.as_view(), name='surat-request-create'),
    path('requests/', SuratRequestListAPIView.as_view(), name='surat-request-list'),
    path('requests/<int:pk>/', SuratRequestDetailAPIView.as_view(), name='surat-request-detail'),
    path('approval/<int:approval_id>/action/', LecturerApprovalActionAPIView.as_view(), name='surat-approval-action'),
    path('verify/<str:token>/', SuratVerifyAPIView.as_view(), name='surat-verify'),
    path('requests/<int:pk>/re-draft/', SuratRequestRedraftAPIView.as_view(), name='surat-request-redraft'),
    path('chat/<str:thread_id>/', ChatSessionMessageAPIView.as_view(), name='chat-session')
]