"""
Canvas LMS MCP Server - Remote/Cloud version (SSE transport)
Exposes Canvas API as tools usable in any Claude session.
"""
import os
import re
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from mcp.server.fastmcp import FastMCP

CANVAS_BASE = "https://csulb.instructure.com/api/v1"
TOKEN = os.environ.get("CANVAS_TOKEN", "21139~ekkazRPUMrDBRt46Phy6JyXL6UDnfrxBu7ZnnN6Rz2MCRYDTVTYt8QfcnmHWvhYM")
PORT = int(os.environ.get("PORT", 8000))

mcp = FastMCP("Canvas", host="0.0.0.0", port=PORT)


def _hdr():
    return {"Authorization": f"Bearer {TOKEN}"}


def _get(path, params=None):
    url = CANVAS_BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_hdr())
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def _get_all(path, params=None):
    params = dict(params or {})
    params.setdefault("per_page", "100")
    url = CANVAS_BASE + path + "?" + urllib.parse.urlencode(params)
    results = []
    while url:
        req = urllib.request.Request(url, headers=_hdr())
        with urllib.request.urlopen(req, timeout=15) as r:
            results.extend(json.loads(r.read().decode()))
            link = r.headers.get("Link", "")
            url = None
            for part in link.split(","):
                if 'rel="next"' in part:
                    url = part.split(";")[0].strip().strip("<>")
    return results


def _active_course_ids() -> list:
    """Return IDs of all currently active enrolled courses."""
    courses = _get("/courses", {"enrollment_state": "active", "per_page": "50"})
    return [c["id"] for c in courses if isinstance(c, dict) and c.get("id")]


@mcp.tool()
def get_courses() -> str:
    """List all active Canvas courses with their IDs."""
    courses = _get("/courses", {"enrollment_state": "active", "per_page": "50"})
    if not courses:
        return "No active courses."
    lines = []
    for c in courses:
        if isinstance(c, dict) and c.get("id"):
            lines.append(f"[id:{c['id']}] {c.get('name', '?')} - {c.get('course_code', '')}")
    return "\n".join(lines) if lines else "No courses found."


@mcp.tool()
def get_due_today() -> str:
    """Get all Canvas assignments due today."""
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    items = _get("/planner/items", {"start_date": today, "end_date": tomorrow, "per_page": "50"})
    if not items:
        return "Nothing due today!"
    lines = []
    for item in items:
        title = item.get("plannable", {}).get("title", "Untitled")
        course = item.get("context_name", "")
        lines.append(f"- {title}" + (f" - {course}" if course else ""))
    return "\n".join(lines)


@mcp.tool()
def get_upcoming_assignments(days: int = 7) -> str:
    """Get Canvas assignments due in the next N days (default 7)."""
    today = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    items = _get_all("/planner/items", {"start_date": today, "end_date": end})
    if not items:
        return f"Nothing due in the next {days} days."
    lines = []
    for item in items:
        title = item.get("plannable", {}).get("title", "Untitled")
        course = item.get("context_name", "")
        due = (item.get("plannable_date") or "")[:10]
        lines.append(f"[{due}] {title}" + (f" - {course}" if course else ""))
    return "\n".join(lines)


@mcp.tool()
def get_missing_assignments() -> str:
    """Get Canvas assignments that are missing/unsubmitted (looks back 90 days)."""
    start = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")
    items = _get_all("/planner/items", {"start_date": start, "end_date": today})
    missing = [
        a for a in items
        if a.get("plannable_type") == "assignment"
        and not (a.get("submissions") or {}).get("submitted")
    ]
    if not missing:
        return "No missing assignments found."
    lines = []
    for a in missing:
        title = a.get("plannable", {}).get("title", "?")
        course = a.get("context_name", "?")
        due = (a.get("plannable_date") or "?")[:10]
        lines.append(f"[{due}] {title} - {course}")
    return "\n".join(lines)


@mcp.tool()
def get_grades() -> str:
    """Get current grades for all active Canvas courses."""
    enrollments = _get_all("/users/self/enrollments", {
        "type[]": "StudentEnrollment",
        "state[]": "active",
        "per_page": "50"
    })
    if not enrollments:
        return "No enrollments found."
    lines = []
    for e in enrollments:
        course_name = e.get("course", {}).get("name") or f"Course {e.get('course_id', '?')}"
        grade = e.get("grades", {})
        current = grade.get("current_grade") or grade.get("current_score") or "N/A"
        final = grade.get("final_grade") or grade.get("final_score") or "N/A"
        lines.append(f"{course_name}: current={current}, final={final}")
    return "\n".join(lines) if lines else "No grade data found."


@mcp.tool()
def get_announcements() -> str:
    """Get recent announcements with full message text from all active courses."""
    course_ids = _active_course_ids()
    if not course_ids:
        return "No active courses found."
    params = {"per_page": "20"}
    for i, cid in enumerate(course_ids[:10]):
        params[f"context_codes[{i}]"] = f"course_{cid}"
    announcements = _get("/announcements", params)
    if not announcements:
        return "No recent announcements."
    lines = []
    for a in announcements:
        title = a.get("title", "?")
        posted = (a.get("posted_at") or "?")[:10]
        context = a.get("context_name") or a.get("context_code", "?")
        msg = re.sub(r'<[^>]+>', ' ', a.get("message", "")).strip()
        msg = ' '.join(msg.split())[:500]
        lines.append(f"[{posted}] {context}: {title}")
        if msg:
            lines.append(f"  > {msg}")
    return "\n".join(lines)


