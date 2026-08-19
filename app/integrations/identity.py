import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

async def get_app_branding(app_id: str) -> dict:
    """
    Fetches the public branding configuration for a given application ID 
    from the Identity Service.
    """
    url = f"{settings.identity_service_url.rstrip('/')}/api/v1/applications/{app_id}/configuration"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                return {
                    "app_name": data.get("name", "Platform"),
                    "branding": {
                        "primary_color": data.get("primary_color"),
                        "secondary_color": data.get("secondary_color"),
                        "logo_url": data.get("logo_url"),
                        "logo_with_text": data.get("logo_with_text"),
                    }
                }
            logger.warning("Identity Service returned %d for app %s", response.status_code, app_id)
    except Exception as exc:
        logger.warning("Failed to fetch branding for app %s from Identity Service: %s", app_id, exc)
    return {}
