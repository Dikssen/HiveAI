from app.agents.base import BaseITAgent
from app.tools.code_review import CodeReviewTool
from app.tools.report_writer import ReportWriterTool


class QAEngineerAgent(BaseITAgent):
    name = "QAEngineerAgent"
    role = "QA Engineer"
    goal = (
        "Verify proposed solutions, identify test cases, describe edge cases, "
        "assess risks, and ensure that changes won't break existing functionality."
    )
    backstory = (
        "You are a thorough QA Engineer who catches bugs before they reach production. "
        "You think in edge cases, write test scenarios, and evaluate the quality and "
        "completeness of any proposed solution or change."
    )
    description = "Reviews solutions, creates test cases, identifies risks, assesses quality."
    capabilities = [
        "test case design",
        "edge case identification",
        "risk assessment",
        "solution verification",
        "regression risk analysis",
        "acceptance criteria writing",
    ]

    def get_tools(self):
        return [CodeReviewTool(), ReportWriterTool()]
