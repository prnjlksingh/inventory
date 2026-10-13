from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, Optional

from flask import Flask, flash, redirect, render_template, request, url_for

from inventory_system import DepartmentInventorySystem, InventoryError


METRIC_KEYS = ("total", "available", "issued", "overdue", "damaged", "lost")


def seed_demo_data(system: DepartmentInventorySystem) -> None:
    students = [
        ("Aarav Mehta", "ENR-001", "B.Tech CSE", "V", "aarav@example.com"),
        ("Naina Roy", "ENR-002", "B.Tech ECE", "VII", "naina@example.com"),
        ("Riya Sharma", "ENR-003", "M.Sc. Data Science", "III", "riya@example.com"),
        ("Kabir Jain", "ENR-004", "BCA", "II", "kabir@example.com"),
    ]
    for student in students:
        system.register_student(*student)

    items = [
        ("HDMI-CBL", "HDMI Cable", "Cable", "High-speed HDMI cable", "HDMI 2.1", 30, "quantity"),
        ("LAP-BAG", "Laptop Bag", "Accessory", "Padded laptop bag", "14-inch", 12, "quantity"),
        ("CAL-KIT", "Calculator Kit", "Kit", "Engineering calculator kit", "FX-991 + tools", 18, "quantity"),
        ("DSLR", "DSLR Camera", "Camera", "Lab camera for media projects", "Canon EOS", 3, "asset"),
    ]
    for item in items:
        system.add_inventory_item(*item)

    for index in range(1, 4):
        system.add_asset(
            asset_id=f"DSLR-{index:03d}",
            item_code="DSLR",
            serial_number=f"CAM-SN-{index:03d}",
            location="Media Lab",
        )

    today = date.today()
    overdue_issue = system.issue_item(
        student_enrolment="ENR-001",
        item_code="HDMI-CBL",
        quantity=4,
        purpose="Workshop setup",
        issuing_staff="Coordinator",
        issue_date=today - timedelta(days=20),
    )
    system.record_return(
        issue_id=overdue_issue.issue_id,
        quantity_returned=1,
        condition_on_return="usable",
        receiving_staff="Coordinator",
        return_date=today - timedelta(days=12),
    )

    upcoming_issue = system.issue_item(
        student_enrolment="ENR-002",
        item_code="LAP-BAG",
        quantity=2,
        purpose="Field visit",
        issuing_staff="Lab Assistant",
        issue_date=today - timedelta(days=13),
    )

    damaged_issue = system.issue_item(
        student_enrolment="ENR-004",
        item_code="CAL-KIT",
        quantity=2,
        purpose="Exam support",
        issuing_staff="Lab Assistant",
        issue_date=today - timedelta(days=18),
    )
    system.record_return(
        issue_id=damaged_issue.issue_id,
        quantity_returned=1,
        condition_on_return="damaged",
        receiving_staff="Lab Assistant",
        return_date=today - timedelta(days=10),
    )

    lost_issue = system.issue_item(
        student_enrolment="ENR-003",
        item_code="CAL-KIT",
        quantity=1,
        purpose="Case study",
        issuing_staff="Coordinator",
        issue_date=today - timedelta(days=17),
    )
    system.record_return(
        issue_id=lost_issue.issue_id,
        quantity_returned=1,
        condition_on_return="lost",
        receiving_staff="Coordinator",
        return_date=today - timedelta(days=8),
    )

    system.issue_item(
        student_enrolment="ENR-003",
        item_code="DSLR",
        quantity=1,
        asset_id="DSLR-001",
        purpose="Photography club",
        issuing_staff="Media Incharge",
        issue_date=today - timedelta(days=2),
    )

    _ = upcoming_issue


