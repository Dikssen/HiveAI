"""
Fleio support analytics tools — read-only queries against the Fleio MySQL database.
Configure via /api/integrations: FLEIO_DB_HOST, FLEIO_DB_PORT, FLEIO_DB_USER, FLEIO_DB_PASSWORD, FLEIO_DB_NAME.
"""
from contextlib import contextmanager
from typing import Optional

from pydantic import BaseModel, Field

from app.db.integration_config_helper import get_integration_value
from app.tools.base import LoggedTool

_NOT_CONFIGURED_MSG = (
    "FLEIO_NOT_CONFIGURED: Fleio database is not configured. "
    "Set FLEIO_DB_HOST, FLEIO_DB_USER, FLEIO_DB_PASSWORD, FLEIO_DB_NAME via /api/integrations. "
    "Do not retry — inform the user."
)


def _get_connection():
    import pymysql

    host = get_integration_value("FLEIO_DB_HOST") or ""
    user = get_integration_value("FLEIO_DB_USER") or ""
    password = get_integration_value("FLEIO_DB_PASSWORD") or ""
    db = get_integration_value("FLEIO_DB_NAME") or ""
    port = int(get_integration_value("FLEIO_DB_PORT") or "3306")

    if not host or not user or not db:
        raise RuntimeError(_NOT_CONFIGURED_MSG)

    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=db,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5,
        read_timeout=10,
    )


@contextmanager
def _db():
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            yield cur
    finally:
        conn.close()


@contextmanager
def _fleio_errors():
    try:
        yield
    except RuntimeError:
        raise
    except Exception as e:
        msg = str(e)
        if "connect" in msg.lower() or "refused" in msg.lower() or "timed out" in msg.lower():
            raise RuntimeError(
                f"FLEIO_UNREACHABLE: Cannot connect to Fleio database ({e}). "
                "Check FLEIO_DB_HOST and network. Do not retry."
            ) from e
        raise RuntimeError(f"FLEIO_DB_ERROR: {e}. Do not retry — inform the user.") from e


def _fmt_dt(dt) -> str:
    return str(dt)[:16] if dt else "—"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

class FleioTicketSummaryTool(LoggedTool):
    name: str = "FleioTicketSummary"
    description: str = (
        "Get an overview of Fleio support tickets: total count, breakdown by status and priority, "
        "number of unanswered tickets, and tickets created in the last 7 and 30 days. "
        "Use this first to understand the current support workload."
    )

    def _run(self) -> str:
        with _fleio_errors():
            with _db() as cur:
                cur.execute("SELECT COUNT(*) AS total FROM tickets_ticket")
                total = cur.fetchone()["total"]

                cur.execute("""
                    SELECT status, COUNT(*) AS cnt
                    FROM tickets_ticket
                    GROUP BY status ORDER BY cnt DESC
                """)
                by_status = cur.fetchall()

                cur.execute("""
                    SELECT priority, COUNT(*) AS cnt
                    FROM tickets_ticket
                    GROUP BY priority ORDER BY cnt DESC
                """)
                by_priority = cur.fetchall()

                cur.execute("""
                    SELECT COUNT(*) AS cnt FROM tickets_ticket
                    WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
                """)
                last_7 = cur.fetchone()["cnt"]

                cur.execute("""
                    SELECT COUNT(*) AS cnt FROM tickets_ticket
                    WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
                """)
                last_30 = cur.fetchone()["cnt"]

                cur.execute("""
                    SELECT COUNT(*) AS cnt FROM tickets_ticket
                    WHERE status IN ('open', 'customer reply')
                """)
                unanswered = cur.fetchone()["cnt"]

                cur.execute("""
                    SELECT AVG(TIMESTAMPDIFF(HOUR, t.created_at, tu.created_at)) AS avg_hours
                    FROM tickets_ticketupdate tu
                    JOIN tickets_ticket t ON tu.ticket_id = t.id
                    WHERE tu.created_by_id IN (SELECT id FROM core_appuser WHERE is_staff = 1)
                """)
                avg = cur.fetchone()["avg_hours"]

            lines = [
                f"Fleio Support Summary",
                f"=====================",
                f"Total tickets: {total}",
                f"Unanswered (open + customer reply): {unanswered}",
                f"Created last 7 days: {last_7}",
                f"Created last 30 days: {last_30}",
                f"Avg first staff response: {round(avg, 1)}h" if avg else "Avg first staff response: n/a",
                "",
                "By status:",
            ]
            for r in by_status:
                lines.append(f"  {r['status']}: {r['cnt']}")
            lines.append("\nBy priority:")
            for r in by_priority:
                lines.append(f"  {r['priority']}: {r['cnt']}")

            return "\n".join(lines)


