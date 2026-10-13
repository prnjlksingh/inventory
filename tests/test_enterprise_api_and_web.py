import json
import unittest

from app import create_app


class EnterpriseApiAndWebTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test-secret"})
        self.client = self.app.test_client()
        self.system = self.app.config["INVENTORY_SYSTEM"]

    def test_enterprise_page_renders(self) -> None:
        routes = [
            "/",
            "/inventory",
            "/students",
            "/transactions",
            "/due",
            "/history",
            "/kits",
            "/kits/new",
            "/reservations",
            "/reservations/new",
            "/maintenance",
            "/maintenance/new",
            "/analytics",
            "/labels",
            "/api/docs",
            "/api/openapi.json",
            "/assets/css/bundle.css",
            "/assets/img/NFSU_logo.png",
            "/assets/img/banner/12.jpg",
            "/assets/img/preloader.gif",
            "/favicon.ico",
        ]
        for path in routes:
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200, msg=f"Failed on route {path}")

    def test_csv_exports(self) -> None:
        export_routes = [
            ("/export/inventory.csv", "attachment;filename=inventory_report.csv"),
            ("/export/transactions.csv", "attachment;filename=transaction_audit_trail.csv"),
            ("/export/overdue.csv", "attachment;filename=overdue_equipment.csv"),
        ]
        for route, expected_disposition in export_routes:
            res = self.client.get(route)
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.mimetype, "text/csv")
            self.assertIn(expected_disposition, res.headers.get("Content-Disposition", ""))
            self.assertTrue(len(res.data) > 0)

    def test_custody_receipt_rendering(self) -> None:
        first_issue = list(self.system.issues.values())[0]
        res = self.client.get(f"/issues/{first_issue.issue_id}/receipt")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Official Custody", res.data)
        self.assertIn(first_issue.issue_id.encode("utf-8"), res.data)

    def test_rest_api_health_and_metrics(self) -> None:
        health_res = self.client.get("/api/v1/health")
        self.assertEqual(health_res.status_code, 200)
        self.assertEqual(health_res.json["status"], "healthy")

        metrics_res = self.client.get("/api/v1/metrics")
        self.assertEqual(metrics_res.status_code, 200)
        self.assertIn("utilization_rate", metrics_res.json)

    def test_rest_api_items_crud(self) -> None:
        # Create item via API
        create_res = self.client.post(
            "/api/v1/items",
            data=json.dumps({
                "code": "API-TEST-SKU",
                "name": "API Sensor",
                "category": "Sensor",
                "description": "Temperature probe",
                "make_model": "DS18B20",
                "total_quantity": 25,
                "tracking_type": "quantity",
            }),
            content_type="application/json",
        )
        self.assertEqual(create_res.status_code, 201)

        # Get item
        get_res = self.client.get("/api/v1/items/API-TEST-SKU")
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.json["name"], "API Sensor")
        self.assertEqual(get_res.json["status"]["total"], 25)

    def test_rest_api_checkout_and_checkin(self) -> None:
        # Checkout via API
        checkout_res = self.client.post(
            "/api/v1/checkout",
            data=json.dumps({
                "student_enrolment": "ENR-001",
                "item_code": "HDMI-CBL",
                "quantity": 2,
                "purpose": "REST API Integration Test",
                "issuing_staff": "Automated Test",
            }),
            content_type="application/json",
        )
        self.assertEqual(checkout_res.status_code, 201)
        issue_id = checkout_res.json["issue_id"]

        # Checkin via API
        checkin_res = self.client.post(
            "/api/v1/checkin",
            data=json.dumps({
                "issue_id": issue_id,
                "quantity_returned": 2,
                "condition_on_return": "usable",
                "receiving_staff": "Automated Test",
            }),
            content_type="application/json",
        )
        self.assertEqual(checkin_res.status_code, 200)
        self.assertEqual(checkin_res.json["remaining_outstanding"], 0)

    def test_rest_api_kits_and_reservations(self) -> None:
        # Check kits list
        kits_res = self.client.get("/api/v1/kits")
        self.assertEqual(kits_res.status_code, 200)
        self.assertTrue(kits_res.json["count"] >= 1)

        # Check reservations list
        res_list = self.client.get("/api/v1/reservations")
        self.assertEqual(res_list.status_code, 200)
        self.assertTrue(res_list.json["count"] >= 1)

    def test_barcode_and_qr_api_endpoints(self) -> None:
        barcode_res = self.client.get("/api/v1/barcode/DSLR-001")
        self.assertEqual(barcode_res.status_code, 200)
        self.assertEqual(barcode_res.mimetype, "image/svg+xml")

        qr_res = self.client.get("/api/v1/qr/DSLR-001")
        self.assertEqual(qr_res.status_code, 200)
        self.assertEqual(qr_res.mimetype, "image/svg+xml")

    def test_instant_search_api(self) -> None:
        search_res = self.client.get("/api/v1/search?q=DSLR")
        self.assertEqual(search_res.status_code, 200)
        self.assertTrue(len(search_res.json["items"]) > 0 or len(search_res.json["assets"]) > 0)


if __name__ == "__main__":
    unittest.main()
