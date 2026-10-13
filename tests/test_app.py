from datetime import date
import unittest

from app import create_app


class InventoryMvpAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test-secret"})
        self.client = self.app.test_client()
        self.system = self.app.config["INVENTORY_SYSTEM"]

    def test_core_pages_render(self) -> None:
        for path in ["/", "/inventory", "/students", "/transactions", "/due", "/history"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, msg=f"Expected 200 for {path}")

    def test_issue_and_return_workflow_updates_stock_and_history(self) -> None:
        available_before = self.system.get_available_quantity("HDMI-CBL")

        issue_response = self.client.post(
            "/transactions",
            data={
                "action": "issue",
                "student_enrolment": "ENR-002",
                "item_code": "HDMI-CBL",
                "quantity": "2",
                "purpose": "Hackathon demo",
                "staff": "Desk",
                "issue_date": date.today().isoformat(),
                "asset_id": "",
            },
            follow_redirects=True,
        )
        self.assertEqual(issue_response.status_code, 200)
        self.assertIn(b"Item issued successfully.", issue_response.data)

        new_issue = max(self.system.issues.values(), key=lambda issue: issue.issue_id)
        self.assertEqual(new_issue.item_code, "HDMI-CBL")
        self.assertEqual(self.system.get_available_quantity("HDMI-CBL"), available_before - 2)

        return_response = self.client.post(
            "/transactions",
            data={
                "action": "return",
                "issue_id": new_issue.issue_id,
                "quantity_returned": "1",
                "condition_on_return": "usable",
                "staff": "Desk",
                "return_date": date.today().isoformat(),
            },
            follow_redirects=True,
        )
        self.assertEqual(return_response.status_code, 200)
        self.assertIn(b"Return recorded successfully.", return_response.data)
        self.assertEqual(self.system.issues[new_issue.issue_id].outstanding_quantity, 1)

    def test_issue_validation_error_when_requesting_unavailable_stock(self) -> None:
        response = self.client.post(
            "/transactions",
            data={
                "action": "issue",
                "student_enrolment": "ENR-001",
                "item_code": "HDMI-CBL",
                "quantity": "9999",
                "purpose": "Too much",
                "staff": "Desk",
                "issue_date": date.today().isoformat(),
                "asset_id": "",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"currently available", response.data)


if __name__ == "__main__":
    unittest.main()
