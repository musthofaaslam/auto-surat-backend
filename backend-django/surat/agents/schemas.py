from datetime import date
from typing import Any, Dict, List, Type, Union
from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator, model_validator

# SARAN PERBAIKAN ARSITEKTURAL:
# 1. Fungsi `build_dynamic_payload_schema` telah direvisi agar menerima `List[Dict[str, str]]`
#    sesuai struktur aktual `required_field_surat.json` dan memetakan tipe "date" ke `datetime.date`.
# 2. Struktur komposisi bersarang (`extracted_payload` dan `evaluation`) dipertahankan
#    karena sangat efektif memisahkan konteks ekstraksi data dan refleksi diri pada LLM.


# class SuratMagangPayloadSchema(BaseModel):
#     """
#     Kontrak data dasar berdasarkan `required_field_surat.json` untuk jenis surat
#     observasi atau magang.
#     """

#     model_config = ConfigDict(
#         extra="forbid",
#         str_strip_whitespace=True,
#     )

#     instansi_tujuan: str = Field(
#         ...,
#         min_length=3,
#         max_length=255,
#         description="Nama resmi instansi atau perusahaan yang menerima surat.",
#     )
#     tujuan_keperluan: str = Field(
#         ...,
#         min_length=5,
#         max_length=500,
#         description="Tujuan spesifik penggunaan surat secara formal.",
#     )
#     posisi_dilamar: str = Field(
#         ...,
#         min_length=2,
#         max_length=150,
#         description="Posisi atau divisi magang yang dituju.",
#     )
#     tanggal_mulai: date = Field(
#         ...,
#         description="Tanggal mulai kegiatan dalam format ISO 8601 (YYYY-MM-DD).",
#     )
#     tanggal_selesai: date = Field(
#         ...,
#         description="Tanggal selesai kegiatan dalam format ISO 8601 (YYYY-MM-DD).",
#     )

#     @field_validator("instansi_tujuan", "tujuan_keperluan", "posisi_dilamar")
#     @classmethod
#     def validate_non_empty_text(cls, value: str) -> str:
#         if not value or not value.strip():
#             raise ValueError("Atribut teks wajib diisi dan tidak boleh hanya berisi spasi kosong.")
#         return value

#     @model_validator(mode="after")
#     def validate_date_chronology(self) -> "SuratMagangPayloadSchema":
#         if self.tanggal_selesai < self.tanggal_mulai:
#             raise ValueError(
#                 "Atribut tanggal_selesai tidak boleh lebih awal daripada tanggal_mulai."
#             )
#         return self


class SelfEvaluationSchema(BaseModel):
    """
    Skema evaluasi diri (Self-Reflection) untuk memvalidasi kualitas draf secara internal
    sebelum masuk ke tahap PENDING_APPROVAL.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    self_critique_score: int = Field(
        ...,
        ge=1,
        le=10,
        description="Skor evaluasi internal agen (1-10) terhadap formalitas dan kelengkapan atribut.",
    )
    revision_notes: List[str] = Field(
        default_factory=list,
        description="Catatan koreksi internal atau peringatan untuk ditinjau Admin.",
    )

    @model_validator(mode="after")
    def validate_critique_consistency(self) -> "SelfEvaluationSchema":
        if self.self_critique_score < 8 and not self.revision_notes:
            raise ValueError(
                "Apabila self_critique_score kurang dari 8, revision_notes wajib memuat "
                "minimal satu alasan evaluasi untuk ditinjau oleh Admin."
            )
        return self


# class AgentSuratDraftOutputSchema(BaseModel):
#     """
#     Skema Structured Output utama yang dikembalikan oleh Surat Agent pada Fase 1.
#     """

#     model_config = ConfigDict(
#         extra="forbid",
#         str_strip_whitespace=True,
#     )

#     # extracted_payload: SuratMagangPayloadSchema = Field(
#     #     ...,
#     #     description="Data atribut terstruktur yang diekstrak dari konteks pengguna.",
#     # )
#     ai_original_draft: str = Field(
#         ...,
#         min_length=50,
#         description="Naskah draf surat formal utuh yang disusun oleh agen.",
#     )
#     evaluation: SelfEvaluationSchema = Field(
#         ...,
#         description="Hasil evaluasi internal agen terhadap draf yang baru disusun.",
#     )

#     def to_payload_dict(self) -> Dict[str, Any]:
#         """
#         Mengekstrak dictionary murni yang siap disimpan ke kolom `SuratRequest.payload_data`.
#         """
#         return {
#             "instansi_tujuan": self.extracted_payload.instansi_tujuan,
#             "tujuan_keperluan": self.extracted_payload.tujuan_keperluan,
#             "posisi_dilamar": self.extracted_payload.posisi_dilamar,
#             "tanggal_mulai": self.extracted_payload.tanggal_mulai.isoformat(),
#             "tanggal_selesai": self.extracted_payload.tanggal_selesai.isoformat(),
#         }


# # Alias untuk menjaga kompatibilitas impor modul
# AgentLetterOutputSchema = AgentSuratDraftOutputSchema
from typing import Optional # Pastikan Optional sudah diimpor

def build_dynamic_payload_schema(
    schema_name: str, required_fields: Union[List[Dict[str, str]], Dict[str, str]]
) -> Type[BaseModel]:
    """
    Factory function untuk membangun skema Pydantic secara dinamis baik dari struktur list
    pada `required_field_surat.json` maupun dictionary dari database.
    Seluruh field dibuat opsional (bisa bernilai None) untuk mendukung Zero-Hallucination Policy.
    """
    field_definitions: Dict[str, Any] = {}

    if isinstance(required_fields, list):
        for item in required_fields:
            field_name = item["field"]
            field_type_str = item.get("type", "string")
            desc = item.get("description") or item.get("label", "")

            # Ubah tipe menjadi Optional dan default=None agar tidak wajib diisi AI
            if field_type_str == "date":
                field_definitions[field_name] = (Optional[date], Field(None, description=desc))
            else:
                field_definitions[field_name] = (
                    Optional[str],
                    Field(None, description=desc),
                )
    elif isinstance(required_fields, dict):
        for field_name, field_description in required_fields.items():
            field_definitions[field_name] = (
                Optional[str],
                Field(None, description=str(field_description)),
            )

    return create_model(
        schema_name,
        __config__=ConfigDict(extra="forbid", str_strip_whitespace=True),
        **field_definitions,
    )
    
def create_dynamic_agent_output_schema(dynamic_payload_schema: Type[BaseModel]) -> Type[BaseModel]:
    """
    Factory untuk membungkus payload dinamis ke dalam struktur output utama agen
    beserta evaluasi diri (Self-Reflection).
    """
    return create_model(
        "DynamicAgentSuratDraftOutputSchema",
        __config__=ConfigDict(extra="forbid", str_strip_whitespace=True),
        extracted_payload=(dynamic_payload_schema, Field(..., description="Data atribut terstruktur dinamis.")),
        ai_original_draft=(str, Field(..., min_length=50, description="Naskah draf surat formal utuh.")),
        evaluation=(SelfEvaluationSchema, Field(..., description="Hasil evaluasi internal agen.")),
    )