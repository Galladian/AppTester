# fuzzer.py
import httpx
import json
import os
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from openai import AsyncOpenAI

class TestPayload(BaseModel):
    test_type: str = Field(description="Type of test: 'valid', 'edge_case', or 'malformed'")
    payload: Dict[str, Any] = Field(description="The JSON request body to send to the endpoint")
    reasoning: str = Field(description="Explanation of what this payload is testing")

class PayloadGenerationResult(BaseModel):
    test_cases: List[TestPayload]

class AuditIssue(BaseModel):
    """Stores details of issue found during auditing"""
    issue_type: str  # "BUG" or "IMPROVEMENT"
    title: str
    endpoint: str
    method: str
    payload_sent: Dict[str, Any]
    status_code: int
    response_time_ms: float
    description: str
    recommendation: str

class APIFuzzer:
    def __init__(self, openai_api_key: Optional[str] = None):
        api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self.client = AsyncOpenAI(api_key=api_key) if api_key else None

    async def generate_test_payloads(self, endpoint_info: Dict[str, Any]) -> List[TestPayload]:
        """Uses LLM structured outputs to generate smart edge-case test payloads."""
        # Fallback if no API key is set for offline testing
        if not self.client:
            return self._heuristic_fallback_payloads(endpoint_info)

        system_prompt = (
            "You are an expert QA API Security & Reliability Engineer. "
            "Analyze the given OpenAPI route and parameters schema. "
            "Generate 3 distinct JSON payloads designed to test this endpoint:\n"
            "1. Valid: Standard expected input.\n"
            "2. Edge Case: Boundary conditions (e.g. 0, negative numbers, empty strings, max int).\n"
            "3. Malformed: Invalid data types or unexpected missing keys."
        )

        user_prompt = f"""
        Endpoint: [{endpoint_info['method']}] {endpoint_info['path']}
        Request Schema: {json.dumps(endpoint_info.get('request_schema', {}))}
        """

        try:
            # Use OpenAI Structured Outputs via client.beta.chat.completions.parse
            response = await self.client.beta.chat.completions.parse(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format=PayloadGenerationResult
            )
            return response.choices[0].message.parsed.test_cases
        except Exception as e:
            print(f"[Fuzzer Warning] AI generation failed ({e}). Falling back to heuristic generator.")
            return self._heuristic_fallback_payloads(endpoint_info)

    def _heuristic_fallback_payloads(self, endpoint_info: Dict[str, Any]) -> List[TestPayload]:
        """Provides instant local fallback payloads if API key is missing or network drops."""
        path = endpoint_info["path"]
        if "checkout" in path:
            return [
                TestPayload(test_type="valid", payload={"item_id": "p1", "quantity": 2, "user_email": "test@app.com"}, reasoning="Valid checkout"),
                TestPayload(test_type="edge_case", payload={"item_id": "p1", "quantity": -1, "user_email": "test@app.com"}, reasoning="Negative quantity trigger"),
                TestPayload(test_type="malformed", payload={"item_id": "p1"}, reasoning="Missing required fields")
            ]
        elif "reviews" in path:
            return [
                TestPayload(test_type="valid", payload={"product_id": "p1", "comment": "Great product!"}, reasoning="Valid review"),
                TestPayload(test_type="edge_case", payload={"product_id": "p1", "comment": ""}, reasoning="Empty string review")
            ]
        return [TestPayload(test_type="valid", payload={}, reasoning="Default baseline")]

    async def execute_and_audit(self, endpoint_info: Dict[str, Any], test_cases: List[TestPayload]) -> List[AuditIssue]:
        """Executes the AI payloads against the live server and classifies responses into Bugs or Improvements."""
        issues = []
        
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            for test in test_cases:
                url = endpoint_info["full_url"]
                method = endpoint_info["method"]

                try:
                    start_time = httpx.ByteStream.time() if hasattr(httpx.ByteStream, "time") else 0
                    import time
                    start = time.time()
                    
                    if method == "POST":
                        res = await http_client.post(url, json=test.payload)
                    else:
                        res = await http_client.get(url, params=test.payload)
                    
                    elapsed_ms = (time.time() - start) * 1000

                    # --- BUG CLASSIFICATION ---
                    if res.status_code == 500:
                        issues.append(AuditIssue(
                            issue_type="BUG",
                            title="Unhandled Internal Server Crash (500 Error)",
                            endpoint=url,
                            method=method,
                            payload_sent=test.payload,
                            status_code=500,
                            response_time_ms=elapsed_ms,
                            description=f"Server crashed when tested with {test.test_type} payload: '{test.reasoning}'.",
                            recommendation="Add input validation boundaries and handle exceptions gracefully with 400 status codes."
                        ))

                    # --- IMPROVEMENT CLASSIFICATION ---
                    elif elapsed_ms > 1000:
                        issues.append(AuditIssue(
                            issue_type="IMPROVEMENT",
                            title="Slow Endpoint Latency (>1000ms)",
                            endpoint=url,
                            method=method,
                            payload_sent=test.payload,
                            status_code=res.status_code,
                            response_time_ms=elapsed_ms,
                            description=f"Response took {elapsed_ms:.1f}ms to complete, which degrades user experience.",
                            recommendation="Optimize database queries, introduce response caching, or run heavy operations asynchronously."
                        ))
                    
                    elif res.status_code == 200 and "err" in res.json():
                        issues.append(AuditIssue(
                            issue_type="IMPROVEMENT",
                            title="Vague Error Format (200 OK with internal error body)",
                            endpoint=url,
                            method=method,
                            payload_sent=test.payload,
                            status_code=200,
                            response_time_ms=elapsed_ms,
                            description="API returned HTTP 200 OK containing an ambiguous error payload (e.g. {'err': 1}).",
                            recommendation="Return HTTP 400 Bad Request with standardized error responses (e.g., {'error': 'Comment cannot be empty'})."
                        ))

                except Exception as e:
                    print(f"[Fuzzer Error] Failed request to {url}: {e}")

        return issues

# --- Local test ---
if __name__ == "__main__":
    # Tests for crawler functionality
    import asyncio
    from crawler import APICrawler

    async def main():
        crawler = APICrawler("http://127.0.0.1:8000")
        schema = await crawler.discover_openapi_schema()
        endpoints = crawler.extract_endpoints(schema)

        fuzzer = APIFuzzer()  # Uses heuristic fallback if OPENAI_API_KEY is not set
        all_issues = []

        for ep in endpoints:
            print(f"\n[Fuzzer] Generating AI payloads for {ep['method']} {ep['path']}...")
            payloads = await fuzzer.generate_test_payloads(ep)
            
            print(f"[Fuzzer] Executing {len(payloads)} test cases...")
            issues = await fuzzer.execute_and_audit(ep, payloads)
            all_issues.extend(issues)

        print("\n================ AUDIT SUMMARY ================")
        print(f"Total Issues Detected: {len(all_issues)}\n")
        for issue in all_issues:
            icon = "🔴" if issue.issue_type == "BUG" else "💡"
            print(f"{icon} [{issue.issue_type}] {issue.title}")
            print(f"   Endpoint: {issue.method} {issue.endpoint}")
            print(f"   Payload: {issue.payload_sent}")
            print(f"   Description: {issue.description}\n")

    asyncio.run(main())