@mcp.tool()
def get_modules(course_id: int) -> str:
    """Get all modules and their items for a specific course."""
    modules = _get_all(f"/courses/{course_id}/modules", {"include[]": "items"})
    if not modules:
        return f"No modules found for course {course_id}."
    lines = []
    for m in modules:
        lines.append(f"\n## {m.get('name', '?')}")
        for item in m.get("items", []):
            lines.append(f"  - [{item.get('type', '?')}] {item.get('title', '?')}")
    return "\n".join(lines)


@mcp.tool()
def get_course_assignments(course_id: int) -> str:
    """Get all assignments for a specific course with due dates and submission status."""
    assignments = _get_all(f"/courses/{course_id}/assignments", {
        "include[]": "submission",
        "order_by": "due_at"
    })
    if not assignments:
        return f"No assignments found for course {course_id}."
    lines = []
    for a in assignments:
        title = a.get("name", "?")
        aid = a.get("id", "?")
        due = (a.get("due_at") or "no due date")[:10]
        sub = a.get("submission", {}) or {}
        submitted = sub.get("submitted_at")
        score = sub.get("score")
        late = sub.get("late", False)
        missing = sub.get("missing", False)
        flag = "submitted" if submitted else ("missing" if missing else "not submitted")
        if late:
            flag += " (LATE)"
        if score is not None:
            flag += f" - score: {score}/{a.get('points_possible', '?')}"
        lines.append(f"[{due}] (id:{aid}) {title} - {flag}")
    return "\n".join(lines)


@mcp.tool()
def get_submission(course_id: int, assignment_id: int) -> str:
    """Get detailed submission info for a specific assignment, including submitted filenames."""
    sub = _get(
        f"/courses/{course_id}/assignments/{assignment_id}/submissions/self",
        {"include[]": "submission_comments"}
    )
    if not sub:
        return "No submission data found."
    lines = []
    workflow = sub.get("workflow_state", "?")
    submitted_at = sub.get("submitted_at")
    score = sub.get("score")
    late = sub.get("late", False)
    missing = sub.get("missing", False)
    lines.append(f"Status: {workflow}")
    if submitted_at:
        lines.append(f"Submitted at: {submitted_at}")
    if late:
        lines.append("WARNING: This submission was LATE")
    if missing:
        lines.append("WARNING: Marked as MISSING")
    if score is not None:
        lines.append(f"Score: {score}")
    attachments = sub.get("attachments", [])
    if attachments:
        lines.append("Submitted files:")
        for f in attachments:
            lines.append(f"  - {f.get('filename', '?')} ({f.get('size', '?')} bytes)")
    comments = sub.get("submission_comments", [])
    if comments:
        lines.append("Comments:")
        for c in comments:
            lines.append(f"  [{(c.get('created_at') or '')[:10]}] {c.get('author_name', '?')}: {c.get('comment', '')}")
    return "\n".join(lines) if lines else "Submission exists but no details available."


@mcp.tool()
def get_course_announcements(course_id: int, count: int = 10) -> str:
    """Get recent announcements with full message text for a specific course."""
    announcements = _get(
        f"/courses/{course_id}/discussion_topics",
        {"only_announcements": "true", "per_page": str(count), "order_by": "posted_at"}
    )
    if not announcements:
        return f"No announcements found for course {course_id}."
    lines = []
    for a in announcements:
        title = a.get("title", "?")
        posted = (a.get("posted_at") or "?")[:10]
        msg = re.sub(r'<[^>]+>', ' ', a.get("message", "")).strip()
        msg = ' '.join(msg.split())[:600]
        lines.append(f"[{posted}] {title}")
        if msg:
            lines.append(f"  > {msg}")
    return "\n".join(lines)


@mcp.tool()
def get_announcement_detail(course_id: int, announcement_id: int) -> str:
    """Get the full body text of a specific announcement by its ID."""
    data = _get(f"/courses/{course_id}/discussion_topics/{announcement_id}", {})
    if not data or isinstance(data, list):
        return "Announcement not found."
    title = data.get("title", "?")
    posted = (data.get("posted_at") or "?")[:10]
    msg = re.sub(r'<[^>]+>', ' ', data.get("message", "")).strip()
    msg = ' '.join(msg.split())
    return f"[{posted}] {title}\n\n{msg}"


@mcp.tool()
def get_submission_file(course_id: int, assignment_id: int) -> str:
    """Download and return text content of submitted files for an assignment (up to 3000 chars per file)."""
    sub = _get(
        f"/courses/{course_id}/assignments/{assignment_id}/submissions/self",
        {"include[]": "submission_comments"}
    )
    if not sub or isinstance(sub, list):
        return "Submission not found."
    attachments = sub.get("attachments", [])
    if not attachments:
        return "No file attachments found in this submission."
    results = []
    for att in attachments:
        filename = att.get("filename", "unknown")
        url = att.get("url", "")
        if not url:
            results.append(f"--- {filename} ---\n(no download URL)")
            continue
        try:
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read(3000)
            try:
                text = raw.decode("utf-8", errors="replace")
            except Exception:
                text = "(binary file, cannot display as text)"
            results.append(f"--- {filename} ---\n{text[:3000]}")
        except Exception as e:
            results.append(f"--- {filename} ---\n(error downloading: {e})")
    return "\n\n".join(results)


if __name__ == "__main__":
    mcp.run(transport="sse")