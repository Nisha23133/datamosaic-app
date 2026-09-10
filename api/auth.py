"""
Platform Owner authentication.
Public endpoints (discovery, AI suggestions, request submission) are open.
Only administrative and approval operations require Platform Owner password authorization.
"""

from fastapi import Header, HTTPException
import config


def verify_platform_owner_password(x_platform_owner_password: str = Header(default=None, alias="X-Platform-Owner-Password")):
    if x_platform_owner_password != config.PLATFORM_OWNER_PASSWORD:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Incorrect Platform Owner password."
        )


