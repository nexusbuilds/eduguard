from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import settings

class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("Host")
        tenant_id = None

        if host:
            host = host.split(":")[0]
            if host in ["localhost", "127.0.0.1"] or "tail1f5702.ts.net" in host or "nexus" in host:
                tenant_id = "default"
            else:
                parts = host.split(".")
                if len(parts) > 2 and parts[0] not in ["www", "localhost", "127.0.0.1"]:
                    tenant_id = parts[0]
                elif len(parts) == 2:  # e.g., eduguard.com
                    tenant_id = "default"
                else:
                    tenant_id = request.headers.get("X-Tenant-ID")
        else:
            tenant_id = request.headers.get("X-Tenant-ID")

        if tenant_id is None:
            raise HTTPException(status_code=400, detail="Tenant ID not found in host or header")

        request.state.tenant_id = tenant_id
        return await call_next(request)