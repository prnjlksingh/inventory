"""
Enterprise REST API v1 for Department Inventory & Asset Management.
Provides JSON endpoints for headless integration, mobile barcode scanners, and ERP syncing.
Includes OpenAPI 3.0 specification and Swagger UI documentation.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict

from flask import Blueprint, Response, jsonify, request

from barcode_utils import generate_code128_svg, generate_qr_svg
from inventory_system import (
    DepartmentInventorySystem,
    InventoryError,
    KitValidationError,
    MaintenanceValidationError,
    ReservationValidationError,
)

api_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")


def _get_system() -> DepartmentInventorySystem:
    from flask import current_app
    return current_app.config["INVENTORY_SYSTEM"]


@api_bp.get("/health")
def health_check():
    return jsonify({
        "status": "healthy",
        "service": "NFSU Central Laboratory Inventory Enterprise API (inventory.nfsu.ac.in)",
        "university": "National Forensic Sciences University, Ministry of Home Affairs",
        "version": "2.0.0",
        "timestamp": date.today().isoformat(),
    })


@api_bp.get("/metrics")
def get_metrics():
    system = _get_system()
    analytics = system.get_analytics_summary()
    return jsonify(analytics)


@api_bp.get("/items")
def list_items():
    system = _get_system()
    query = request.args.get("q", "").strip().lower()
    category = request.args.get("category", "").strip().lower()

    items = []
    for it in system.items.values():
        if query and query not in f"{it.code} {it.name}".lower():
            continue
        if category and it.category.lower() != category:
            continue
        status = system.get_inventory_status(it.code)
        items.append({
            "code": it.code,
            "name": it.name,
            "category": it.category,
            "description": it.description,
            "make_model": it.make_model,
            "tracking_type": it.tracking_type,
            "status": status,
        })
    return jsonify({"count": len(items), "items": items})


@api_bp.get("/items/<code>")
def get_item(code: str):
    system = _get_system()
    if code not in system.items:
        return jsonify({"error": f"Item '{code}' not found"}), 404
    it = system.items[code]
    status = system.get_inventory_status(code)
    assets = [
        {
            "asset_id": a.asset_id,
            "serial_number": a.serial_number,
            "location": a.location,
            "condition": a.condition,
            "is_issued": a.is_issued,
        }
        for a in system.assets.values()
        if a.item_code == code
    ]
    return jsonify({
        "code": it.code,
        "name": it.name,
        "category": it.category,
        "description": it.description,
        "make_model": it.make_model,
        "tracking_type": it.tracking_type,
        "status": status,
        "assets": assets,
    })


@api_bp.post("/items")
def create_item():
    system = _get_system()
    data = request.get_json(force=True, silent=True) or {}
    try:
        system.add_inventory_item(
            code=data["code"].strip(),
            name=data["name"].strip(),
            category=data["category"].strip(),
            description=data.get("description", "").strip(),
            make_model=data.get("make_model", "").strip(),
            total_quantity=int(data.get("total_quantity", 1)),
            tracking_type=data.get("tracking_type", "quantity"),
        )
        return jsonify({"message": "Item created successfully", "code": data["code"]}), 201
    except (KeyError, ValueError, InventoryError) as err:
        return jsonify({"error": str(err)}), 400


@api_bp.get("/assets")
def list_assets():
    system = _get_system()
    item_code = request.args.get("item_code")
    condition = request.args.get("condition")

    assets = list(system.assets.values())
    if item_code:
        assets = [a for a in assets if a.item_code == item_code]
    if condition:
        assets = [a for a in assets if a.condition == condition]

    return jsonify({
        "count": len(assets),
        "assets": [
            {
                "asset_id": a.asset_id,
                "item_code": a.item_code,
                "serial_number": a.serial_number,
                "location": a.location,
                "condition": a.condition,
                "is_issued": a.is_issued,
                "issue_id": a.issued_to_issue_id,
            }
            for a in assets
        ],
    })


@api_bp.post("/assets")
def create_asset():
    system = _get_system()
    data = request.get_json(force=True, silent=True) or {}
    try:
        system.add_asset(
            asset_id=data["asset_id"].strip(),
            item_code=data["item_code"].strip(),
            serial_number=data["serial_number"].strip(),
            location=data.get("location", "Main Storage").strip(),
            condition=data.get("condition", "usable"),
        )
        return jsonify({"message": "Asset registered successfully", "asset_id": data["asset_id"]}), 201
    except (KeyError, ValueError, InventoryError) as err:
        return jsonify({"error": str(err)}), 400


@api_bp.get("/students")
def list_students():
    system = _get_system()
    students = [
        {
            "enrolment_number": s.enrolment_number,
            "name": s.name,
            "programme": s.programme,
            "semester": s.semester,
            "contact_details": s.contact_details,
            "active_issues_count": len([
                iss for iss in system.get_student_records(s.enrolment_number)
                if iss.outstanding_quantity > 0
            ]),
        }
        for s in system.students.values()
    ]
    return jsonify({"count": len(students), "students": sorted(students, key=lambda x: x["enrolment_number"])})


@api_bp.post("/students")
def create_student():
    system = _get_system()
    data = request.get_json(force=True, silent=True) or {}
    try:
        system.register_student(
            name=data["name"].strip(),
            enrolment_number=data["enrolment_number"].strip(),
            programme=data["programme"].strip(),
            semester=data.get("semester", "I").strip(),
            contact_details=data.get("contact_details", "").strip(),
        )
        return jsonify({"message": "Student registered successfully", "enrolment_number": data["enrolment_number"]}), 201
    except (KeyError, ValueError, InventoryError) as err:
        return jsonify({"error": str(err)}), 400


@api_bp.get("/issues")
def list_issues():
    system = _get_system()
    open_only = request.args.get("open", "false").lower() == "true"
    issues = list(system.issues.values())
    if open_only:
        issues = [i for i in issues if i.outstanding_quantity > 0]

    return jsonify({
        "count": len(issues),
        "issues": [
            {
                "issue_id": i.issue_id,
                "student_enrolment": i.student_enrolment,
                "item_code": i.item_code,
                "quantity": i.quantity,
                "outstanding_quantity": i.outstanding_quantity,
                "purpose": i.purpose,
                "issue_date": i.issue_date.isoformat(),
                "due_date": i.due_date.isoformat(),
                "issuing_staff": i.issuing_staff,
                "asset_id": i.asset_id,
                "is_closed": i.is_closed,
            }
            for i in issues
        ],
    })


@api_bp.post("/checkout")
def checkout_item():
    system = _get_system()
    data = request.get_json(force=True, silent=True) or {}
    try:
        issue_date_val = None
        if data.get("issue_date"):
            issue_date_val = date.fromisoformat(data["issue_date"])

        record = system.issue_item(
            student_enrolment=data["student_enrolment"].strip(),
            item_code=data["item_code"].strip(),
            quantity=int(data.get("quantity", 1)),
            purpose=data.get("purpose", "Equipment Checkout").strip(),
            issuing_staff=data.get("issuing_staff", "API").strip(),
            issue_date=issue_date_val,
            asset_id=data.get("asset_id", "").strip() or None,
        )
        return jsonify({
            "message": "Checkout completed successfully",
            "issue_id": record.issue_id,
            "due_date": record.due_date.isoformat(),
            "outstanding_quantity": record.outstanding_quantity,
        }), 201
    except (KeyError, ValueError, InventoryError) as err:
        return jsonify({"error": str(err)}), 400


@api_bp.post("/checkin")
def checkin_item():
    system = _get_system()
    data = request.get_json(force=True, silent=True) or {}
    try:
        return_date_val = None
        if data.get("return_date"):
            return_date_val = date.fromisoformat(data["return_date"])

        system.record_return(
            issue_id=data["issue_id"].strip(),
            quantity_returned=int(data.get("quantity_returned", 1)),
            condition_on_return=data.get("condition_on_return", "usable"),
            receiving_staff=data.get("receiving_staff", "API").strip(),
            return_date=return_date_val,
        )
        return jsonify({
            "message": "Check-in completed successfully",
            "issue_id": data["issue_id"],
            "remaining_outstanding": system.issues[data["issue_id"]].outstanding_quantity,
        }), 200
    except (KeyError, ValueError, InventoryError) as err:
        return jsonify({"error": str(err)}), 400


@api_bp.get("/kits")
def list_kits():
    system = _get_system()
    kits = []
    for k in system.list_kits():
        kits.append({
            "kit_id": k.kit_id,
            "name": k.name,
            "category": k.category,
            "description": k.description,
            "is_available": system.is_kit_available(k.kit_id),
            "items": [{"item_code": it.item_code, "quantity": it.quantity} for it in k.items],
        })
    return jsonify({"count": len(kits), "kits": kits})


@api_bp.post("/kits")
def create_kit():
    system = _get_system()
    data = request.get_json(force=True, silent=True) or {}
    try:
        kit = system.add_kit(
            kit_id=data["kit_id"].strip(),
            name=data["name"].strip(),
            category=data.get("category", "General").strip(),
            description=data.get("description", "").strip(),
            items=data.get("items", []),
        )
        return jsonify({"message": "Kit registered successfully", "kit_id": kit.kit_id}), 201
    except (KeyError, ValueError, InventoryError) as err:
        return jsonify({"error": str(err)}), 400


@api_bp.post("/kits/checkout")
def checkout_kit():
    system = _get_system()
    data = request.get_json(force=True, silent=True) or {}
    try:
        issue_date_val = None
        if data.get("issue_date"):
            issue_date_val = date.fromisoformat(data["issue_date"])

        records = system.issue_kit(
            kit_id=data["kit_id"].strip(),
            student_enrolment=data["student_enrolment"].strip(),
            purpose=data.get("purpose", "Kit Issue").strip(),
            issuing_staff=data.get("issuing_staff", "API").strip(),
            issue_date=issue_date_val,
            asset_mappings=data.get("asset_mappings"),
        )
        return jsonify({
            "message": "Kit issued successfully",
            "kit_id": data["kit_id"],
            "issued_records": [r.issue_id for r in records],
        }), 201
    except (KeyError, ValueError, InventoryError) as err:
        return jsonify({"error": str(err)}), 400


@api_bp.get("/reservations")
def list_reservations():
    system = _get_system()
    status = request.args.get("status")
    student = request.args.get("student_enrolment")
    res_list = system.get_reservations(status=status, student_enrolment=student)
    return jsonify({
        "count": len(res_list),
        "reservations": [
            {
                "reservation_id": r.reservation_id,
                "student_enrolment": r.student_enrolment,
                "item_code": r.item_code,
                "quantity": r.quantity,
                "start_date": r.start_date.isoformat(),
                "end_date": r.end_date.isoformat(),
                "purpose": r.purpose,
                "status": r.status,
                "asset_id": r.asset_id,
                "notes": r.notes,
            }
            for r in res_list
        ],
    })


@api_bp.post("/reservations")
def create_reservation():
    system = _get_system()
    data = request.get_json(force=True, silent=True) or {}
    try:
        start_d = date.fromisoformat(data["start_date"])
        end_d = date.fromisoformat(data["end_date"])
        res = system.create_reservation(
            student_enrolment=data["student_enrolment"].strip(),
            item_code=data["item_code"].strip(),
            quantity=int(data.get("quantity", 1)),
            start_date=start_d,
            end_date=end_d,
            purpose=data.get("purpose", "").strip(),
            asset_id=data.get("asset_id", "").strip() or None,
            notes=data.get("notes", "").strip(),
        )
        return jsonify({"message": "Reservation created", "reservation_id": res.reservation_id, "status": res.status}), 201
    except (KeyError, ValueError, InventoryError) as err:
        return jsonify({"error": str(err)}), 400


@api_bp.get("/maintenance")
def list_maintenance():
    system = _get_system()
    status = request.args.get("status")
    records = system.get_maintenance_records(status=status)
    return jsonify({
        "count": len(records),
        "records": [
            {
                "record_id": m.record_id,
                "item_code": m.item_code,
                "asset_id": m.asset_id,
                "title": m.title,
                "issue_description": m.issue_description,
                "technician": m.technician,
                "cost": m.cost,
                "started_date": m.started_date.isoformat(),
                "completed_date": m.completed_date.isoformat() if m.completed_date else None,
                "status": m.status,
                "notes": m.notes,
            }
            for m in records
        ],
    })


@api_bp.post("/maintenance")
def create_maintenance():
    system = _get_system()
    data = request.get_json(force=True, silent=True) or {}
    try:
        started_d = (
            date.fromisoformat(data["started_date"])
            if data.get("started_date")
            else None
        )
        rec = system.create_maintenance_record(
            item_code=data["item_code"].strip(),
            title=data["title"].strip(),
            issue_description=data.get("issue_description", "").strip(),
            technician=data.get("technician", "Service Center").strip(),
            cost=float(data.get("cost", 0.0)),
            asset_id=data.get("asset_id", "").strip() or None,
            started_date=started_d,
        )
        return jsonify({"message": "Maintenance record created", "record_id": rec.record_id}), 201
    except (KeyError, ValueError, InventoryError) as err:
        return jsonify({"error": str(err)}), 400


@api_bp.get("/search")
def instant_search():
    system = _get_system()
    q = request.args.get("q", "")
    results = system.search_everything(q)
    return jsonify(results)


@api_bp.get("/barcode/<code>")
def get_barcode_svg(code: str):
    svg = generate_code128_svg(code)
    return Response(svg, mimetype="image/svg+xml")


@api_bp.get("/qr/<code>")
def get_qr_svg(code: str):
    svg = generate_qr_svg(code)
    return Response(svg, mimetype="image/svg+xml")
