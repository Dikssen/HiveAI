from app.agents.base import BaseITAgent
from app.tools.support_analytics import SupportAnalyticsTool
from app.tools.read_logs import ReadLogsTool
from app.tools.report_writer import ReportWriterTool


class SupportEngineerAgent(BaseITAgent):
    name = "SupportEngineerAgent"
    role = "Support Engineer"
    goal = (
        "Analyze support requests and tickets, classify issues by category and severity, "
        "identify recurring problems, and produce clear summaries for the team."
    )
    backstory = (
        "You are a Support Engineer who is the first line of defense between users and the product. "
        "You have seen every type of support ticket, know how to classify issues quickly, "
        "and can spot when a single ticket represents a bigger systemic problem."
    )
    description = "Analyzes support tickets, classifies issues, identifies trends, prepares summaries."
    capabilities = [
        "support ticket classification",
        "issue triage",
        "support trend analysis",
        "SLA compliance checking",
        "escalation identification",
        "support summary writing",
    ]

    def get_tools(self):
        return [SupportAnalyticsTool(), ReadLogsTool(), ReportWriterTool()]
