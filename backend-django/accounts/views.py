# accounts/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from rest_framework_simplejwt.exceptions import TokenError
from drf_spectacular.utils import extend_schema

from .models import User, Student, Lecturer
from .serializers import (
    LoginSerializer,
    StandardErrorResponseSerializer,
    LoginResponseSuccessSerializer,
    GetMeResponseSerializer,
    LogoutRequestSerializer,
    LogoutSuccessSerializer)

class LoginAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    @extend_schema(
        request=LoginSerializer,
        responses={
            200: LoginResponseSuccessSerializer,
            400: StandardErrorResponseSerializer, # Pakai yang global!
            401: StandardErrorResponseSerializer, # Pakai yang global!
        }
    )
    
    def post(self, request):
        print("--- DEBUG ISI REQUEST ---")
        print("BODY MENTAH (data):", request.body)
        print("PARSED DATA (request.data):", request.data)
        print("CONTENT-TYPE:", request.META.get('CONTENT_TYPE'))
        print("---------------------------")
        # ----------------------------------------
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "status": "error",
                "message": "Validasi gagal",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        nip_nim = serializer.validated_data['nip_nim']
        password = serializer.validated_data['password']

        # Validasi user via custom authentication backend
        user_obj = authenticate(username=nip_nim, password=password)

        if user_obj is None:
            return Response({
                "status": "error",
                "message": "Otentikasi gagal",
                "errors": {
                    "non_field_errors": ["Username atau password salah."]
                }
            }, status=status.HTTP_401_UNAUTHORIZED)

        # Generate token secara manual dengan menyimpan ID user di dalam payload (claims)
        refresh = RefreshToken()
        refresh['user_id'] = user_obj.id
        refresh['role'] = user_obj.role
        refresh['nip_nim'] = user_obj.nip_nim

        return Response({
            "message": "Login berhasil",
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": {
                "id": user_obj.id,
                "nama": user_obj.nama,
                "nip_nim": user_obj.nip_nim,
                "role": user_obj.role
            }
        }, status=status.HTTP_200_OK)

class GetMeAPIView(APIView):
    """
    Endpoint Get Me menggunakan autentikasi standar JWT Bearer Token.
    """
    permission_classes = [permissions.IsAuthenticated]
    @extend_schema(
            request=GetMeResponseSerializer,
            responses={
                200: GetMeResponseSerializer,
                400: StandardErrorResponseSerializer, # Pakai yang global!
                401: StandardErrorResponseSerializer, # Pakai yang global!
            }
        )
    def get(self, request):
        # request.user otomatis diisi oleh SimpleJWT dari token yang dibawa di Header
        user_obj = request.user 

        profile_data = {}
        if user_obj.role == 'STUDENT':
            try:
                student = Student.objects.get(user=user_obj)
                profile_data = {
                    "nim": student.nim,
                    "prodi": student.prodi.nama_prodi,
                    "fakultas": student.fakultas.nama_fakultas
                }
            except Student.DoesNotExist:
                pass
        elif user_obj.role == 'LECTURER':
            try:
                lecturer = Lecturer.objects.get(user=user_obj)
                profile_data = {
                    "user_id": lecturer.user.id,
                    "fakultas": lecturer.fakultas.nama_fakultas if lecturer.fakultas else None
                }
            except Lecturer.DoesNotExist:
                pass

        return Response({
            "id": user_obj.id,
            "nama": user_obj.nama,
            "nip_nim": user_obj.nip_nim,
            "role": user_obj.role,
            "profile": profile_data
        }, status=status.HTTP_200_OK)
        

class LogoutAPIView(APIView):
    """
    Endpoint Logout untuk membatalkan/blacklist Refresh Token.
    POST /api/auth/logout/
    Body: { "refresh": "<refresh_token_anda>" }
    """
    permission_classes = [permissions.IsAuthenticated]
    @extend_schema(
            request=LogoutRequestSerializer,
            responses={
                200: LogoutSuccessSerializer,
                400: StandardErrorResponseSerializer, # Pakai yang global!
                401: StandardErrorResponseSerializer, # Pakai yang global!
            }
        )

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if not refresh_token:
                return Response({
                    "status": "error",
                    "message": "Otentikasi token gagal",
                    "errors": {
                        "refresh": ["Refresh token wajib disertakan."]
                    }
                }, status=status.HTTP_400_BAD_REQUEST)

            # Masukkan token ke dalam blacklist
            token = RefreshToken(refresh_token)
            token.blacklist()

            return Response({
                "status": "success",
                "message": "Logout berhasil. Sesi telah diakhiri."
            }, status=status.HTTP_200_OK)
        except TokenError:
           return Response({
                "status": "error",
                "message": "Otentikasi token gagal",
                "errors": {
                    "refresh": ["Token tidak valid atau sudah kedaluwarsa."]
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                "status": "error",
                "message": "Terjadi kesalahan.",
                "errors": {
                    "refresh": [str(e)]
                }
            }, status=status.HTTP_400_BAD_REQUEST)