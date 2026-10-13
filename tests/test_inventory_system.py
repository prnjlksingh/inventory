from datetime import date
import unittest

from inventory_system import DepartmentInventorySystem, InventoryError


class DepartmentInventorySystemTests(unittest.TestCase):
    def setUp(self) -> None:
        self.system = DepartmentInventorySystem()
        self.system.register_student(
            name="Alice",
            enrolment_number="ENR-001",
            programme="M.Sc. DFIS",
            semester="I",
            contact_details="alice@example.com",
        )
        self.system.add_inventory_item(
            code="USB-CBL",
            name="USB Cable",
            category="Cable",
            description="Reusable cable",
            make_model="Type-C",
            total_quantity=20,
            tracking_type="quantity",
        )
        self.system.add_inventory_item(
            code="DB",
            name="Development Board",
            category="Board",
            description="Lab board",
            make_model="DB-Model",
            total_quantity=10,
            tracking_type="asset",
        )
        for index in range(1, 11):
            self.system.add_asset(
                asset_id=f"DB-{index:03d}",
                item_code="DB",
                serial_number=f"SER-{index:03d}",
                location="Lab A",
            )

    def test_due_date_auto_set_to_15_days(self) -> None:
        issue = self.system.issue_item(
            student_enrolment="ENR-001",
            item_code="USB-CBL",
            quantity=2,
            purpose="Lab work",
            issuing_staff="coord",
            issue_date=date(2026, 10, 1),
        )
        self.assertEqual(issue.due_date, date(2026, 10, 16))

    def test_quantity_issue_reduces_available_and_blocks_excess(self) -> None:
        self.system.issue_item(
            student_enrolment="ENR-001",
            item_code="USB-CBL",
            quantity=2,
            purpose="Lab work",
            issuing_staff="coord",
            issue_date=date(2026, 10, 1),
        )
        self.assertEqual(self.system.get_available_quantity("USB-CBL"), 18)

        with self.assertRaises(InventoryError):
            self.system.issue_item(
                student_enrolment="ENR-001",
                item_code="USB-CBL",
                quantity=25,
                purpose="Lab work",
                issuing_staff="coord",
                issue_date=date(2026, 10, 1),
            )
        self.assertEqual(self.system.get_available_quantity("USB-CBL"), 18)

    def test_asset_cannot_be_issued_twice(self) -> None:
        self.system.issue_item(
            student_enrolment="ENR-001",
            item_code="DB",
            quantity=1,
            asset_id="DB-001",
            purpose="Lab work",
            issuing_staff="coord",
            issue_date=date(2026, 10, 1),
        )

        with self.assertRaises(InventoryError):
            self.system.issue_item(
                student_enrolment="ENR-001",
                item_code="DB",
                quantity=1,
                asset_id="DB-001",
                purpose="Lab work",
                issuing_staff="coord",
                issue_date=date(2026, 10, 2),
            )

    def test_partial_return_keeps_outstanding(self) -> None:
        issue = self.system.issue_item(
            student_enrolment="ENR-001",
            item_code="USB-CBL",
            quantity=3,
            purpose="Lab work",
            issuing_staff="coord",
            issue_date=date(2026, 10, 1),
        )

        self.system.record_return(
            issue_id=issue.issue_id,
            quantity_returned=1,
            condition_on_return="usable",
            receiving_staff="coord",
            return_date=date(2026, 10, 5),
        )

        refreshed_issue = self.system.issues[issue.issue_id]
        self.assertEqual(refreshed_issue.outstanding_quantity, 2)
        self.assertEqual(self.system.get_available_quantity("USB-CBL"), 18)

    def test_renewal_request_does_not_change_due_date_until_approved(self) -> None:
        issue = self.system.issue_item(
            student_enrolment="ENR-001",
            item_code="USB-CBL",
            quantity=1,
            purpose="Lab work",
            issuing_staff="coord",
            issue_date=date(2026, 10, 1),
        )

        self.system.request_renewal(
            issue_id=issue.issue_id,
            request_date=date(2026, 10, 10),
            requested_by="ENR-001",
        )
        self.assertEqual(self.system.issues[issue.issue_id].due_date, date(2026, 10, 16))

        self.system.review_renewal(
            issue_id=issue.issue_id,
            approval_status="approved",
            approval_date=date(2026, 10, 11),
            approving_staff="coord",
        )
        self.assertEqual(self.system.issues[issue.issue_id].due_date, date(2026, 10, 31))

    def test_overdue_and_upcoming_lists(self) -> None:
        issue = self.system.issue_item(
            student_enrolment="ENR-001",
            item_code="USB-CBL",
            quantity=1,
            purpose="Lab work",
            issuing_staff="coord",
            issue_date=date(2026, 10, 1),
        )

        upcoming = self.system.get_upcoming_due_items(as_of_date=date(2026, 10, 14), within_days=3)
        self.assertEqual(len(upcoming), 1)
        self.assertEqual(upcoming[0]["issue_id"], issue.issue_id)

        overdue = self.system.get_overdue_items(as_of_date=date(2026, 10, 19))
        self.assertEqual(len(overdue), 1)
        self.assertEqual(overdue[0]["overdue_days"], 3)


if __name__ == "__main__":
    unittest.main()
