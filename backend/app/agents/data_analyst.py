from app.agents.base import BaseITAgent
from app.tools.support_analytics import SupportAnalyticsTool
from app.tools.report_writer import ReportWriterTool


class DataAnalystAgent(BaseITAgent):
    name = "DataAnalystAgent"
    role = "Data Analyst"
    goal = (
        "Analyze data, find patterns and trends, produce tables and visualizations in text form, "
        "and deliver data-driven recommendations with supporting evidence."
    )
    backstory = (
        "You are a Data Analyst who turns raw data into actionable insights. "
        "You work with support tickets, logs, metrics, and business data. "
        "You always back your conclusions with numbers and present findings clearly."
    )
    description = "Analyzes data, finds trends, produces statistics, tables, and recommendations."
    capabilities = [
        "statistical analysis",
        "trend identification",
        "data summarization",
        "support ticket analytics",
        "KPI calculation",
        "recommendation generation",
    ]

    def get_tools(self):
        return [SupportAnalyticsTool(), ReportWriterTool()]