def create_app(test_config: Optional[Dict[str, object]] = None) -> Flask:
    app = Flask(__name__)
    app.config.update(SECRET_KEY="inventory-mvp-secret")
    if test_config:
        app.config.update(test_config)

    system = DepartmentInventorySystem()
    seed_demo_data(system)
    app.config["INVENTORY_SYSTEM"] = system

    def _system() -> DepartmentInventorySystem:
        return app.config["INVENTORY_SYSTEM"]

    def _parse_date(value: str) -> Optional[date]:
        if not value:
            return None
        return date.fromisoformat(value)

    def _dashboard_metrics() -> Dict[str, int]:
        totals = {key: 0 for key in METRIC_KEYS}
        for item_code in _system().items:
            status = _system().get_inventory_status(item_code)
            for key in METRIC_KEYS:
                totals[key] += status[key]
        return totals

    @app.get("/")
    def dashboard():
        metrics = _dashboard_metrics()
        overdue_items = _system().get_overdue_items()
        upcoming_items = _system().get_upcoming_due_items(within_days=5)
        recent_activity = _system().get_transaction_history()[-8:]
        return render_template(
            "dashboard.html",
            metrics=metrics,
            overdue_items=overdue_items,
            upcoming_items=upcoming_items,
            recent_activity=recent_activity,
        )

    @app.get("/inventory")
    def inventory_list():
        query = request.args.get("q", "").strip().lower()
        category = request.args.get("category", "").strip().lower()
        rows = []
        categories = sorted({item.category for item in _system().items.values()})

        for item in _system().items.values():
            if query and query not in f"{item.code} {item.name}".lower():
                continue
            if category and item.category.lower() != category:
                continue
            status = _system().get_inventory_status(item.code)
            rows.append({"item": item, "status": status})

        return render_template(
            "inventory.html",
            rows=rows,
            query=query,
            category=category,
            categories=categories,
        )

    @app.route("/inventory/new", methods=["GET", "POST"])
    def add_inventory_item():
        if request.method == "POST":
            try:
                _system().add_inventory_item(
                    code=request.form["code"].strip(),
                    name=request.form["name"].strip(),
                    category=request.form["category"].strip(),
                    description=request.form["description"].strip(),
                    make_model=request.form["make_model"].strip(),
                    total_quantity=int(request.form["total_quantity"]),
                    tracking_type=request.form["tracking_type"],
                )
                flash("Inventory item added successfully.", "success")
                return redirect(url_for("inventory_list"))
            except (ValueError, InventoryError) as error:
                flash(str(error), "error")
        return render_template("inventory_form.html", item=None)

    @app.route("/inventory/<item_code>/edit", methods=["GET", "POST"])
    def edit_inventory_item(item_code: str):
        item = _system()._require_item(item_code)
        if request.method == "POST":
            try:
                total_quantity = int(request.form["total_quantity"])
                issued = _system().get_issued_quantity(item.code)
                unavailable = item.unavailable_quantity()
                if total_quantity < issued + unavailable:
                    raise InventoryError(
                        f"Total quantity must be at least {issued + unavailable} to preserve issued/unavailable stock."
                    )

                item.name = request.form["name"].strip()
                item.category = request.form["category"].strip()
                item.description = request.form["description"].strip()
                item.make_model = request.form["make_model"].strip()
                item.total_quantity = total_quantity
                _system()._assert_item_stock_consistency(item.code)
                flash("Inventory item updated successfully.", "success")
                return redirect(url_for("inventory_list"))
            except (ValueError, InventoryError) as error:
                flash(str(error), "error")

        return render_template("inventory_form.html", item=item)

    @app.get("/students")
    def students_list():
        students = sorted(_system().students.values(), key=lambda student: student.enrolment_number)
        return render_template("students.html", students=students)

    @app.get("/students/<enrolment>")
    def student_detail(enrolment: str):
        student = _system().students.get(enrolment)
        if not student:
            flash("Student not found.", "error")
            return redirect(url_for("students_list"))
        records = _system().get_student_records(enrolment)
        outstanding = [record for record in records if record.outstanding_quantity > 0]
        return render_template(
            "student_detail.html",
            student=student,
            records=records,
            outstanding=outstanding,
            today=date.today(),
        )

    @app.route("/transactions", methods=["GET", "POST"])
    def transactions():
        if request.method == "POST":
            action = request.form.get("action")
            try:
                if action == "issue":
                    _system().issue_item(
                        student_enrolment=request.form["student_enrolment"],
                        item_code=request.form["item_code"],
                        quantity=int(request.form["quantity"]),
                        purpose=request.form["purpose"].strip(),
                        issuing_staff=request.form["staff"].strip() or "Inventory Desk",
                        issue_date=_parse_date(request.form.get("issue_date", "")),
                        asset_id=request.form.get("asset_id", "").strip() or None,
                    )
                    flash("Item issued successfully.", "success")
                elif action == "return":
                    _system().record_return(
                        issue_id=request.form["issue_id"],
                        quantity_returned=int(request.form["quantity_returned"]),
                        condition_on_return=request.form["condition_on_return"],
                        receiving_staff=request.form["staff"].strip() or "Inventory Desk",
                        return_date=_parse_date(request.form.get("return_date", "")),
                    )
                    flash("Return recorded successfully.", "success")
                else:
                    flash("Unknown transaction action.", "error")
            except (ValueError, InventoryError) as error:
                flash(str(error), "error")
            return redirect(url_for("transactions"))

        open_issues = [issue for issue in _system().issues.values() if issue.outstanding_quantity > 0]
        open_issues.sort(key=lambda issue: (issue.due_date, issue.issue_id))
        return render_template(
            "transactions.html",
            students=sorted(_system().students.values(), key=lambda student: student.enrolment_number),
            items=sorted(_system().items.values(), key=lambda item: item.code),
            open_issues=open_issues,
            conditions=["usable", "damaged", "lost", "maintenance"],
        )

    @app.get("/due")
    def due_items():
        overdue_items = _system().get_overdue_items()
        upcoming_items = _system().get_upcoming_due_items(within_days=5)
        return render_template("due.html", overdue_items=overdue_items, upcoming_items=upcoming_items)

    @app.get("/history")
    def history():
        events = _system().get_transaction_history()
        return render_template("history.html", events=events)

    return app


app = create_app()


if __name__ == "__main__":
    app.run()
