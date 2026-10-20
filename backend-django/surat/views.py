# apps/surat/views.py
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.generics import ListAPIView, RetrieveAPIView
from accounts.authentication import CustomJWTAuthentication
from rest_framework.parsers import MultiPartParser, FormParser
from drf_spectacular.utils import extend_schema

from .models import SuratType, SuratRequest, SuratApproval, TteSignature
from accounts.models import Student, Lecturer
from accounts.serializers import StandardErrorResponseSerializer 

from .serializers import (
    SuratTypeSerializer,
    SuratRequestCreateSerializer,
    SuratRequestListSerializer,
    SuratRequestDetailSerializer,
    SuratApprovalSerializer,
    SuratApprovalActionSerializer,
    SuratRejectActionSerializer,
    SuratRequestSuccessResponseSerializer
)
from .services.workflow_service import process_surat_request, process_approval_action
from .accounts.serializers import StandardErrorResponseSerializer

class SuratTypeListAPIView(ListAPIView):
    """
    Endpoint untuk melihat daftar jenis surat yang tersedia (untuk dropdown form frontend).
    GET /api/surat/types/
    """
    queryset = SuratType.objects.all()
    serializer_class = SuratTypeSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly] 

class SuratRequestCreateAPIView(APIView):
    """
    Endpoint bagi mahasiswa untuk mengajukan surat baru (Auto atau Manual).
    POST /api/surat/request/
    """
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]  
    parser_classes = [MultiPartParser, FormParser] # <--- Tambahkan parser ini!
    @extend_schema(
        summary="Ajukan Surat Baru (Mahasiswa)",
        description="Digunakan mahasiswa untuk mengajukan permohonan pembuatan surat (otomatis/manual). Mendukung pengiriman file lampiran (multi-part form-data) dan payload dinamis.",
        request=SuratRequestCreateSerializer,
        responses={
            201: SuratRequestSuccessResponseSerializer, # Atau 200 tergantung return code service kamu
            400: StandardErrorResponseSerializer,       # Validasi gagal / field kurang / logika bisnis gagal
            403: StandardErrorResponseSerializer,       # Bukan akun mahasiswa
            404: StandardErrorResponseSerializer        # Kode surat tidak ditemukan
        }
    )
    
    def post(self, request):
        serializer = SuratRequestCreateSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response({
                "status": "error",
                "message": "Validasi gagal",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        # Ambil data tervalidasi
        kode_surat_str = serializer.validated_data['kode_surat']
        payload_data = serializer.validated_data['payload_data']
        attachments = request.FILES.getlist('attachments') # Mengambil file multi-part

        # Pastikan user yang login adalah mahasiswa (Student)
        try:
            student_obj = request.user.student_profile # Mengikuti related_name OneToOne
        except Student.DoesNotExist:
            return Response({
                "status": "error",
                "message": "Validasi gagal",
                "errors": "bukan akun mahasiswa. Hanya mahasiswa yang dapat mengajukan surat."
            }, status=status.HTTP_400_BAD_REQUEST)
        try:
            surat_type = SuratType.objects.get(kode_surat=kode_surat_str)
        except SuratType.DoesNotExist:
            return Response({
                "status": "error",
                "message": "Validasi gagal",
                "errors": "Jenis surat tidak ditemukan."
            }, status=status.HTTP_404_NOT_FOUND)

        # Jalankan service layer workflow
        result, http_code = process_surat_request(
            student=student_obj,
            surat_type=surat_type,
            payload_data=payload_data,
            attachments_files=attachments
        )

        return Response(result, status=http_code)


class SuratRequestListAPIView(ListAPIView):
    """
    Endpoint untuk melihat daftar riwayat pengajuan surat milik mahasiswa yang sedang login.
    GET /api/surat/requests/
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SuratRequestListSerializer

    def get_queryset(self):
        user = self.request.user
        # Jika mahasiswa, tampilkan surat miliknya saja. Jika dosen/admin, bisa disesuaikan.
        if hasattr(user, 'student_profile'):
            return SuratRequest.objects.filter(student=user.student_profile).order_by('-created_at')
        return SuratRequest.objects.all().order_by('-created_at')


class SuratRequestDetailAPIView(RetrieveAPIView):
    """
    Endpoint untuk melihat detail lengkap suatu pengajuan surat beserta status TTE & Approval.
    GET /api/surat/requests/<int:pk>/
    """
    permission_classes = [permissions.IsAuthenticated]
    queryset = SuratRequest.objects.all()
    serializer_class = SuratRequestDetailSerializer


class LecturerApprovalActionAPIView(APIView):
    """
    Endpoint bagi Dosen/Pejabat untuk menyetujui (APPROVE) atau menolak (REJECT) antrean surat.
    POST /api/surat/approval/<int:approval_id>/action/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, approval_id):
        action = request.data.get('action') # 'APPROVE' atau 'REJECT'
        if action not in ['APPROVE', 'REJECT']:
            return Response({"error": "Aksi harus bernilai 'APPROVE' atau 'REJECT'."}, status=status.HTTP_400_BAD_REQUEST)

        # Pastikan user yang login adalah Dosen (Lecturer)
        try:
            lecturer_obj = request.user.lecturer_profile
        except Lecturer.DoesNotExist:
            return Response({"error": "Anda tidak memiliki hak akses sebagai pejabat pemberi persetujuan."}, status=status.HTTP_403_FORBIDDEN)

        catatan = ""
        if action == 'APPROVE':
            serializer = SuratApprovalActionSerializer(data=request.data)
            if serializer.is_valid():
                catatan = serializer.validated_data.get('catatan', '')
        elif action == 'REJECT':
            serializer = SuratRejectActionSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            catatan = serializer.validated_data['alasan_penolakan']

        # Panggil service workflow approval
        result, http_code = process_approval_action(
            approval_id=approval_id,
            lecturer=lecturer_obj,
            action=action,
            catatan=catatan
        )

        return Response(result, status=http_code)
    
class SuratVerifyAPIView(APIView):
    """
    Endpoint publik untuk memverifikasi keaslian surat via QR Code / Token TTE.
    GET /api/surat/verify/<str:token>/
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, token):
        try:
            # Cari tanda tangan digital berdasarkan token unik QR Code
            tte_sig = TteSignature.objects.select_related(
                'surat_request',
                'surat_request__student',
                'surat_request__student__user',
                'surat_request__student__prodi',
                'surat_request__student__fakultas',
                'surat_request__kode_surat',
                'signer__user'
            ).get(token=token)
        except TteSignature.DoesNotExist:
            return Response({
                "status": "INVALID",
                "message": "Dokumen Surat TIDAK VALID atau palsu. Token verifikasi tidak ditemukan di sistem."
            }, status=status.HTTP_404_NOT_FOUND)

        surat_req = tte_sig.surat_request
        student = surat_req.student

        # Susun data hasil verifikasi resmi
        return Response({
            "status": "VALID",
            "message": "Dokumen Surat ASLI dan terdaftar secara resmi di sistem kampus.",
            "detail_surat": {
                "nomor_surat_resmi": surat_req.nomor_surat_resmi,
                "jenis_surat": surat_req.kode_surat.nama_surat,
                "kategori": surat_req.kode_surat.kategori,
                "tanggal_terbit": surat_req.created_at,
            },
            "mahasiswa": {
                "nim": student.nim,
                "nama": student.user.nama,
                "prodi": student.prodi.nama_prodi,
                "fakultas": student.fakultas.nama_fakultas,
            },
            "tte_info": {
                "hash_sha256": tte_sig.hash_document,
                "penandatangan": tte_sig.signer.user.nama if tte_sig.signer else "Sistem Otomatis Kampus",
                "tanggal_ttd": tte_sig.created_at
            }
        }, status=status.HTTP_200_OK)