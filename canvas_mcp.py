"""
Canvas LMS MCP Server — Remote/Cloud version (SSE transport)
Exposes Canvas API as tools usable in any Claude session.
"""

import os
import json
import urllib.request
from datetime import datetime, timedelta
from mcp.server.fastmcp import FastMCP

# ── Config ────────────────────────────────────────────────────────────────────
CANVAS_BASE = "https://csulb.instructure.com/api/v1"
TOKEN = os.environ.get("CANVAS_TOKEN", "21139~ekkazRPUMrDBRt46Phy6JyXL6UDnfrxBu7ZnnN6Rz2MCRYDTVTYt8QfcnmHWvhYM")
PORT = int(os.environ.get("PORT", 8000))

mcp = FastMCP("Canvas", host="0.0.0.0", port=PORT)


def _get(path: str, params: dict = None) -> list | dict:
    url = f"{CANVAS_BASE}{path}"
    if params:
        query = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
        url = f"{url}?{query}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


import urllib.parse


@mcp.tool()
def get_due_today() -> str:
    """Get everything due today on Canvas."""
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    items = _get("/planner/items", {"start_date": today, "end_date": tomorrow, "per_page": "50"})
    if not items:
        return "Nothing due today!"
    lines = []
    for item in items:
        title = item.get("plannable", {}).get("title", "Untitled")
        course = item.get("context_name", "")
        kind = item.get("plannable_type", "")
        subs = item.get("submissions", {})
        submitted = subs.get("submitted", False) if isinstance(subs, dict) else False
        status = "✅" if submitted else "⬜"
        lines.append(f"{status} {title} — {course} ({kind})")
    return "\n".join(lines)


@mcp.tool()
def get_upcoming_assignments(days: int = 7) -> str:
    """Get assignments and events due in the next N days (default 7)."""
    start = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    items = _get("/planner/items", {"start_date": start, "end_date": end, "per_page": "50"})
    if not items:
        return "No upcoming items."
    lines = []
    for item in items:
        title = item.get("plannable", {}).get("title", "Untitled")
        due = item.get("plannable_date", "")[:10]
        course = item.get("context_name", "")
        kind = item.get("plannable_type", "")
        subs = item.get("submissions", {})
        submitted = subs.get("submitted", False) if isinstance(subs, dict) else False
        missing = subs.get("missing", False) if isinstance(subs, dict) else False
        status = "✅" if submitted else ("🔴 MISSING" if missing else "⬜")
        lines.append(f"[{due}] {status} {title} — {course} ({kind})")
    return "\n".join(lines)


@mcp.tool()
def get_missing_assignments() -> str:
    """Get all missing or unsubmitted assignments."""
    start = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    items = _get("/planner/items", {"start_date": start, "end_date": end, "per_page": "100"})
    missing = []
    for item in items:
        subs = item.get("submissions", {})
        if not isinstance(subs, dict):
            continue
        if not subs.get("submitted") and not subs.get("excused") and item.get("plannable_type") == "assignment":
            title = item.get("plannable", {}).get("title", "Untitled")
            due = item.get("plannable_date", "")[:10]
            course = item.get("context_name", "")
            pts = item.get("plannable", {}).get("points_possible", "?")
            missing.append(f"[{due}] {title} — {course} ({pts} pts)")
    return "\n".join(missing) if missing else "No missing assignments!"


@mcp.tool()
def get_grades() -> str:
    """Get current grades for all active courses."""
    courses = _get("/courses", {"enrollment_state": "active", "include[]": "total_scores", "per_page": "20"})
    lines = []
    for c in courses:
        name = c.get("name", "Unknown")
        enroll = c.get("enrollments", [{}])[0] if c.get("enrollments") else {}
        score = enroll.get("computed_current_score")
        grade = enroll.get("computed_current_grade", "")
        if score is not None:
            lines.append(f"{name}: {grade} ({score}%)")
        else:
            lines.append(f"{name}: N/A")
    return "\n".join(lines) if lines else "No grade data found."


@mcp.tool()
def get_announcements() -> str:
    """Get recent announcements from all courses."""
    context_codes = ["course_111078", "course_116443", "course_114428"]
    params = {"per_page": "10"}
    for i, code in enumerate(context_codes):
        params[f"context_codes[{i}]"] = code
    announcements = _get("/announcements", params)
    if not announcements:
        return "No recent announcements."
    lines = []
    for a in announcements:
        title = a.get("title", "No title")
        posted = a.get("posted_at", "")[:10]
        course = a.get("context_name", "")
        lines.append(f"[{posted}] {title} — {course}")
    return "\n".join(lines)


@mcp.tool()
def get_courses() -> str:
    """List all active enrolled courses."""
    courses = _get("/courses", {"enrollment_state": "active", "per_page": "20"})
    lines = [f"ID {c.get('id')} — {c.get('name', 'Unknown')} ({c.get('course_code', '')})" for c in courses]
    return "\n".join(lines) if lines else "No active courses found."


if __name__ == "__main__":
        mcp.run(transport="sse")
