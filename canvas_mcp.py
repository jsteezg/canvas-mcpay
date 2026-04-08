"""
Canvas LMS MCP Server — Remote/Cloud version (SSE transport)
Exposes Canvas API as tools usable in any Claude session.
"""
import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from mcp.server.fastmcp import FastMCP

# ── Config ───────────────────────────────────────────────────────────────────
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


def _get_all(path: str, params: dict = None) -> list:
    """Fetch all pages from a paginated Canvas endpoint."""
    params = dict(params or {})
    params.setdefault("per_page", "100")
    url = f"{CANVAS_BASE}{path}"
    query = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    url = f"{url}?{query}"
    results = []
    while url:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            results.extend(json.loads(resp.read().decode()))
            link = resp.headers.get("Link", "")
            url = None
            for part in link.split(","):
                if 'rel="next"' in part:
                    url = part.split(";")[0].strip().strip("<>")
    return results


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
    """Get all missing or unsubmitted assignments (looks back 90 days)."""
    start = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
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
    """List all active enrolled courses with their IDs."""
    courses = _get("/courses", {"enrollment_state": "active", "per_page": "20"})
    lines = [f"ID {c.get('id')} — {c.get('name', 'Unknown')} ({c.get('course_code', '')})"
             for c in courses]
    return "\n".join(lines) if lines else "No active courses found."


@mcp.tool()
def get_modules(course_id: int) -> str:
    """Get all modules and their items for a course. Use get_courses first to find the course ID."""
    modules = _get_all(f"/courses/{course_id}/modules", {"include[]": "items"})
    if not modules:
        return f"No modules found for course {course_id}."
    lines = []
    for mod in modules:
        lines.append(f"\n📦 {mod.get('name', 'Unnamed')} (items: {mod.get('items_count', 0)})")
        for item in mod.get("items", []):
            title = item.get("title", "Untitled")
            kind = item.get("type", "")
            content_id = item.get("content_id", "")
            lines.append(f"  • [{kind}] {title}" + (f" (id:{content_id})" if content_id else ""))
    return "\n".join(lines)


@mcp.tool()
def get_course_assignments(course_id: int) -> str:
    """Get all assignments for a course with scores and submission status. Shows late flags."""
    assignments = _get_all(
        f"/courses/{course_id}/assignments",
        {"include[]": "submission", "order_by": "due_at"}
    )
    if not assignments:
        return f"No assignments found for course {course_id}."
    lines = []
    for a in assignments:
        title = a.get("name", "Untitled")
        due = (a.get("due_at") or "")[:10] or "no due date"
        pts = a.get("points_possible", "?")
        sub = a.get("submission", {}) or {}
        state = sub.get("workflow_state", "unsubmitted")
        score = sub.get("score")
        late = sub.get("late", False)
        missing = sub.get("missing", False)

        if state == "graded":
            flag = f"✅ {score}/{pts}"
            if late:
                flag += " ⚠️ LATE"
        elif state == "submitted":
            flag = "📬 submitted"
            if late:
                flag += " ⚠️ LATE"
        elif missing:
            flag = "🔴 MISSING"
        else:
            flag = "⬜ not submitted"

        lines.append(f"[{due}] {title} — {flag}")
    return "\n".join(lines)


@mcp.tool()
def get_submission(course_id: int, assignment_id: int) -> str:
    """Get detailed submission info for a specific assignment including late penalty."""
    sub = _get(f"/courses/{course_id}/assignments/{assignment_id}/submissions/self",
               {"include[]": "submission_comments"})
    if not sub:
        return "No submission found."
    state = sub.get("workflow_state", "unknown")
    score = sub.get("score")
    late = sub.get("late", False)
    missing = sub.get("missing", False)
    submitted_at = (sub.get("submitted_at") or "")[:16]
    graded_at = (sub.get("graded_at") or "")[:16]
    late_policy = sub.get("points_deducted")

    lines = [
        f"State: {state}",
        f"Submitted: {submitted_at or 'not submitted'}",
        f"Late: {'Yes' if late else 'No'}",
        f"Missing: {'Yes' if missing else 'No'}",
        f"Score: {score} pts" if score is not None else "Score: not graded",
        f"Graded at: {graded_at or 'not graded'}",
    ]
    if late_policy:
        lines.append(f"Points deducted (late penalty): {late_policy}")

    comments = sub.get("submission_comments", [])
    if comments:
        lines.append("\nComments:")
        for c in comments:
            author = c.get("author", {}).get("display_name", "?")
            body = c.get("comment", "")[:200]
            lines.append(f"  {author}: {body}")

    return "\n".join(lines)


@mcp.tool()
def get_course_announcements(course_id: int, count: int = 10) -> str:
    """Get announcements for a specific course."""
    announcements = _get("/announcements", {
        "context_codes[0]": f"course_{course_id}",
        "per_page": str(count)
    })
    if not announcements:
        return f"No announcements for course {course_id}."
    lines = []
    for a in announcements:
        title = a.get("title", "No title")
        posted = (a.get("posted_at") or "")[:10]
        lines.append(f"[{posted}] {title}")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="sse")
