"""Annotated-Depends alias for the repurpose service.

NOTE: RepurposeService is imported at runtime so FastAPI can resolve the
Annotated alias without a NameError (forward-ref strings inside Annotated
break dependency detection in Python 3.13).
"""

from typing import Annotated

from fastapi import Depends, Request

from app.repurpose.service import RepurposeService


def get_repurpose_service(request: Request) -> RepurposeService:
    svc = getattr(request.app.state, "repurpose_service", None)
    if svc is None:
        from app.core.exceptions import KGNotLoadedError

        raise KGNotLoadedError(
            "RepurposeService not initialised on app.state -- did lifespan run?",
        )
    return svc


RepurposeDep = Annotated[RepurposeService, Depends(get_repurpose_service)]
