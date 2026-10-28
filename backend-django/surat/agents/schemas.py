from datetime import date
from typing import Any, Dict, List, Type, Union
from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator, model_validator

# SARAN PERBAIKAN ARSITEKTURAL:
# 1. Fungsi `build_dynamic_payload_schema` telah direvisi agar menerima `List[Dict[str, str]]`
#    sesuai struktur aktual `required_field_surat.json` dan memetakan tipe "date" ke `datetime.date`.
# 2. Struktur komposisi bersarang (`extracted_payload` dan `evaluation`) dipertahankan
#    karena sangat efektif memisahkan konteks ekstraksi data dan refleksi diri pada LLM.

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
    
# Alias untuk menjaga kompatibilitas impor modul
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

class ClarificationEvaluationSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    is_complete: bool = Field(
        ...,
        description="Bernilai True jika informasi pengguna sudah cukup untuk menyusun surat, False jika masih ada data yang kurang."
    )
    missing_fields: List[str] = Field(
        default_factory=list,
        description="Field utama/pertama yang masih belum disebutkan oleh pengguna."
    )
    clarification_message: str = Field(
        default="",
        description="Pertanyaan interaktif yang ramah dan spesifik untuk menanyakan 1 hal yang kurang tersebut kepada pengguna."
    )