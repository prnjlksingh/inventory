from datetime import date, timedelta
import os
import tempfile
import unittest

from barcode_utils import generate_code128_svg, generate_qr_svg
from inventory_system import (
    DepartmentInventorySystem,
    InventoryError,
    KitValidationError,
    MaintenanceValidationError,
    ReservationValidationError,
)


class EnterpriseFeaturesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.system = DepartmentInventorySystem()
        # Seed students
        self.system.register_student(
            name="Alice Walker",
            enrolment_number="STU-001",
            programme="Computer Science",
            semester="IV",
            contact_details="alice@campus.edu",
        )
        self.system.register_student(
            name="Bob Martin",
            enrolment_number="STU-002",
            programme="Media Arts",
            semester="VI",
            contact_details="bob@campus.edu",
        )
        # Seed items
        self.system.add_inventory_item(
            code="CAM-A7",
            name="Sony A7 IV Camera",
            category="Camera",
            description="Full-frame 4K mirrorless",
            make_model="Sony Alpha",
            total_quantity=3,
            tracking_type="asset",
        )
        for i in range(1, 4):
            self.system.add_asset(
                asset_id=f"CAM-A7-{i:03d}",
                item_code="CAM-A7",
                serial_number=f"SN-A7-{i:03d}",
                location="Media Cage",
            )
        self.system.add_inventory_item(
            code="MIC-RODE",
            name="Rode Wireless Pro",
            category="Audio",
            description="Wireless lavalier system",
            make_model="Rode Pro",
            total_quantity=5,
            tracking_type="quantity",
        )
        self.system.add_inventory_item(
            code="TRI-MAN",
            name="Manfrotto Tripod",
            category="Grip",
            description="Carbon fiber tripod",
            make_model="055XPRO3",
            total_quantity=4,
            tracking_type="quantity",
        )

    def test_kit_creation_and_atomic_issue(self) -> None:
        kit = self.system.add_kit(
            kit_id="KIT-FILM",
            name="Filmmaker Starter Kit",
            category="Production",
            description="Complete camera and audio package",
            items=[
                {"item_code": "CAM-A7", "quantity": 1},
                {"item_code": "MIC-RODE", "quantity": 1},
                {"item_code": "TRI-MAN", "quantity": 1},
            ],
        )
        self.assertEqual(kit.name, "Filmmaker Starter Kit")
        self.assertTrue(self.system.is_kit_available("KIT-FILM"))

        # Issue kit
        issues = self.system.issue_kit(
            kit_id="KIT-FILM",
            student_enrolment="STU-001",
            purpose="Short film project",
            issuing_staff="Instructor Mark",
        )
        self.assertEqual(len(issues), 3)
        self.assertEqual(self.system.get_available_quantity("CAM-A7"), 2)
        self.assertEqual(self.system.get_available_quantity("MIC-RODE"), 4)
        self.assertEqual(self.system.get_available_quantity("TRI-MAN"), 3)

    def test_kit_validation_blocks_when_insufficient_stock(self) -> None:
        self.system.add_kit(
            kit_id="KIT-HEAVY",
            name="Broadcasting Studio Kit",
            category="Production",
            description="Multi-mic package",
            items=[{"item_code": "MIC-RODE", "quantity": 10}],  # Only 5 exist
        )
        self.assertFalse(self.system.is_kit_available("KIT-HEAVY"))
        with self.assertRaises(KitValidationError):
            self.system.issue_kit(
                kit_id="KIT-HEAVY",
                student_enrolment="STU-001",
                purpose="Podcast",
                issuing_staff="Staff",
            )

    def test_reservation_lifecycle(self) -> None:
        tomorrow = date.today() + timedelta(days=1)
        next_week = date.today() + timedelta(days=7)

        res = self.system.create_reservation(
            student_enrolment="STU-002",
            item_code="MIC-RODE",
            quantity=2,
            start_date=tomorrow,
            end_date=next_week,
            purpose="Documentary recording",
        )
        self.assertEqual(res.status, "approved")

        # Fulfill reservation into an active checkout
        initial_avail = self.system.get_available_quantity("MIC-RODE")
        issue = self.system.fulfill_reservation(res.reservation_id, issuing_staff="Desk Agent")
        self.assertEqual(res.status, "fulfilled")
        self.assertEqual(issue.student_enrolment, "STU-002")
        self.assertEqual(self.system.get_available_quantity("MIC-RODE"), initial_avail - 2)

    def test_maintenance_workflow_for_asset_and_quantity(self) -> None:
        # Asset maintenance
        rec = self.system.create_maintenance_record(
            item_code="CAM-A7",
            asset_id="CAM-A7-001",
            title="Sensor Cleaning & Calibration",
            issue_description="Dust speck visible at f/8",
            technician="Sony Pro Service",
            cost=85.0,
        )
        self.assertEqual(rec.status, "open")
        self.assertEqual(self.system.assets["CAM-A7-001"].condition, "maintenance")
        self.assertFalse(self.system.assets["CAM-A7-001"].is_issuable)

        # Complete maintenance
        completed_rec = self.system.complete_maintenance_record(
            record_id=rec.record_id,
            resolution_condition="usable",
            notes="Cleaned and firmware updated",
        )
        self.assertEqual(completed_rec.status, "completed")
        self.assertEqual(self.system.assets["CAM-A7-001"].condition, "usable")
        self.assertTrue(self.system.assets["CAM-A7-001"].is_issuable)

    def test_sqlite_persistence_roundtrip(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            db_file = tf.name

        try:
            persisted_system = DepartmentInventorySystem(db_path=db_file)
            persisted_system.register_student(
                name="David Hall",
                enrolment_number="STU-PERSIST",
                programme="Robotics",
                semester="I",
                contact_details="david@campus.edu",
            )
            persisted_system.add_inventory_item(
                code="ARD-UNO",
                name="Arduino Uno R4",
                category="Microcontroller",
                description="MCU Dev board",
                make_model="Rev4 WiFi",
                total_quantity=15,
                tracking_type="quantity",
            )
            persisted_system.issue_item(
                student_enrolment="STU-PERSIST",
                item_code="ARD-UNO",
                quantity=3,
                purpose="IoT Lab",
                issuing_staff="Lab Tech",
            )

            # Re-instantiate from the same SQLite file
            reloaded_system = DepartmentInventorySystem(db_path=db_file)
            self.assertIn("STU-PERSIST", reloaded_system.students)
            self.assertIn("ARD-UNO", reloaded_system.items)
            self.assertEqual(reloaded_system.get_available_quantity("ARD-UNO"), 12)
            self.assertEqual(reloaded_system.get_issued_quantity("ARD-UNO"), 3)
        finally:
            if os.path.exists(db_file):
                try:
                    os.remove(db_file)
                except OSError:
                    pass

    def test_analytics_and_search(self) -> None:
        analytics = self.system.get_analytics_summary()
        self.assertIn("utilization_rate", analytics)
        self.assertIn("category_distribution", analytics)
        self.assertEqual(analytics["total_units"], 12)

        results = self.system.search_everything("Sony")
        self.assertTrue(len(results["items"]) > 0 or len(results["assets"]) > 0)

    def test_barcode_and_qr_generation(self) -> None:
        code128_svg = generate_code128_svg("CAM-A7-001")
        self.assertIn("<svg", code128_svg)
        self.assertIn("CAM-A7-001", code128_svg)

        qr_svg = generate_qr_svg("CAM-A7-001")
        self.assertIn("<svg", qr_svg)


if __name__ == "__main__":
    unittest.main()