class FleioListTicketsInput(BaseModel):
    status: str = Field(
        default="",
        description="Filter by status: 'open', 'answered', 'customer reply'. Empty = all."
    )
    priority: str = Field(
        default="",
        description="Filter by priority: 'low', 'medium', 'high', 'urgent'. Empty = all."
    )
    days: int = Field(
        default=0,
        description="Limit to tickets created in the last N days. 0 = no limit."
    )
    limit: int = Field(default=20, description="Maximum number of tickets to return")


class FleioListTicketsTool(LoggedTool):
    name: str = "FleioListTickets"
    description: str = (
        "List Fleio support tickets with optional filters by status, priority, and date range. "
        "Returns ticket ID, title, status, priority, client name, created date, and last reply date. "
        "Use FleioGetTicket to read full details and replies of a specific ticket."
    )
    args_schema: type[BaseModel] = FleioListTicketsInput

    def _run(self, status: str = "", priority: str = "", days: int = 0, limit: int = 20) -> str:
        with _fleio_errors():
            with _db() as cur:
                where = []
                params: list = []
                if status:
                    where.append("t.status = %s")
                    params.append(status)
                if priority:
                    where.append("t.priority = %s")
                    params.append(priority)
                if days:
                    where.append("t.created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)")
                    params.append(days)

                where_sql = "WHERE " + " AND ".join(where) if where else ""
                params.append(min(limit, 100))

                cur.execute(f"""
                    SELECT t.id, t.title, t.status, t.priority,
                           t.created_at, t.last_reply_at,
                           c.first_name, c.last_name, c.company
                    FROM tickets_ticket t
                    LEFT JOIN core_client c ON t.client_id = c.id
                    {where_sql}
                    ORDER BY t.last_reply_at DESC
                    LIMIT %s
                """, params)
                rows = cur.fetchall()

            if not rows:
                return "No tickets found."

            lines = [f"Found {len(rows)} ticket(s):"]
            for r in rows:
                client = r["company"] or f"{r['first_name']} {r['last_name']}".strip() or "—"
                lines.append(
                    f"[{r['id']}] {r['title']}\n"
                    f"  Status: {r['status']} | Priority: {r['priority']} | Client: {client}\n"
                    f"  Created: {_fmt_dt(r['created_at'])} | Last reply: {_fmt_dt(r['last_reply_at'])}"
                )
            return "\n\n".join(lines)


class FleioGetTicketInput(BaseModel):
    ticket_id: str = Field(description="Fleio ticket ID, e.g. 'ABC-123'")


class FleioGetTicketTool(LoggedTool):
    name: str = "FleioGetTicket"
    description: str = (
        "Get full details of a Fleio support ticket including all replies. "
        "Returns ticket info, client details, and the complete conversation thread. "
        "Use FleioListTickets to find ticket IDs first."
    )
    args_schema: type[BaseModel] = FleioGetTicketInput

    def _run(self, ticket_id: str) -> str:
        with _fleio_errors():
            with _db() as cur:
                cur.execute("""
                    SELECT t.id, t.title, t.description, t.status, t.priority,
                           t.created_at, t.last_reply_at,
                           c.first_name, c.last_name, c.company,
                           d.name AS department,
                           u.email AS assigned_to,
                           cb.email AS created_by_email
                    FROM tickets_ticket t
                    LEFT JOIN core_client c ON t.client_id = c.id
                    LEFT JOIN tickets_department d ON t.department_id = d.id
                    LEFT JOIN core_appuser u ON t.assigned_to_id = u.id
                    LEFT JOIN core_appuser cb ON t.created_by_id = cb.id
                    WHERE t.id = %s
                """, (ticket_id,))
                ticket = cur.fetchone()

                if not ticket:
                    return f"Ticket '{ticket_id}' not found."

                cur.execute("""
                    SELECT tu.created_at, tu.reply_text, tu.new_status,
                           tu.new_priority, u.email AS author, u.is_staff
                    FROM tickets_ticketupdate tu
                    LEFT JOIN core_appuser u ON tu.created_by_id = u.id
                    WHERE tu.ticket_id = %s
                    ORDER BY tu.created_at
                """, (ticket_id,))
                replies = cur.fetchall()

            client = ticket["company"] or f"{ticket['first_name']} {ticket['last_name']}".strip() or "—"
            lines = [
                f"Ticket: {ticket['id']}",
                f"Title: {ticket['title']}",
                f"Status: {ticket['status']} | Priority: {ticket['priority']}",
                f"Client: {client}",
                f"Department: {ticket['department'] or '—'} | Assigned to: {ticket['assigned_to'] or 'Unassigned'}",
                f"Created by: {ticket['created_by_email'] or '—'}",
                f"Created: {_fmt_dt(ticket['created_at'])} | Last reply: {_fmt_dt(ticket['last_reply_at'])}",
                f"\nDescription:\n{ticket['description'] or '(empty)'}",
            ]

            if replies:
                lines.append(f"\n--- Replies ({len(replies)}) ---")
                for r in replies:
                    role = "Staff" if r["is_staff"] else "Client"
                    author = r["author"] or "?"
                    lines.append(f"\n[{_fmt_dt(r['created_at'])}] {role} — {author}")
                    if r["new_status"]:
                        lines.append(f"  Status changed to: {r['new_status']}")
                    if r["new_priority"]:
                        lines.append(f"  Priority changed to: {r['new_priority']}")
                    if r["reply_text"]:
                        lines.append(r["reply_text"])

            return "\n".join(lines)


