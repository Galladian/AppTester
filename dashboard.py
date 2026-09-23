# dashboard.py
import streamlit as st
import asyncio
import pandas as pd
from crawler import APICrawler
from fuzzer import APIFuzzer

st.set_page_config(
    page_title="AI AppTester Dashboard",
    page_icon="⚡",
    layout="wide"
)

st.title("⚡ AI AppTester — Autonomous Quality & Security Auditor")
st.caption("AI-powered crawling, payload fuzzing, and issue detection for modern web applications.")

# --- Sidebar Inputs ---
st.sidebar.header("Scan Configuration")
target_url = st.sidebar.text_input("Target Base URL", value="http://127.0.0.1:8000")
openai_key = st.sidebar.text_input("OpenAI API Key (Optional)", type="password", help="Leave blank to use smart offline heuristic fallback.")
start_scan = st.sidebar.button("🚀 Start AI Scan", use_container_width=True)

# --- Execution Function ---
async def run_full_audit(url: str, api_key: str):
    crawler = APICrawler(url)
    
    with st.status("🔍 Discovering OpenAPI blueprint...", expanded=True) as status:
        schema = await crawler.discover_openapi_schema()
        endpoints = crawler.extract_endpoints(schema)
        
        if not endpoints:
            status.update(label="❌ No endpoints discovered!", state="error")
            return None, None
            
        status.write(f"Found {len(endpoints)} active API endpoints.")
        status.update(label="✅ Endpoint Discovery Complete!", state="complete")

    fuzzer = APIFuzzer(openai_api_key=api_key if api_key else None)
    all_issues = []

    progress_bar = st.progress(0)
    status_text = st.empty()

    for idx, ep in enumerate(endpoints):
        status_text.text(f"Auditing [{ep['method']}] {ep['path']}...")
        payloads = await fuzzer.generate_test_payloads(ep)
        issues = await fuzzer.execute_and_audit(ep, payloads)
        all_issues.extend(issues)
        progress_bar.progress((idx + 1) / len(endpoints))

    status_text.text("Audit Complete!")
    return endpoints, all_issues

# --- Main Dashboard Area ---
if start_scan:
    endpoints, issues = asyncio.run(run_full_audit(target_url, openai_key))

    if endpoints is not None and issues is not None:
        st.divider()
        
        # High Level Metrics
        bugs_count = sum(1 for i in issues if i.issue_type == "BUG")
        improvements_count = sum(1 for i in issues if i.issue_type == "IMPROVEMENT")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Endpoints Audited", len(endpoints))
        col2.metric("🔴 Critical Bugs", bugs_count)
        col3.metric("💡 UX & Performance Improvements", improvements_count)

        st.divider()

        # Detailed Issue Output
        st.subheader("📋 Executive Audit Report")

        if not issues:
            st.success("🎉 No issues detected! The application appears healthy.")
        else:
            for issue in issues:
                icon = "🔴" if issue.issue_type == "BUG" else "💡"
                card_title = f"{icon} [{issue.issue_type}] {issue.title}"
                
                with st.expander(card_title, expanded=True):
                    st.write(f"**Endpoint:** `{issue.method} {issue.endpoint}`")
                    st.write(f"**HTTP Status:** `{issue.status_code}` | **Response Time:** `{issue.response_time_ms:.1f}ms`")
                    st.write(f"**Description:** {issue.description}")
                    st.write(f"**Recommended Fix:** {issue.recommendation}")
                    st.caption("Payload Sent:")
                    st.json(issue.payload_sent)

else:
    st.info("👈 Enter target URL in the sidebar and click **Start AI Scan** to begin live audit.")