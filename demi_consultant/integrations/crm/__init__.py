from demi_consultant.integrations.crm.crm_service import (
    CRMService,
    InMemoryCRM,
    JSONFileCRM,
    NullCRM,
    PostgreSQLCRM,
    build_crm_service,
)

__all__ = [
    "CRMService",
    "InMemoryCRM",
    "JSONFileCRM",
    "NullCRM",
    "PostgreSQLCRM",
    "build_crm_service",
]
