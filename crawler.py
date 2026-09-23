# crawler.py
import httpx
from bs4 import BeautifulSoup
from typing import Dict, List, Any

class APICrawler:
    def __init__(self, base_url: str):
        # Normalise base URL 
        self.base_url = base_url.rstrip("/")

    async def discover_openapi_schema(self) -> Dict[str, Any]:
        """Attempts to discover and fetch OpenAPI/Swagger schema via common paths"""
        common_schema_paths = [
            "/openapi.json",
            "/swagger.json",
            "/api-docs",
            "/v1/openapi.json"
        ]

        async with httpx.AsyncClient(timeout=5.0) as client:
            # Fetch schemas 
            # Done aync to avoid blocking the event loop in case of slow responses [REMOVE LATER]
            for path in common_schema_paths:
                try:
                    target = f"{self.base_url}{path}"
                    response = await client.get(target)
                    if response.status_code == 200 and "application/json" in response.headers.get("content-type", ""):
                        print(f"[Crawler] Found OpenAPI schema at: {target}")
                        return response.json()
                except Exception:
                    continue

        print("[Crawler] OpenAPI schema not directly found. Returning empty schema.")
        return {}

    def extract_endpoints(self, schema: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Iterates JSON paths to extract endpoint information"""
        endpoints = []
        paths = schema.get("paths", {})

        for path, methods in paths.items():
            for method, details in methods.items():
                if method.upper() not in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                    continue

                # Extract request body structure if present
                request_body = details.get("requestBody", {})
                schema_ref = None
                
                if request_body:
                    content = request_body.get("content", {})
                    json_content = content.get("application/json", {})
                    schema_ref = json_content.get("schema", {})

                endpoints.append({
                    "path": path,
                    "method": method.upper(),
                    "full_url": f"{self.base_url}{path}",
                    "summary": details.get("summary", ""),
                    "request_schema": schema_ref
                })

        return endpoints

# --- Local test ---
if __name__ == "__main__":
    # Tests for crawler functionality
    import asyncio

    async def main():
        crawler = APICrawler("http://127.0.0.1:8000")
        schema = await crawler.discover_openapi_schema()
        endpoints = crawler.extract_endpoints(schema)
        
        print(f"\nSuccessfully discovered {len(endpoints)} endpoints:")
        for ep in endpoints:
            print(f" -> [{ep['method']}] {ep['full_url']}")

    asyncio.run(main())