"""Dependency aliases for the KG domain.

Follows the full-stack-fastapi-template idiom of declaring
`Annotated[T, Depends(...)]` once and reusing the alias in every route
signature. Routes get to write `kg: KGDep` instead of
`kg: KG = Depends(get_kg)`.

NOTE: KG is imported at runtime (not only under TYPE_CHECKING) so that
FastAPI can resolve the Annotated type alias without a NameError. Keeping
it under TYPE_CHECKING caused FastAPI to treat the parameter as a query
param in Python 3.13.
"""

from typing import Annotated

from fastapi import Depends, Request

from app.kg.loader import KG


def get_kg(request: Request) -> KG:
    """Pull the KG instance out of the app-level state populated by
    `lifespan`. Raises a clear error if the app is misconfigured."""
    kg = getattr(request.app.state, "kg", None)
    if kg is None:
        from app.core.exceptions import KGNotLoadedError

        raise KGNotLoadedError(
            "KG is not loaded on app.state -- did lifespan run?",
        )
    return kg


KGDep = Annotated[KG, Depends(get_kg)]
