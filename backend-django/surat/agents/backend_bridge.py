import inspect
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_BRIDGE_INSTALLED = False


def ensure_approval_queue_for_request(surat_request: Any) -> int:
    """
    Membangun antrean berjenjang `SuratApproval` berdasarkan `ApprovalRule` (DPA -> KAPRODI -> DEKAN)
    ketika draf AI pada `SuratRequest` mencapai status `PENDING_APPROVAL` (Menutup Bagian 2 #1).
    Jika `SuratApproval` untuk `surat_request` tersebut sudah ada, fungsi ini bersifat idempotent.
    """
    try:
        from surat.models import ApprovalRule, ApprovalStatus, SuratApproval, SuratStatus

        if getattr(surat_request, "status", None) != SuratStatus.PENDING_APPROVAL:
            return 0

        if SuratApproval.objects.filter(surat_request=surat_request).exists():
            return 0

        student = getattr(surat_request, "student", None)
        surat_type = getattr(surat_request, "kode_surat", None)
        if student is None or surat_type is None:
            return 0

        rules = list(ApprovalRule.objects.filter(kode_surat=surat_type).order_by("step_order"))
        created_count = 0

        if not rules:
            default_approver = (
                getattr(student, "dosen_pembimbing_akademik", None)
                or getattr(getattr(student, "prodi", None), "kaprodi", None)
                or getattr(getattr(student, "fakultas", None), "dekan", None)
            )
            if default_approver is not None:
                SuratApproval.objects.create(
                    surat_request=surat_request,
                    step_order=1,
                    approver=default_approver,
                    status=ApprovalStatus.PENDING,
                )
                created_count = 1
        else:
            for rule in rules:
                role = str(getattr(rule, "approval_role", "")).strip().upper()
                approver_obj = None
                if role == "DPA":
                    approver_obj = getattr(student, "dosen_pembimbing_akademik", None)
                elif role == "KAPRODI":
                    approver_obj = getattr(getattr(student, "prodi", None), "kaprodi", None)
                elif role == "DEKAN":
                    approver_obj = getattr(getattr(student, "fakultas", None), "dekan", None)
                elif role in ("WADEK_1", "WADEK1"):
                    approver_obj = getattr(getattr(student, "fakultas", None), "wadek_1", None)
                elif role in ("WADEK_3", "WADEK3"):
                    approver_obj = getattr(getattr(student, "fakultas", None), "wadek_3", None)
                elif role in ("KOOR_MAGANG", "KOORDINATOR_MAGANG"):
                    approver_obj = getattr(student, "koordinator_magang_prodi", None)

                if approver_obj is not None:
                    created_count += 1
                    SuratApproval.objects.create(
                        surat_request=surat_request,
                        step_order=rule.step_order,
                        approver=approver_obj,
                        status=(
                            ApprovalStatus.PENDING
                            if created_count == 1
                            else ApprovalStatus.WAITING
                        ),
                    )

        if created_count > 0:
            logger.info(
                "Berhasil membuat %d antrean SuratApproval berjenjang untuk SuratRequest id=%s.",
                created_count,
                getattr(surat_request, "id", None),
            )
        return created_count
    except Exception as exc:
        logger.warning(
            "Gagal membuat antrean SuratApproval otomatis untuk SuratRequest id=%s: %s",
            getattr(surat_request, "id", None),
            exc,
        )
        return 0