class FleioClientTicketsInput(BaseModel):
    search: str = Field(
        description=(
            "Search by client email, company name, or first/last name. "
            "Example: 'john@example.com' or 'Acme Corp'"
        )
    )


class FleioClientTicketsTool(LoggedTool):
    name: str = "FleioClientTickets"
    description: str = (
        "Find a Fleio client and show all their support tickets and active services. "
        "Search by email, company name, or client name. "
        "Returns client profile, service list, and ticket history."
    )
    args_schema: type[BaseModel] = FleioClientTicketsInput

    def _run(self, search: str) -> str:
        with _fleio_errors():
            with _db() as cur:
                pattern = f"%{search}%"
                cur.execute("""
                    SELECT DISTINCT c.id, c.first_name, c.last_name, c.company,
                                    c.status, c.date_created, c.country,
                                    u.email
                    FROM core_client c
                    LEFT JOIN core_usertoclient uc ON uc.client_id = c.id
                    LEFT JOIN core_appuser u ON uc.user_id = u.id
                    WHERE u.email LIKE %s
                       OR c.company LIKE %s
                       OR c.first_name LIKE %s
                       OR c.last_name LIKE %s
                    LIMIT 5
                """, (pattern, pattern, pattern, pattern))
                clients = cur.fetchall()

                if not clients:
                    return f"No client found matching '{search}'."

                client = clients[0]
                cid = client["id"]

                cur.execute("""
                    SELECT s.id, s.display_name, s.status, s.created_at, s.paid_until,
                           p.name AS product
                    FROM billing_service s
                    JOIN billing_product p ON s.product_id = p.id
                    WHERE s.client_id = %s
                    ORDER BY s.created_at DESC
                """, (cid,))
                services = cur.fetchall()

                cur.execute("""
                    SELECT id, title, status, priority, created_at, last_reply_at
                    FROM tickets_ticket
                    WHERE client_id = %s
                    ORDER BY last_reply_at DESC
                """, (cid,))
                tickets = cur.fetchall()

            name = client["company"] or f"{client['first_name']} {client['last_name']}".strip()
            lines = [
                f"Client: {name}",
                f"Email: {client['email'] or '—'} | Country: {client['country']}",
                f"Status: {client['status']} | Since: {_fmt_dt(client['date_created'])}",
            ]

            lines.append(f"\nServices ({len(services)}):")
            if services:
                for s in services:
                    paid = f" | Paid until: {_fmt_dt(s['paid_until'])}" if s["paid_until"] else ""
                    lines.append(f"  [{s['status']}] {s['display_name']} ({s['product']}){paid}")
            else:
                lines.append("  No services.")

            lines.append(f"\nTickets ({len(tickets)}):")
            if tickets:
                for t in tickets:
                    lines.append(
                        f"  [{t['id']}] {t['title']} | {t['status']} | {t['priority']} | {_fmt_dt(t['last_reply_at'])}"
                    )
            else:
                lines.append("  No tickets.")

            return "\n".join(lines)


