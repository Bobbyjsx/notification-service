import os
from collections.abc import AsyncGenerator

from fastapi import Request
from google.auth.credentials import AnonymousCredentials
from google.cloud.firestore_v1.async_client import AsyncClient

from app.core.config import settings

_db_client: AsyncClient | None = None


def get_db_client() -> AsyncClient:
    """Creates a configured AsyncClient for Firestore with emulator / ADC fallback."""
    emulator_host = os.environ.get("FIRESTORE_EMULATOR_HOST")
    project = settings.google_cloud_project or os.environ.get("GOOGLE_CLOUD_PROJECT", "local-dev-project")
    database = settings.firestore_database or "(default)"

    if emulator_host:
        return AsyncClient(
            project=project,
            database=database,
            credentials=AnonymousCredentials(),
        )

    creds_file = (
        settings.google_application_credentials
        or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        or ("firebase-credentials.json" if os.path.exists("firebase-credentials.json") else None)
    )

    if creds_file and os.path.exists(creds_file):
        return AsyncClient.from_service_account_json(
            creds_file,
            database=database,
            project=project if project else None,
        )

    return AsyncClient(
        project=project if project else None,
        database=database,
    )


async def get_db(request: Request) -> AsyncGenerator[AsyncClient, None]:
    """FastAPI dependency for accessing the shared async Firestore client."""
    client: AsyncClient | None = getattr(request.app.state, "db_client", None)
    if client is None:
        global _db_client
        if _db_client is None:
            _db_client = get_db_client()
        client = _db_client
    yield client