def persist_attachments_for_request(
    surat_request: Any,
    attachment_files: Optional[List[Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Menyimpan berkas lampiran (`attachments`) dari permohonan mahasiswa ke Cloudinary
    dan mencatatnya ke tabel `SuratAttachment`, serta mengekstrak byte dokumen untuk
    diteruskan ke Gemini Multimodal API pada `SuratDraftingAgent` (Menutup Bagian 2 #5).
    """
    extracted_multimodal_parts: List[Dict[str, Any]] = []
    if not attachment_files:
        return extracted_multimodal_parts

    try:
        from surat.models import SuratAttachment
    except Exception:
        SuratAttachment = None  # type: ignore[assignment]

    for file_obj in attachment_files:
        try:
            filename = str(getattr(file_obj, "name", "lampiran.pdf") or "lampiran.pdf")
            mime_type = str(
                getattr(file_obj, "content_type", None) or "application/pdf"
            )
            raw_bytes: Optional[bytes] = None
            if hasattr(file_obj, "read") and callable(file_obj.read):
                if hasattr(file_obj, "seek") and callable(file_obj.seek):
                    try:
                        file_obj.seek(0)
                    except Exception:
                        pass
                raw_bytes = file_obj.read()
                if hasattr(file_obj, "seek") and callable(file_obj.seek):
                    try:
                        file_obj.seek(0)
                    except Exception:
                        pass
            elif isinstance(file_obj, (bytes, bytearray)):
                raw_bytes = bytes(file_obj)

            if raw_bytes:
                extracted_multimodal_parts.append(
                    {
                        "name": filename,
                        "mime_type": mime_type,
                        "bytes": raw_bytes,
                    }
                )

            # Simpan ke Cloudinary & SuratAttachment jika model tersedia
            if SuratAttachment is not None and surat_request is not None:
                file_url = f"https://res.cloudinary.com/autosurat/raw/upload/{filename}"
                try:
                    import cloudinary.uploader

                    upload_res = cloudinary.uploader.upload(
                        file_obj,
                        resource_type="auto",
                        folder="autosurat_attachments",
                    )
                    if isinstance(upload_res, dict) and upload_res.get("secure_url"):
                        file_url = str(upload_res["secure_url"])
                except Exception:
                    pass

                try:
                    SuratAttachment.objects.create(
                        surat_request=surat_request,
                        nama_dokumen=filename[:255],
                        file_url=file_url[:500],
                        mime_type=mime_type[:100],
                    )
                except Exception as db_exc:
                    logger.warning("Gagal menyimpan record SuratAttachment: %s", db_exc)
        except Exception as exc:
            logger.warning("Gagal memproses berkas lampiran '%s': %s", file_obj, exc)

    return extracted_multimodal_parts


def build_safe_validator_adapter(original_validators: Dict[str, Any]) -> Dict[str, Any]:
    """
    Membungkus dictionary `SURAT_VALIDATORS` di `surat/services/validators.py` dengan
    Intelligent Signature Adapter agar ketidaksesuaian jumlah parameter pada 5 jenis surat
    (`SK-BEA`, `SP-SKC`, `SI-MAG`, `SI-SUR`, `SP-TRA`) dan perbedaan nama key `student_courses_data`
    (`student_id` vs `nim`, `course_id` vs `kode_matkul`) terselesaikan tanpa melempar `TypeError`
    (Menutup Bagian 2 #7).
    """

    def _normalize_courses_data(
        student_data: Dict[str, Any],
        courses_data: Optional[List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        if not isinstance(courses_data, list):
            return []
        default_nim = student_data.get("nim", "") if isinstance(student_data, dict) else ""
        normalized: List[Dict[str, Any]] = []
        for item in courses_data:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            if "nim" not in row:
                row["nim"] = row.get("student_id") or default_nim
            if "kode_matkul" not in row and "course_id" in row:
                row["kode_matkul"] = row["course_id"]
            normalized.append(row)
        return normalized

    wrapped_map: Dict[str, Any] = {}

    for kode, func in original_validators.items():
        if getattr(func, "_is_agent_adapted", False):
            wrapped_map[kode] = func
            continue

        def _make_adapter(target_fn: Any, target_kode: str) -> Any:
            sig = inspect.signature(target_fn)
            param_names = list(sig.parameters.keys())
            arity = len(param_names)

            def _adapted_validator(
                student_data: Dict[str, Any],
                payload: Optional[Dict[str, Any]] = None,
                student_courses_data: Optional[List[Dict[str, Any]]] = None,
            ) -> Any:
                safe_payload = payload if isinstance(payload, dict) else {}
                norm_courses = _normalize_courses_data(student_data, student_courses_data)

                if target_kode == "SP-TRA" or param_names == [
                    "student_data",
                    "student_courses_data",
                    "semester_aktif",
                ]:
                    semester_aktif = (
                        student_data.get("semester_aktif", 1)
                        if isinstance(student_data, dict)
                        else 1
                    )
                    return target_fn(student_data, norm_courses, semester_aktif)

                if target_kode == "SI-SUR" or param_names == [
                    "student_data",
                    "student_courses_data",
                ]:
                    # Periksa apakah fungsi di dalamnya memanggil verify_observation_course_enrolled
                    # yang membutuhkan 3 argumen (student_nim, course_code, student_courses_data)
                    try:
                        return target_fn(student_data, norm_courses)
                    except TypeError:
                        from rest_framework import serializers
                        from surat.services.helpers import verify_observation_course_enrolled

                        course_code = (
                            safe_payload.get("kode_matkul")
                            or safe_payload.get("mata_kuliah")
                            or (norm_courses[0].get("kode_matkul") if norm_courses else "")
                        )
                        if not course_code and not norm_courses:
                            # Saat fase awal AI drafting dan payload belum diekstrak, lewati jika belum ada kode matkul
                            return None
                        is_enrolled, msg = verify_observation_course_enrolled(
                            student_data.get("nim"),
                            course_code,
                            norm_courses,
                        )
                        if not is_enrolled:
                            raise serializers.ValidationError(msg)
                        return None

                if arity == 1:
                    return target_fn(student_data)
                if arity == 2:
                    return target_fn(student_data, safe_payload)
                return target_fn(student_data, safe_payload, norm_courses)

            _adapted_validator._is_agent_adapted = True  # type: ignore[attr-defined]
            _adapted_validator._original_fn = target_fn  # type: ignore[attr-defined]
            return _adapted_validator

        wrapped_map[kode] = _make_adapter(func, kode)

    return wrapped_map


def extract_dynamic_fields_from_surat_type(surat_type: Any) -> Optional[Dict[str, str]]:
    """
    Fungsi siap panggil bagi Backend (`views.py#L692`) untuk mengekstrak spesifikasi
    field dinamis dari objek model `SuratType` (membaca kolom `required_payload_fields`
    maupun alias `required_fields_dict`) menjadi dictionary `{field_name: description}`.
    """
    if surat_type is None:
        return None
    raw_fields = getattr(surat_type, "required_payload_fields", None)
    if not raw_fields:
        raw_fields = getattr(surat_type, "__dict__", {}).get("required_fields_dict")
    if isinstance(raw_fields, dict) and raw_fields:
        return {str(k).strip(): str(v) for k, v in raw_fields.items() if str(k).strip()}
    if isinstance(raw_fields, list) and raw_fields:
        converted: Dict[str, str] = {}
        for item in raw_fields:
            if isinstance(item, dict) and item.get("field"):
                fname = str(item["field"]).strip()
                fdesc = str(item.get("description") or item.get("label") or fname)
                if fname:
                    converted[fname] = fdesc
            elif isinstance(item, str) and item.strip():
                fname = item.strip()
                converted[fname] = fname.replace("_", " ").title()
        return converted or None
    return None


def evaluate_draft_readiness(
    draft_output: Any,
    kode_surat: str,
    dynamic_fields_dict: Optional[Dict[str, Any]] = None,
    min_score: int = 8,
    agent: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Fungsi siap panggil bagi Backend (`views.py#L150` dan `views.py#L380-L384`) untuk
    mengevaluasi secara akurat apakah hasil `draft_output` dari `SuratDraftingAgent`
    telah memenuhi seluruh syarat kelengkapan slot (`SlotMemoryManager` & `is_value_filled`)
    dan ambang batas `self_critique_score >= min_score`.

    Mengembalikan dictionary:
    {
        "is_ready_for_approval": bool,       # True -> PENDING_APPROVAL, False -> REVISION_REQUIRED
        "recommended_status": str,           # "PENDING_APPROVAL" atau "REVISION_REQUIRED"
        "critique_score": int,
        "has_missing_fields": bool,
        "missing_fields": List[Dict[str, str]],
        "structured_payload": Dict[str, Any],
        "revision_notes": List[str],
    }
    """
    from surat.agents.letter_agent import SuratDraftingAgent
    from surat.agents.slot_memory import SlotMemoryManager

    if hasattr(draft_output, "to_payload_dict") and callable(draft_output.to_payload_dict):
        structured_payload = draft_output.to_payload_dict()
    elif hasattr(draft_output, "extracted_payload"):
        ep = draft_output.extracted_payload
        structured_payload = ep.model_dump(mode="json") if hasattr(ep, "model_dump") else dict(ep)
    elif isinstance(draft_output, dict):
        structured_payload = dict(draft_output)
    else:
        structured_payload = {}

    evaluation_obj = getattr(draft_output, "evaluation", None)
    critique_score = int(getattr(evaluation_obj, "self_critique_score", 0) or 0)
    revision_notes = list(getattr(evaluation_obj, "revision_notes", []) or [])

    helper_agent = agent if agent is not None else SuratDraftingAgent(api_key="validation-only")
    required_fields = helper_agent.get_required_fields_for_kode(
        kode_surat=kode_surat,
        dynamic_fields_dict=dynamic_fields_dict,
    )
    slot_mgr = SlotMemoryManager(
        kode_surat=kode_surat,
        required_fields=required_fields,
        initial_slots=structured_payload,
    )
    missing_fields = slot_mgr.get_missing_fields()
    has_missing = len(missing_fields) > 0

    if has_missing:
        critique_score = min(critique_score, 7)
        for note in slot_mgr.generate_clarification_notes():
            if note not in revision_notes:
                revision_notes.append(note)

    is_ready = (critique_score >= min_score) and (not has_missing)
    return {
        "is_ready_for_approval": is_ready,
        "recommended_status": "PENDING_APPROVAL" if is_ready else "REVISION_REQUIRED",
        "critique_score": critique_score,
        "has_missing_fields": has_missing,
        "missing_fields": missing_fields,
        "structured_payload": structured_payload,
        "revision_notes": revision_notes,
    }


def install_backend_integration_bridges() -> None:
    """
    Memasang jembatan integrasi (Runtime Integration Bridges) dari modul `surat.agents`
    ke komponen-komponen backend (`SuratType`, `SuratRequest`, `SURAT_VALIDATORS`)
    secara non-intrusif tanpa perlu mengubah kode di luar `surat/agents/`:
    1. Bridge `SuratType.required_fields_dict` -> `required_payload_fields` (Bagian 2 #3).
    2. Bridge `SuratRequest.save` -> otomatis men-generate antrean `SuratApproval` saat
       status menjadi `PENDING_APPROVAL` dan menangkap `attachments` dari request aktif
       untuk disimpan ke `SuratAttachment` & diteruskan ke Gemini Multimodal (Bagian 2 #1 & #5).
    3. Bridge `SURAT_VALIDATORS` -> mengadaptasi signature ke-10 fungsi validator (Bagian 2 #7).
    """
    global _BRIDGE_INSTALLED
    if _BRIDGE_INSTALLED:
        return

    # 1. Pasang adapter pada SURAT_VALIDATORS (dapat bekerja dengan atau tanpa Django DB)
    try:
        from surat.services import validators as validators_mod

        if hasattr(validators_mod, "SURAT_VALIDATORS") and isinstance(
            validators_mod.SURAT_VALIDATORS, dict
        ):
            adapted = build_safe_validator_adapter(validators_mod.SURAT_VALIDATORS)
            validators_mod.SURAT_VALIDATORS.update(adapted)
    except Exception as exc:
        logger.debug("Melewati pemasangan bridge SURAT_VALIDATORS: %s", exc)

    # 2. Pasang property `required_fields_dict` pada `SuratType` & lifecycle hook pada `SuratRequest`
    try:
        from surat.models import SuratRequest, SuratStatus, SuratType

        if not hasattr(SuratType, "required_fields_dict"):
            setattr(
                SuratType,
                "required_fields_dict",
                property(lambda self: extract_dynamic_fields_from_surat_type(self)),
            )

        orig_save = getattr(SuratRequest, "save", None)
        if orig_save is not None and not getattr(orig_save, "_is_agent_bridged", False):
            def _bridged_surat_request_save(self: Any, *args: Any, **kwargs: Any) -> Any:
                is_creating = self.pk is None
                result = orig_save(self, *args, **kwargs)

                # Jika baru dibuat di SuratRequestCreateAPIView.post, periksa apakah caller
                # memiliki serializer.validated_data["attachments"] atau request.FILES
                if is_creating:
                    try:
                        frame = inspect.currentframe()
                        while frame is not None:
                            if frame.f_code.co_name == "post":
                                ser = frame.f_locals.get("serializer")
                                files_list = None
                                if ser is not None and hasattr(ser, "validated_data"):
                                    files_list = ser.validated_data.get("attachments")
                                if not files_list:
                                    req = frame.f_locals.get("request")
                                    if req is not None and hasattr(req, "FILES"):
                                        files_list = req.FILES.getlist("attachments")
                                if files_list:
                                    multimodal_parts = persist_attachments_for_request(
                                        self, files_list
                                    )
                                    setattr(self, "_multimodal_attachments", multimodal_parts)
                                break
                            frame = frame.f_back
                    except Exception:
                        pass

                # Jika status mencapai PENDING_APPROVAL, pastikan antrean SuratApproval dibuat
                if getattr(self, "status", None) == SuratStatus.PENDING_APPROVAL:
                    ensure_approval_queue_for_request(self)

                return result

            _bridged_surat_request_save._is_agent_bridged = True  # type: ignore[attr-defined]
            setattr(SuratRequest, "save", _bridged_surat_request_save)

        _BRIDGE_INSTALLED = True
    except Exception as exc:
        logger.debug("Melewati pemasangan bridge model Django: %s", exc)

