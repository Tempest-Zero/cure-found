"""Annotated-Depends alias for the diagnosis service.

NOTE: DiagnoseService is imported at runtime so FastAPI can resolve the
Annotated alias without a NameError (forward-ref strings inside Annotated
break dependency detection in Python 3.13).
"""

from typing import Annotated

from fastapi import Depends, Request

from app.diagnose.service import DiagnoseService


def get_diagnose_service(request: Request) -> DiagnoseService:
    svc = getattr(request.app.state, "diagnose_service", None)
    if svc is None:
        from app.core.exceptions import KGNotLoadedError

        raise KGNotLoadedError(
            "DiagnoseService not initialised on app.state -- did lifespan run?",
        )
    return svc


DiagnoseDep = Annotated[DiagnoseService, Depends(get_diagnose_service)]
