from __future__ import annotations

import csv
from datetime import date, timedelta
import io
import json
from typing import Dict, Optional

import os
from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

from api_v1 import api_bp
from barcode_utils import generate_code128_svg, generate_qr_svg, svg_to_data_uri
from inventory_system import (
    DepartmentInventorySystem,
    InventoryError,
    KitValidationError,
    MaintenanceValidationError,
    ReservationValidationError,
)

METRIC_KEYS = ("total", "available", "issued", "overdue", "damaged", "lost")


def seed_demo_data(system: DepartmentInventorySystem) -> None:
    if len(system.items) > 0:
        return  # already seeded or hydrated from database

    students = [
        ("Aarav Mehta", "ENR-001", "M.Sc. Digital Forensics & Info Security (SCSDF)", "III", "aarav.dfis@nfsu.ac.in"),
        ("Naina Roy", "ENR-002", "M.Sc. Forensic Science (SFS)", "II", "naina.fs@nfsu.ac.in"),
        ("Riya Sharma", "ENR-003", "M.Tech Cyber Security (SCSDF)", "IV", "riya.cs@nfsu.ac.in"),
        ("Kabir Jain", "ENR-004", "B.Tech-M.Tech CSE Cyber Security (SET)", "VI", "kabir.cse@nfsu.ac.in"),
        ("Devika Sen", "ENR-005", "M.Sc. Behavioral Forensics (SBF)", "II", "devika.bf@nfsu.ac.in"),
    ]
    for student in students:
        system.register_student(*student)

    items = [
        ("HDMI-CBL", "Forensic High-Speed Video Cable", "Forensic Hardware", "Ultra-shielded 4K 60Hz forensic display & monitor cable", "HDMI 2.1 Ultra-Shield", 30, "quantity"),
        ("LAP-BAG", "RF Faraday Signal-Shielded Evidence Bag", "Evidence Enclosures", "Faraday cage RF signal blocking padded laptop seizure bag", "Disklabs RF-14", 12, "quantity"),
        ("CAL-KIT", "Forensic Trajectory & Calibration Kit", "Ballistics & Laser", "Trajectory laser rods, calibration gauge, and angle scale", "Forensic-Calib FX", 18, "quantity"),
        ("DSLR", "Crime Scene DSLR Camera Kit", "Forensic Imaging", "4K Crime scene forensic imaging camera with macro ring flash", "Canon EOS R50 Forensic", 4, "asset"),
        ("TABLEAU-T8U", "Tableau T8u USB 3.0 Forensic WriteBlocker", "Hardware WriteBlockers", "Hardware write-blocking bridge for triage & imaging", "Tableau T8u", 8, "quantity"),
        ("CELLEBRITE-UFED", "Cellebrite UFED Mobile Extraction Kit", "Mobile Forensics", "Physical & logical mobile device extraction workstation kit", "UFED Touch 2", 3, "asset"),
        ("MIC-RODE", "Forensic Acoustic Wireless Mic Set", "Audio Forensics", "Dual transmitter lavalier audio recording system", "Rode Wireless GO II", 8, "quantity"),
        ("TRIPOD-PRO", "Pro Forensic Imaging Tripod", "Imaging Grip", "Heavy duty carbon fiber tripod with angle indicator", "Manfrotto 504X", 5, "quantity"),
    ]
    for item in items:
        system.add_inventory_item(*item)

    for index in range(1, 5):
        system.add_asset(
            asset_id=f"DSLR-{index:03d}",
            item_code="DSLR",
            serial_number=f"CAM-SN-{index:03d}",
            location="Digital Forensics Lab - Locker A",
        )

    for index in range(1, 4):
        system.add_asset(
            asset_id=f"UFED-{index:03d}",
            item_code="CELLEBRITE-UFED",
            serial_number=f"UFED-SN-{index:03d}",
            location="Mobile Forensics Lab - Locker B",
        )

    today = date.today()

    # Overdue issue (M.Sc. DFIS Lab research)
    overdue_issue = system.issue_item(
        student_enrolment="ENR-001",
        item_code="HDMI-CBL",
        quantity=4,
        purpose="Digital Forensics Lab Workstation Setup",
        issuing_staff="Dr. V. Sharma (Lab Incharge)",
        issue_date=today - timedelta(days=20),
    )
    system.record_return(
        issue_id=overdue_issue.issue_id,
        quantity_returned=1,
        condition_on_return="usable",
        receiving_staff="Dr. V. Sharma (Lab Incharge)",
        return_date=today - timedelta(days=12),
    )

    # Upcoming issue (Crime Scene Field Visit)
    system.issue_item(
        student_enrolment="ENR-002",
        item_code="LAP-BAG",
        quantity=2,
        purpose="Crime Scene Reconstruction Field Visit",
        issuing_staff="Lab Assistant",
        issue_date=today - timedelta(days=13),
    )

    # Damaged return (Ballistics Practical Support)
    damaged_issue = system.issue_item(
        student_enrolment="ENR-004",
        item_code="CAL-KIT",
        quantity=2,
        purpose="Ballistics Trajectory Practical Examination",
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

    # Lost return
    lost_issue = system.issue_item(
        student_enrolment="ENR-003",
        item_code="CAL-KIT",
        quantity=1,
        purpose="Forensic Crime Simulation Case Study",
        issuing_staff="Store Incharge",
        issue_date=today - timedelta(days=17),
    )
    system.record_return(
        issue_id=lost_issue.issue_id,
        quantity_returned=1,
        condition_on_return="lost",
        receiving_staff="Store Incharge",
        return_date=today - timedelta(days=8),
    )

    # Active asset issue (Forensic Photography)
    system.issue_item(
        student_enrolment="ENR-003",
        item_code="DSLR",
        quantity=1,
        asset_id="DSLR-001",
        purpose="Forensic Photography & Macro Evidence Capture",
        issuing_staff="Digital Forensics Lab Tech",
        issue_date=today - timedelta(days=2),
    )

    # Register Cyber Crime Scene Evidence Seizure Kit
    system.add_kit(
        kit_id="KIT-CSI-01",
        name="Cyber Crime Scene Evidence Seizure Kit",
        category="Digital Forensics",
        description="Official field seizure package: WriteBlocker + Faraday Bag + Crime Scene DSLR + Forensic Cables",
        items=[
            {"item_code": "DSLR", "quantity": 1},
            {"item_code": "TABLEAU-T8U", "quantity": 1},
            {"item_code": "LAP-BAG", "quantity": 1},
            {"item_code": "HDMI-CBL", "quantity": 2},
        ],
    )

    # Upcoming reservation
    system.create_reservation(
        student_enrolment="ENR-005",
        item_code="MIC-RODE",
        quantity=2,
        start_date=today + timedelta(days=2),
        end_date=today + timedelta(days=5),
        purpose="Behavioral Forensics Acoustic Voice Stress Analysis",
        notes="Calibrated microphone needed for BEOS/Polygraph chamber",
    )

    # Maintenance record
    system.create_maintenance_record(
        item_code="DSLR",
        asset_id="DSLR-002",
        title="Macro Ring Flash Sync & Sensor Decontamination",
        issue_description="Dust speck observed during high-resolution latent print capture",
        technician="Canon Authorized Precision Lab",
        cost=120.0,
        started_date=today - timedelta(days=1),
    )


def create_app(test_config: Optional[Dict[str, object]] = None) -> Flask:
    app = Flask(__name__)
    app.config.update(SECRET_KEY="inventory-mvp-secret")
    if test_config:
        app.config.update(test_config)

    # In testing mode or when explicit in test_config, use in-memory; otherwise persist to inventory.db
    is_testing = app.config.get("TESTING", False)
    db_path = app.config.get("DATABASE_PATH")
    if not db_path and not is_testing:
        db_path = "inventory.db"

    system = DepartmentInventorySystem(db_path=db_path)
    seed_demo_data(system)
    app.config["INVENTORY_SYSTEM"] = system

    # Register Enterprise REST API v1
    app.register_blueprint(api_bp)

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

    @app.context_processor
    def inject_global_data():
        return {
            "all_categories": sorted({item.category for item in _system().items.values()}),
            "current_year": date.today().year,
        }

    @app.route("/assets/<path:path>")
    def nfsu_assets(path):
        return send_from_directory(os.path.join(app.root_path, "static", "assets"), path)

    @app.route("/favicon.ico")
    def favicon():
        return send_from_directory(os.path.join(app.root_path, "static"), "nfsu_logo.png")

    # ==========================================
    # CORE DASHBOARD & INVENTORY
    # ==========================================

    @app.get("/")
    def dashboard():
        metrics = _dashboard_metrics()
        overdue_items = _system().get_overdue_items()
        upcoming_items = _system().get_upcoming_due_items(within_days=5)
        recent_activity = _system().get_transaction_history()[-8:]
        analytics = _system().get_analytics_summary()
        active_reservations = _system().get_reservations()[:4]
        open_maintenance = _system().get_maintenance_records(status="open")[:3]

        return render_template(
            "dashboard.html",
            metrics=metrics,
            overdue_items=overdue_items,
            upcoming_items=upcoming_items,
            recent_activity=recent_activity,
            analytics=analytics,
            active_reservations=active_reservations,
            open_maintenance=open_maintenance,
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
                _system()._persist()
                flash("Inventory item updated successfully.", "success")
                return redirect(url_for("inventory_list"))
            except (ValueError, InventoryError) as error:
                flash(str(error), "error")

        return render_template("inventory_form.html", item=item)

    @app.route("/inventory/<item_code>/assets/new", methods=["POST"])
    def add_asset_to_item(item_code: str):
        try:
            asset_id = request.form["asset_id"].strip()
            serial_number = request.form["serial_number"].strip()
            location = request.form.get("location", "Main Storage").strip()
            _system().add_asset(
                asset_id=asset_id,
                item_code=item_code,
                serial_number=serial_number,
                location=location,
            )
            flash(f"Asset {asset_id} registered successfully.", "success")
        except (ValueError, InventoryError) as err:
            flash(str(err), "error")
        return redirect(url_for("edit_inventory_item", item_code=item_code))

    # ==========================================
    # STUDENTS & TRANSACTIONS
    # ==========================================

    @app.get("/students")
    def students_list():
        students = sorted(_system().students.values(), key=lambda student: student.enrolment_number)
        return render_template("students.html", students=students)

    @app.route("/students/new", methods=["GET", "POST"])
    def register_student():
        if request.method == "POST":
            try:
                _system().register_student(
                    name=request.form["name"].strip(),
                    enrolment_number=request.form["enrolment_number"].strip(),
                    programme=request.form["programme"].strip(),
                    semester=request.form["semester"].strip(),
                    contact_details=request.form["contact_details"].strip(),
                )
                flash("Student registered successfully.", "success")
                return redirect(url_for("students_list"))
            except (ValueError, InventoryError) as err:
                flash(str(err), "error")
        return render_template("student_form.html")

    @app.get("/students/<enrolment>")
    def student_detail(enrolment: str):
        student = _system().students.get(enrolment)
        if not student:
            flash("Student not found.", "error")
            return redirect(url_for("students_list"))
        records = _system().get_student_records(enrolment)
        outstanding = [record for record in records if record.outstanding_quantity > 0]
        reservations = _system().get_reservations(student_enrolment=enrolment)
        student_qr = svg_to_data_uri(generate_qr_svg(student.enrolment_number, size=120))
        return render_template(
            "student_detail.html",
            student=student,
            records=records,
            outstanding=outstanding,
            reservations=reservations,
            today=date.today(),
            student_qr=student_qr,
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

    # ==========================================
    # KITS & BUNDLES
    # ==========================================

    @app.get("/kits")
    def kits_list():
        kits = _system().list_kits()
        kit_statuses = {k.kit_id: _system().is_kit_available(k.kit_id) for k in kits}
        return render_template("kits.html", kits=kits, kit_statuses=kit_statuses)

    @app.route("/kits/new", methods=["GET", "POST"])
    def add_kit():
        if request.method == "POST":
            try:
                kit_id = request.form["kit_id"].strip()
                name = request.form["name"].strip()
                category = request.form.get("category", "General").strip()
                description = request.form.get("description", "").strip()

                raw_codes = request.form.getlist("item_code[]")
                raw_qtys = request.form.getlist("quantity[]")

                items = []
                for c, q in zip(raw_codes, raw_qtys):
                    if c and q:
                        items.append({"item_code": c.strip(), "quantity": int(q)})

                _system().add_kit(kit_id, name, category, description, items)
                flash(f"Kit '{name}' created successfully.", "success")
                return redirect(url_for("kits_list"))
            except (ValueError, KitValidationError, InventoryError) as err:
                flash(str(err), "error")

        return render_template(
            "kit_form.html",
            items=sorted(_system().items.values(), key=lambda it: it.code),
        )

    @app.route("/kits/<kit_id>/issue", methods=["GET", "POST"])
    def issue_kit_view(kit_id: str):
        kit = _system().get_kit(kit_id)
        if request.method == "POST":
            try:
                student = request.form["student_enrolment"].strip()
                purpose = request.form["purpose"].strip()
                staff = request.form.get("staff", "Desk").strip()
                records = _system().issue_kit(
                    kit_id=kit_id,
                    student_enrolment=student,
                    purpose=purpose,
                    issuing_staff=staff,
                )
                flash(f"Bundle Kit '{kit.name}' issued successfully! {len(records)} items checked out.", "success")
                return redirect(url_for("transactions"))
            except (ValueError, KitValidationError, InventoryError) as err:
                flash(str(err), "error")

        return render_template(
            "kit_issue.html",
            kit=kit,
            is_available=_system().is_kit_available(kit_id),
            students=sorted(_system().students.values(), key=lambda s: s.enrolment_number),
        )

    # ==========================================
    # RESERVATIONS & BOOKINGS
    # ==========================================

    @app.get("/reservations")
    def reservations_list():
        status_filter = request.args.get("status")
        reservations = _system().get_reservations(status=status_filter)
        return render_template(
            "reservations.html",
            reservations=reservations,
            status_filter=status_filter,
        )

    @app.route("/reservations/new", methods=["GET", "POST"])
    def add_reservation():
        if request.method == "POST":
            try:
                start_d = date.fromisoformat(request.form["start_date"])
                end_d = date.fromisoformat(request.form["end_date"])
                res = _system().create_reservation(
                    student_enrolment=request.form["student_enrolment"].strip(),
                    item_code=request.form["item_code"].strip(),
                    quantity=int(request.form["quantity"]),
                    start_date=start_d,
                    end_date=end_d,
                    purpose=request.form["purpose"].strip(),
                    notes=request.form.get("notes", "").strip(),
                )
                flash(f"Reservation {res.reservation_id} created successfully.", "success")
                return redirect(url_for("reservations_list"))
            except (ValueError, ReservationValidationError, InventoryError) as err:
                flash(str(err), "error")

        return render_template(
            "reservation_form.html",
            students=sorted(_system().students.values(), key=lambda s: s.enrolment_number),
            items=sorted(_system().items.values(), key=lambda it: it.code),
            today=date.today(),
        )

    @app.post("/reservations/<res_id>/fulfill")
    def fulfill_reservation_view(res_id: str):
        try:
            staff = request.form.get("staff", "Inventory Desk")
            issue = _system().fulfill_reservation(res_id, issuing_staff=staff)
            flash(f"Reservation fulfilled! Checkout record {issue.issue_id} created.", "success")
        except (ReservationValidationError, InventoryError) as err:
            flash(str(err), "error")
        return redirect(url_for("reservations_list"))

    @app.post("/reservations/<res_id>/cancel")
    def cancel_reservation_view(res_id: str):
        try:
            _system().cancel_reservation(res_id, cancelled_by="Desk Staff")
            flash(f"Reservation {res_id} cancelled.", "success")
        except (ReservationValidationError, InventoryError) as err:
            flash(str(err), "error")
        return redirect(url_for("reservations_list"))

    # ==========================================
    # MAINTENANCE & WORK ORDERS
    # ==========================================

    @app.get("/maintenance")
    def maintenance_list():
        records = _system().get_maintenance_records()
        total_cost = sum(r.cost for r in records)
        open_count = len([r for r in records if r.status == "open"])
        return render_template(
            "maintenance.html",
            records=records,
            total_cost=total_cost,
            open_count=open_count,
        )

    @app.route("/maintenance/new", methods=["GET", "POST"])
    def add_maintenance():
        if request.method == "POST":
            try:
                rec = _system().create_maintenance_record(
                    item_code=request.form["item_code"].strip(),
                    title=request.form["title"].strip(),
                    issue_description=request.form["issue_description"].strip(),
                    technician=request.form["technician"].strip(),
                    cost=float(request.form.get("cost", 0.0)),
                    asset_id=request.form.get("asset_id", "").strip() or None,
                )
                flash(f"Work order {rec.record_id} logged. Item placed into maintenance.", "success")
                return redirect(url_for("maintenance_list"))
            except (ValueError, MaintenanceValidationError, InventoryError) as err:
                flash(str(err), "error")

        return render_template(
            "maintenance_form.html",
            items=sorted(_system().items.values(), key=lambda it: it.code),
            assets=list(_system().assets.values()),
        )

    @app.post("/maintenance/<rec_id>/complete")
    def complete_maintenance_view(rec_id: str):
        try:
            condition = request.form.get("resolution_condition", "usable")
            notes = request.form.get("notes", "")
            _system().complete_maintenance_record(rec_id, resolution_condition=condition, notes=notes)
            flash(f"Work order {rec_id} completed and equipment restored to {condition} state.", "success")
        except (MaintenanceValidationError, InventoryError) as err:
            flash(str(err), "error")
        return redirect(url_for("maintenance_list"))

    # ==========================================
    # PRINTABLE CUSTODY SLIP & RECEIPTS
    # ==========================================

    @app.get("/issues/<issue_id>/receipt")
    def issue_receipt(issue_id: str):
        issue = _system()._require_issue(issue_id)
        student = _system()._require_student(issue.student_enrolment)
        item = _system()._require_item(issue.item_code)

        barcode_svg = svg_to_data_uri(generate_code128_svg(issue.issue_id, height=45))
        qr_svg = svg_to_data_uri(generate_qr_svg(f"CHECKOUT:{issue.issue_id}:{issue.student_enrolment}", size=120))

        return render_template(
            "receipt.html",
            issue=issue,
            student=student,
            item=item,
            barcode_svg=barcode_svg,
            qr_svg=qr_svg,
            today=date.today(),
        )

    # ==========================================
    # BARCODE / QR LABELS & SCANNING
    # ==========================================

    @app.get("/labels")
    def labels_sheet():
        items_with_labels = []
        for it in _system().items.values():
            barcode_data = svg_to_data_uri(generate_code128_svg(it.code, height=35))
            qr_data = svg_to_data_uri(generate_qr_svg(it.code, size=90))
            items_with_labels.append({"item": it, "barcode": barcode_data, "qr": qr_data})

        assets_with_labels = []
        for a in _system().assets.values():
            barcode_data = svg_to_data_uri(generate_code128_svg(a.asset_id, height=35))
            qr_data = svg_to_data_uri(generate_qr_svg(a.asset_id, size=90))
            assets_with_labels.append({"asset": a, "barcode": barcode_data, "qr": qr_data})

        return render_template(
            "labels.html",
            items=items_with_labels,
            assets=assets_with_labels,
        )

    # ==========================================
    # ANALYTICS & REPORTS
    # ==========================================

    @app.get("/analytics")
    def analytics_dashboard():
        analytics = _system().get_analytics_summary()
        return render_template("analytics.html", analytics=analytics)

    # ==========================================
    # CSV DATA EXPORTS
    # ==========================================

    @app.get("/export/inventory.csv")
    def export_inventory_csv():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Code", "Name", "Category", "Tracking", "Total", "Available", "Issued", "Damaged", "Lost", "Maintenance", "Retired"])
        for it in _system().items.values():
            st = _system().get_inventory_status(it.code)
            writer.writerow([
                it.code, it.name, it.category, it.tracking_type,
                st["total"], st["available"], st["issued"], st["damaged"], st["lost"], st["maintenance"], st["retired"]
            ])
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=inventory_report.csv"},
        )

    @app.get("/export/transactions.csv")
    def export_transactions_csv():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Date", "Type", "Staff/User", "Issue ID", "Item Code", "Details"])
        for evt in _system().get_transaction_history():
            writer.writerow([
                evt["date"], evt["type"], evt["responsible_user"],
                evt["issue_id"] or "", evt["item_code"] or "", json.dumps(evt["details"])
            ])
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=transaction_audit_trail.csv"},
        )

    @app.get("/export/overdue.csv")
    def export_overdue_csv():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Issue ID", "Student Enrolment", "Student Name", "Student Contact", "Item Code", "Outstanding Qty", "Due Date", "Days Overdue"])
        for row in _system().get_overdue_items():
            stu = _system().students.get(str(row["student_enrolment"]))
            name = stu.name if stu else ""
            contact = stu.contact_details if stu else ""
            writer.writerow([
                row["issue_id"], row["student_enrolment"], name, contact,
                row["item_code"], row["outstanding_quantity"], row["due_date"], row["overdue_days"]
            ])
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=overdue_equipment.csv"},
        )

    # ==========================================
    # API DOCUMENTATION (SWAGGER UI)
    # ==========================================

    @app.get("/api/docs")
    def swagger_ui():
        return render_template("swagger_ui.html")

    @app.get("/api/openapi.json")
    def openapi_spec():
        with open("openapi.json", "r", encoding="utf-8") as f:
            spec = json.load(f)
        return jsonify(spec)

    return app


app = create_app()


if __name__ == "__main__":
    app.run()