class FleioSlaReportInput(BaseModel):
    threshold_days: int = Field(
        default=3,
        description="Tickets open longer than this many days without a staff reply are flagged as SLA violations."
    )


class FleioSlaReportTool(LoggedTool):
    name: str = "FleioSlaReport"
    description: str = (
        "Report on SLA compliance: tickets that have been waiting for a staff reply longer than a threshold. "
        "Returns overdue tickets sorted by wait time (longest first), "
        "plus average first-response time for recently closed tickets. "
        "Use this to identify neglected tickets that need immediate attention."
    )
    args_schema: type[BaseModel] = FleioSlaReportInput

    def _run(self, threshold_days: int = 3) -> str:
        with _fleio_errors():
            with _db() as cur:
                # Overdue: open tickets with no staff reply for > threshold_days
                cur.execute("""
                    SELECT t.id, t.title, t.status, t.priority,
                           t.created_at, t.last_reply_at,
                           DATEDIFF(NOW(), t.last_reply_at) AS days_waiting,
                           c.first_name, c.last_name, c.company
                    FROM tickets_ticket t
                    LEFT JOIN core_client c ON t.client_id = c.id
                    WHERE t.status IN ('open', 'customer reply')
                      AND t.last_reply_at < DATE_SUB(NOW(), INTERVAL %s DAY)
                    ORDER BY days_waiting DESC
                """, (threshold_days,))
                overdue = cur.fetchall()

                # Avg first staff response time (last 30 days)
                cur.execute("""
                    SELECT AVG(TIMESTAMPDIFF(HOUR, t.created_at, first_reply.created_at)) AS avg_hours
                    FROM tickets_ticket t
                    JOIN (
                        SELECT ticket_id, MIN(created_at) AS created_at
                        FROM tickets_ticketupdate
                        WHERE created_by_id IN (SELECT id FROM core_appuser WHERE is_staff = 1)
                        GROUP BY ticket_id
                    ) first_reply ON first_reply.ticket_id = t.id
                    WHERE t.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
                """)
                avg_row = cur.fetchone()
                avg_hours = avg_row["avg_hours"] if avg_row else None

                # Distribution: how many tickets waited 0-4h, 4-24h, 1-3d, 3d+
                cur.execute("""
                    SELECT
                        SUM(CASE WHEN diff_hours < 4   THEN 1 ELSE 0 END) AS under_4h,
                        SUM(CASE WHEN diff_hours BETWEEN 4 AND 23  THEN 1 ELSE 0 END) AS h4_to_24h,
                        SUM(CASE WHEN diff_hours BETWEEN 24 AND 71 THEN 1 ELSE 0 END) AS d1_to_3d,
                        SUM(CASE WHEN diff_hours >= 72 THEN 1 ELSE 0 END) AS over_3d
                    FROM (
                        SELECT TIMESTAMPDIFF(HOUR, t.created_at, first_reply.created_at) AS diff_hours
                        FROM tickets_ticket t
                        JOIN (
                            SELECT ticket_id, MIN(created_at) AS created_at
                            FROM tickets_ticketupdate
                            WHERE created_by_id IN (SELECT id FROM core_appuser WHERE is_staff = 1)
                            GROUP BY ticket_id
                        ) first_reply ON first_reply.ticket_id = t.id
                        WHERE t.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
                    ) sub
                """)
                dist = cur.fetchone()

            lines = [
                f"SLA Report (threshold: {threshold_days} days)",
                f"==========================================",
                f"Avg first staff response (last 30d): {round(avg_hours, 1)}h" if avg_hours else "Avg first staff response: n/a",
            ]

            if dist and any(dist.values()):
                lines += [
                    "\nFirst response time distribution (last 30d):",
                    f"  < 4h:     {dist['under_4h'] or 0}",
                    f"  4h–24h:   {dist['h4_to_24h'] or 0}",
                    f"  1d–3d:    {dist['d1_to_3d'] or 0}",
                    f"  > 3d:     {dist['over_3d'] or 0}",
                ]

            lines.append(f"\nOverdue tickets (no staff reply > {threshold_days}d): {len(overdue)}")
            if overdue:
                lines.append("")
                for r in overdue:
                    client = r["company"] or f"{r['first_name']} {r['last_name']}".strip() or "—"
                    lines.append(
                        f"  [{r['id']}] {r['title']}\n"
                        f"    {r['status']} | {r['priority']} | Client: {client} | Waiting: {r['days_waiting']}d"
                    )

            return "\n".join(lines)


