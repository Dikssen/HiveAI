"""
SupportAnalyticsTool — loads and analyzes support tickets from sample_data/support_tickets.json.
"""
import json
import os
from collections import Counter
from pydantic import BaseModel, Field

from app.tools.base import LoggedTool
from app.config import settings


class SupportAnalyticsInput(BaseModel):
    analysis_type: str = Field(
        default="summary",
        description=(
            "Type of analysis: 'summary' for overview, "
            "'by_category' for category breakdown, "
            "'by_status' for status breakdown, "
            "'top_issues' for most common problems"
        ),
    )


class SupportAnalyticsTool(LoggedTool):
    name: str = "SupportAnalytics"
    description: str = (
        "Analyze support ticket data. "
        "Provides statistics, category breakdowns, and top issues. "
        "analysis_type options: summary, by_category, by_status, top_issues"
    )
    args_schema: type[BaseModel] = SupportAnalyticsInput

    def _run(self, analysis_type: str = "summary") -> str:
        file_path = os.path.join(settings.SAMPLE_DATA_PATH, "support_tickets.json")

        if not os.path.exists(file_path):
            return "support_tickets.json not found in sample_data/."

        with open(file_path, "r") as f:
            data = json.load(f)

        tickets = data.get("tickets", data) if isinstance(data, dict) else data

        if not tickets:
            return "No tickets found in support_tickets.json."

        total = len(tickets)

        if analysis_type == "summary":
            statuses = Counter(t.get("status", "unknown") for t in tickets)
            categories = Counter(t.get("category", "unknown") for t in tickets)
            priorities = Counter(t.get("priority", "unknown") for t in tickets)
            return (
                f"Support Tickets Summary\n"
                f"=======================\n"
                f"Total tickets: {total}\n\n"
                f"By Status:\n" + "\n".join(f"  {k}: {v}" for k, v in statuses.items()) + "\n\n"
                f"By Category:\n" + "\n".join(f"  {k}: {v}" for k, v in categories.items()) + "\n\n"
                f"By Priority:\n" + "\n".join(f"  {k}: {v}" for k, v in priorities.items())
            )

        elif analysis_type == "by_category":
            categories: dict[str, list] = {}
            for t in tickets:
                cat = t.get("category", "unknown")
                categories.setdefault(cat, []).append(t)
            lines = [f"Tickets by Category ({total} total):\n"]
            for cat, items in sorted(categories.items(), key=lambda x: -len(x[1])):
                lines.append(f"\n{cat} ({len(items)} tickets):")
                for t in items[:3]:
                    lines.append(f"  - [{t.get('id')}] {t.get('subject', t.get('title', 'N/A'))}")
                if len(items) > 3:
                    lines.append(f"  ... and {len(items) - 3} more")
            return "\n".join(lines)

        elif analysis_type == "by_status":
            statuses: dict[str, list] = {}
            for t in tickets:
                st = t.get("status", "unknown")
                statuses.setdefault(st, []).append(t)
            lines = [f"Tickets by Status ({total} total):\n"]
            for st, items in statuses.items():
                lines.append(f"\n{st}: {len(items)} tickets")
            return "\n".join(lines)

        elif analysis_type == "top_issues":
            subjects = Counter(
                t.get("subject", t.get("title", "N/A")) for t in tickets
            ).most_common(10)
            lines = [f"Top 10 Most Common Issues:\n"]
            for i, (subject, count) in enumerate(subjects, 1):
                lines.append(f"  {i}. {subject} ({count} tickets)")
            return "\n".join(lines)

        return f"Unknown analysis_type: {analysis_type}. Use: summary, by_category, by_status, top_issues"
