from .slot_memory import SlotMemoryManager, is_value_filled
from .backend_bridge import (
    build_safe_validator_adapter,
    ensure_approval_queue_for_request,
    evaluate_draft_readiness,
    extract_dynamic_fields_from_surat_type,
    install_backend_integration_bridges,
    persist_attachments_for_request,
)
from .prompts import (
    build_initial_user_prompt,
    build_redraft_with_memory_user_prompt,
    build_self_reflection_revision_prompt,
    build_system_prompt,
    format_slots_summary,
)

# Pasang jembatan integrasi otomatis dari modul agen ke komponen backend
install_backend_integration_bridges()

try:
    from .execution_tools import (
        ExecutionPipelineResult,
        SuratExecutionTools,
        execute_post_approval_tools,
    )
    from .letter_agent import (
        SuratAgentConfigurationError,
        SuratAgentError,
        SuratAgentRateLimitError,
        SuratAgentTimeoutError,
        SuratAgentUpstreamError,
        SuratAgentValidationError,
        SuratDraftingAgent,
    )
    from .memory_agent import (
        AgenticMemoryAgent,
        SuratMemoryAgent,
        compare_and_store_memory,
    )

    __all__ = [
        "SuratDraftingAgent",
        "AgenticMemoryAgent",
        "SuratMemoryAgent",
        "SuratExecutionTools",
        "ExecutionPipelineResult",
        "execute_post_approval_tools",
        "compare_and_store_memory",
        "SlotMemoryManager",
        "is_value_filled",
        "ensure_approval_queue_for_request",
        "evaluate_draft_readiness",
        "extract_dynamic_fields_from_surat_type",
        "persist_attachments_for_request",
        "build_safe_validator_adapter",
        "install_backend_integration_bridges",
        "build_initial_user_prompt",
        "build_redraft_with_memory_user_prompt",
        "build_self_reflection_revision_prompt",
        "build_system_prompt",
        "format_slots_summary",
        "SuratAgentError",
        "SuratAgentTimeoutError",
        "SuratAgentRateLimitError",
        "SuratAgentValidationError",
        "SuratAgentConfigurationError",
        "SuratAgentUpstreamError",
    ]
except ImportError:
    __all__ = [
        "SlotMemoryManager",
        "is_value_filled",
        "ensure_approval_queue_for_request",
        "evaluate_draft_readiness",
        "extract_dynamic_fields_from_surat_type",
        "persist_attachments_for_request",
        "build_safe_validator_adapter",
        "install_backend_integration_bridges",
        "build_initial_user_prompt",
        "build_redraft_with_memory_user_prompt",
        "build_self_reflection_revision_prompt",
        "build_system_prompt",
        "format_slots_summary",
    ]