class FleioTrendsInput(BaseModel):
    period: str = Field(
        default="month",
        description="Grouping period: 'week' for last 12 weeks, 'month' for last 12 months."
    )


class FleioTrendsTool(LoggedTool):
    name: str = "FleioTrends"
    description: str = (
        "Show ticket volume trends over time grouped by week or month. "
        "Returns ticket counts per period, top recurring issue patterns from ticket titles, "
        "and which services generate the most tickets. "
        "Use this to detect growing problem areas and seasonal patterns."
    )
    args_schema: type[BaseModel] = FleioTrendsInput

    def _run(self, period: str = "month") -> str:
        with _fleio_errors():
            with _db() as cur:
                if period == "week":
                    cur.execute("""
                        SELECT DATE_FORMAT(created_at, '%Y-W%u') AS period,
                               COUNT(*) AS cnt
                        FROM tickets_ticket
                        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 12 WEEK)
                        GROUP BY period ORDER BY period
                    """)
                else:
                    cur.execute("""
                        SELECT DATE_FORMAT(created_at, '%Y-%m') AS period,
                               COUNT(*) AS cnt
                        FROM tickets_ticket
                        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 12 MONTH)
                        GROUP BY period ORDER BY period
                    """)
                trend_rows = cur.fetchall()

                # Top words in ticket titles (simple frequency)
                cur.execute("SELECT title FROM tickets_ticket")
                titles = [r["title"].lower() for r in cur.fetchall()]

                # Services with most tickets
                cur.execute("""
                    SELECT p.name AS product, COUNT(t.id) AS cnt
                    FROM tickets_ticket t
                    JOIN billing_service s ON t.service_id = s.id
                    JOIN billing_product p ON s.product_id = p.id
                    GROUP BY p.name
                    ORDER BY cnt DESC
                    LIMIT 5
                """)
                by_service = cur.fetchall()

                # Staff performance
                cur.execute("""
                    SELECT u.email,
                           COUNT(DISTINCT tu.ticket_id) AS tickets_handled,
                           ROUND(AVG(TIMESTAMPDIFF(HOUR, t.created_at, tu.created_at)), 1) AS avg_response_h
                    FROM tickets_ticketupdate tu
                    JOIN core_appuser u ON tu.created_by_id = u.id
                    JOIN tickets_ticket t ON tu.ticket_id = t.id
                    WHERE u.is_staff = 1
                    GROUP BY u.email
                    ORDER BY tickets_handled DESC
                """)
                staff_rows = cur.fetchall()

            # Word frequency in titles
            stopwords = {"the", "a", "an", "and", "or", "is", "in", "on", "to", "for",
                         "of", "with", "not", "can", "my", "i", "it", "be", "at"}
            from collections import Counter
            import re
            words = Counter()
            for title in titles:
                for word in re.findall(r'\b[a-zа-яіїє]{4,}\b', title):
                    if word not in stopwords:
                        words[word] += 1
            top_words = words.most_common(10)

            lines = [f"Ticket Trends (by {period})", "=" * 30]

            if trend_rows:
                lines.append(f"\nTickets per {period}:")
                max_cnt = max(r["cnt"] for r in trend_rows)
                for r in trend_rows:
                    bar = "█" * int(r["cnt"] / max_cnt * 20)
                    lines.append(f"  {r['period']}: {r['cnt']:3d} {bar}")
            else:
                lines.append("No data for selected period.")

            if top_words:
                lines.append("\nTop recurring keywords in ticket titles:")
                for word, cnt in top_words:
                    lines.append(f"  {word}: {cnt}")

            if by_service:
                lines.append("\nServices generating most tickets:")
                for r in by_service:
                    lines.append(f"  {r['product']}: {r['cnt']}")
            else:
                lines.append("\nNo service-linked tickets found.")

            if staff_rows:
                lines.append("\nStaff activity:")
                for r in staff_rows:
                    lines.append(
                        f"  {r['email']}: {r['tickets_handled']} tickets handled, "
                        f"avg response {r['avg_response_h']}h"
                    )

            return "\n".join(lines)


def get_fleio_support_tools() -> list:
    return [
        FleioTicketSummaryTool(),
        FleioListTicketsTool(),
        FleioGetTicketTool(),
        FleioClientTicketsTool(),
        FleioSlaReportTool(),
        FleioTrendsTool(),
    ]
