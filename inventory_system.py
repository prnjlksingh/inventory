from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Set


class InventoryError(ValueError):
    """Raised when an inventory operation violates a business rule."""


class StudentValidationError(InventoryError):
    """Raised when student data or lookups are invalid."""


class ItemValidationError(InventoryError):
    """Raised when inventory item data or lookups are invalid."""


class AssetValidationError(InventoryError):
    """Raised when asset operations are invalid."""


class IssueValidationError(InventoryError):
    """Raised when issue operations are invalid."""


class ReturnValidationError(InventoryError):
    """Raised when return operations are invalid."""


class RenewalValidationError(InventoryError):
    """Raised when renewal operations are invalid."""


class StockIntegrityError(InventoryError):
    """Raised when stock adjustments violate invariants."""


class KitValidationError(InventoryError):
    """Raised when kit creation or checkout violates constraints."""


class ReservationValidationError(InventoryError):
    """Raised when reservation or booking violates rules."""


class MaintenanceValidationError(InventoryError):
    """Raised when equipment maintenance workflow violates rules."""


USABLE = "usable"
UNUSABLE_CONDITIONS = {"damaged", "lost", "maintenance", "retired"}


@dataclass
class Student:
    name: str
    enrolment_number: str
    programme: str
    semester: str
    contact_details: str


@dataclass
class InventoryItem:
    code: str
    name: str
    category: str
    description: str
    make_model: str
    total_quantity: int
    tracking_type: str = "quantity"
    damaged_quantity: int = 0
    lost_quantity: int = 0
    maintenance_quantity: int = 0
    retired_quantity: int = 0

    def unavailable_quantity(self) -> int:
        return (
            self.damaged_quantity
            + self.lost_quantity
            + self.maintenance_quantity
            + self.retired_quantity
        )


@dataclass
class Asset:
    asset_id: str
    item_code: str
    serial_number: str
    location: str
    condition: str = USABLE
    issued_to_issue_id: Optional[str] = None

    @property
    def is_issued(self) -> bool:
        return self.issued_to_issue_id is not None

    @property
    def is_issuable(self) -> bool:
        return self.condition == USABLE and not self.is_issued


@dataclass
class IssueRecord:
    issue_id: str
    student_enrolment: str
    item_code: str
    quantity: int
    purpose: str
    issue_date: date
    due_date: date
    issuing_staff: str
    asset_id: Optional[str] = None
    outstanding_quantity: int = 0
    renewal_count: int = 0
    renewal_status: Optional[str] = None
    history: List[Dict[str, object]] = field(default_factory=list)

    @property
    def is_closed(self) -> bool:
        return self.outstanding_quantity == 0


@dataclass
class KitItem:
    item_code: str
    quantity: int


@dataclass
class Kit:
    kit_id: str
    name: str
    category: str
    description: str
    items: List[KitItem] = field(default_factory=list)


@dataclass
class Reservation:
    reservation_id: str
    student_enrolment: str
    item_code: str
    quantity: int
    start_date: date
    end_date: date
    purpose: str
    status: str = "pending"  # pending, approved, fulfilled, rejected, cancelled
    asset_id: Optional[str] = None
    notes: str = ""
    created_at: date = field(default_factory=date.today)
    reviewed_by: Optional[str] = None


@dataclass
class MaintenanceRecord:
    record_id: str
    item_code: str
    asset_id: Optional[str]
    title: str
    issue_description: str
    technician: str
    cost: float
    started_date: date
    completed_date: Optional[date] = None
    status: str = "open"  # open, completed
    notes: str = ""


class DepartmentInventorySystem:
    """Industry-grade domain engine for campus and lab inventory management."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.students: Dict[str, Student] = {}
        self.items: Dict[str, InventoryItem] = {}
        self.assets: Dict[str, Asset] = {}
        self.issues: Dict[str, IssueRecord] = {}
        self.transaction_log: List[Dict[str, object]] = []
        self.storage_locations: Set[str] = set()
        self.issue_limits: Dict[str, int] = {}
        self.renewal_limits: Dict[str, int] = {}
        self._issue_sequence = 0

        # Enterprise modular domain entities
        self.kits: Dict[str, Kit] = {}
        self.reservations: Dict[str, Reservation] = {}
        self.maintenance_records: Dict[str, MaintenanceRecord] = {}
        self._reservation_sequence = 0
        self._maintenance_sequence = 0

        # SQLite persistence engine
        self._db_storage: Optional[Any] = None
        if db_path:
            from database_storage import DatabaseStorage

            self._db_storage = DatabaseStorage(db_path)
            if self._db_storage.has_existing_data():
                self._db_storage.load_into_system(self)

    def _persist(self) -> None:
        if self._db_storage:
            self._db_storage.persist_system(self)

    def add_storage_location(self, location: str) -> None:
        self.storage_locations.add(location)
        self._persist()

    def register_student(
        self,
        name: str,
        enrolment_number: str,
        programme: str,
        semester: str,
        contact_details: str,
    ) -> None:
        if not enrolment_number:
            raise StudentValidationError("enrolment_number is required.")
        if enrolment_number in self.students:
            raise StudentValidationError(f"Student {enrolment_number} is already registered.")
        self.students[enrolment_number] = Student(
            name=name,
            enrolment_number=enrolment_number,
            programme=programme,
            semester=semester,
            contact_details=contact_details,
        )
        self._persist()

    def add_inventory_item(
        self,
        code: str,
        name: str,
        category: str,
        description: str,
        make_model: str,
        total_quantity: int,
        tracking_type: str = "quantity",
    ) -> None:
        if total_quantity < 0:
            raise ItemValidationError("Total quantity cannot be negative.")
        if tracking_type not in {"quantity", "asset"}:
            raise ItemValidationError("tracking_type must be either 'quantity' or 'asset'.")
        if code in self.items:
            raise ItemValidationError(f"Item {code} already exists.")
        self.items[code] = InventoryItem(
            code=code,
            name=name,
            category=category,
            description=description,
            make_model=make_model,
            total_quantity=total_quantity,
            tracking_type=tracking_type,
        )
        self._persist()

    def add_asset(
        self,
        asset_id: str,
        item_code: str,
        serial_number: str,
        location: str,
        condition: str = USABLE,
    ) -> None:
        item = self._require_item(item_code)
        if item.tracking_type != "asset":
            raise AssetValidationError("Assets can only be added for asset-tracked items.")
        if condition not in {USABLE, *UNUSABLE_CONDITIONS}:
            raise AssetValidationError("Invalid asset condition.")
        if asset_id in self.assets:
            raise AssetValidationError(f"Asset {asset_id} already exists.")
        if any(
            existing.item_code == item_code and existing.serial_number == serial_number
            for existing in self.assets.values()
        ):
            raise AssetValidationError("Duplicate serial number for the same item.")
        if location:
            self.storage_locations.add(location)
        self.assets[asset_id] = Asset(
            asset_id=asset_id,
            item_code=item_code,
            serial_number=serial_number,
            location=location,
            condition=condition,
        )
        self._persist()

    def issue_item(
        self,
        student_enrolment: str,
        item_code: str,
        quantity: int,
        purpose: str,
        issuing_staff: str,
        issue_date: Optional[date] = None,
        asset_id: Optional[str] = None,
    ) -> IssueRecord:
        item = self._require_item(item_code)
        self._require_student(student_enrolment)

        issue_date = issue_date or date.today()
        self._ensure_date(issue_date, "issue_date")
        due_date = issue_date + timedelta(days=15)

        if quantity <= 0:
            raise IssueValidationError("Issued quantity must be positive.")

        limit = self.issue_limits.get(item_code)
        if limit is not None and quantity > limit:
            raise IssueValidationError(f"Issue limit exceeded for {item_code}.")

        if item.tracking_type == "asset":
            if quantity != 1:
                raise IssueValidationError("Asset-tracked items can only be issued in quantity 1.")
            if not asset_id:
                raise IssueValidationError("Asset ID is required for asset-tracked issue.")
            asset = self._require_asset(asset_id, item_code)
            if not asset.is_issuable:
                raise IssueValidationError("Asset is unavailable for issue.")
        else:
            available = self.get_available_quantity(item_code)
            if quantity > available:
                raise IssueValidationError(
                    f"{quantity} requested but only {available} currently available."
                )

        issue_id = self._next_issue_id()
        record = IssueRecord(
            issue_id=issue_id,
            student_enrolment=student_enrolment,
            item_code=item_code,
            quantity=quantity,
            purpose=purpose,
            issue_date=issue_date,
            due_date=due_date,
            issuing_staff=issuing_staff,
            asset_id=asset_id,
            outstanding_quantity=quantity,
        )

        if item.tracking_type == "asset":
            self.assets[asset_id].issued_to_issue_id = issue_id

        record.history.append(
            {
                "type": "issue",
                "date": issue_date,
                "user": issuing_staff,
                "quantity": quantity,
                "due_date": due_date,
            }
        )
        self.issues[issue_id] = record
        self._log_event("issue", issue_date, issuing_staff, issue_id, item_code, {"quantity": quantity})
        self._assert_item_stock_consistency(item_code)
        self._persist()
        return record

    def request_renewal(
        self, issue_id: str, request_date: date, requested_by: str, remarks: str = ""
    ) -> None:
        issue = self._require_issue(issue_id)
        self._ensure_date(request_date, "request_date")
        if issue.is_closed:
            raise RenewalValidationError("Cannot renew a fully returned issue.")
        if request_date < issue.issue_date:
            raise RenewalValidationError("Renewal request date cannot be before issue date.")
        if issue.renewal_status == "requested":
            raise RenewalValidationError("A renewal request is already pending review.")
        issue.renewal_status = "requested"
        issue.history.append(
            {
                "type": "renewal_requested",
                "date": request_date,
                "user": requested_by,
                "remarks": remarks,
            }
        )
        self._log_event(
            "renewal_requested",
            request_date,
            requested_by,
            issue_id,
            issue.item_code,
            {"remarks": remarks},
        )
        self._persist()

    def review_renewal(
        self,
        issue_id: str,
        approval_status: str,
        approval_date: date,
        approving_staff: str,
        remarks: str = "",
    ) -> None:
        issue = self._require_issue(issue_id)
        self._ensure_date(approval_date, "approval_date")
        if issue.is_closed:
            raise RenewalValidationError("Cannot review renewal for a closed issue.")
        if approval_status not in {"approved", "rejected"}:
            raise RenewalValidationError("approval_status must be either 'approved' or 'rejected'.")
        if issue.renewal_status != "requested":
            raise RenewalValidationError("Renewal review requires a prior pending request.")
        requested_on = self._latest_history_date(issue, "renewal_requested")
        if requested_on and approval_date < requested_on:
            raise RenewalValidationError("Renewal approval date cannot be before request date.")

        if approval_status == "approved":
            limit = self.renewal_limits.get(issue.item_code)
            if limit is not None and issue.renewal_count >= limit:
                raise RenewalValidationError("Renewal limit exceeded.")
            issue.due_date = issue.due_date + timedelta(days=15)
            issue.renewal_count += 1

        issue.renewal_status = approval_status
        issue.history.append(
            {
                "type": "renewal_reviewed",
                "date": approval_date,
                "user": approving_staff,
                "approval_status": approval_status,
                "remarks": remarks,
                "due_date": issue.due_date,
            }
        )
        self._log_event(
            "renewal_reviewed",
            approval_date,
            approving_staff,
            issue_id,
            issue.item_code,
            {"approval_status": approval_status, "remarks": remarks},
        )
        self._persist()

    def record_return(
        self,
        issue_id: str,
        quantity_returned: int,
        condition_on_return: str,
        receiving_staff: str,
        return_date: Optional[date] = None,
    ) -> None:
        issue = self._require_issue(issue_id)
        item = self._require_item(issue.item_code)
        return_date = return_date or date.today()
        self._ensure_date(return_date, "return_date")

        if quantity_returned <= 0:
            raise ReturnValidationError("Returned quantity must be positive.")
        if issue.is_closed:
            raise ReturnValidationError("Issue is already fully returned.")
        if quantity_returned > issue.outstanding_quantity:
            raise ReturnValidationError("Returned quantity exceeds outstanding quantity.")
        if condition_on_return not in {USABLE, *UNUSABLE_CONDITIONS}:
            raise ReturnValidationError("Invalid return condition.")
        if return_date < issue.issue_date:
            raise ReturnValidationError("Return date cannot be before issue date.")

        if item.tracking_type == "asset" and quantity_returned != 1:
            raise ReturnValidationError("Asset returns must be for quantity 1.")

        issue.outstanding_quantity -= quantity_returned

        if item.tracking_type == "asset":
            asset = self._require_asset(issue.asset_id, issue.item_code)
            if asset.issued_to_issue_id != issue_id:
                raise ReturnValidationError("Asset is not issued against this issue record.")
            asset.issued_to_issue_id = None
            asset.condition = condition_on_return
        else:
            if condition_on_return == "damaged":
                item.damaged_quantity += quantity_returned
            elif condition_on_return == "lost":
                item.lost_quantity += quantity_returned
            elif condition_on_return == "maintenance":
                item.maintenance_quantity += quantity_returned

        issue.history.append(
            {
                "type": "return",
                "date": return_date,
                "user": receiving_staff,
                "quantity": quantity_returned,
                "condition": condition_on_return,
                "outstanding_quantity": issue.outstanding_quantity,
            }
        )
        self._log_event(
            "return",
            return_date,
            receiving_staff,
            issue_id,
            issue.item_code,
            {
                "quantity": quantity_returned,
                "condition": condition_on_return,
                "outstanding_quantity": issue.outstanding_quantity,
            },
        )
        self._assert_item_stock_consistency(issue.item_code)
        self._persist()

    def update_asset_condition(
        self,
        asset_id: str,
        condition: str,
        updated_by: str,
        update_date: Optional[date] = None,
    ) -> None:
        asset = self._require_asset(asset_id)
        if condition not in {USABLE, *UNUSABLE_CONDITIONS}:
            raise AssetValidationError("Invalid asset condition.")
        if asset.is_issued and condition != USABLE:
            raise AssetValidationError("Issued assets cannot move to non-usable states directly.")
        asset.condition = condition
        self._log_event(
            "asset_condition_updated",
            update_date or date.today(),
            updated_by,
            asset.issued_to_issue_id,
            asset.item_code,
            {"asset_id": asset_id, "condition": condition},
        )
        self._persist()

    def record_stock_adjustment(
        self,
        item_code: str,
        quantity_delta: int,
        reason: str,
        responsible_user: str,
        adjustment_date: Optional[date] = None,
    ) -> None:
        item = self._require_item(item_code)
        self._ensure_date(adjustment_date, "adjustment_date", allow_none=True)
        if quantity_delta == 0:
            raise StockIntegrityError("quantity_delta cannot be zero.")
        if item.tracking_type == "asset":
            raise StockIntegrityError(
                "Stock adjustment is unsupported for asset-tracked items; use asset workflows."
            )
        if item.total_quantity + quantity_delta < item.unavailable_quantity():
            raise StockIntegrityError("Adjustment would make stock inconsistent.")
        if (
            self.get_issued_quantity(item_code)
            > item.total_quantity + quantity_delta - item.unavailable_quantity()
        ):
            raise StockIntegrityError("Adjustment would drop below currently issued quantity.")
        item.total_quantity += quantity_delta
        self._assert_item_stock_consistency(item_code)
        self._log_event(
            "stock_adjustment",
            adjustment_date or date.today(),
            responsible_user,
            None,
            item_code,
            {"quantity_delta": quantity_delta, "reason": reason},
        )
        self._persist()

    def retire_stock(
        self,
        item_code: str,
        quantity: int,
        reason: str,
        responsible_user: str,
        retirement_date: Optional[date] = None,
    ) -> None:
        item = self._require_item(item_code)
        if quantity <= 0:
            raise StockIntegrityError("Retired quantity must be positive.")
        if item.tracking_type == "asset":
            raise StockIntegrityError("Use asset condition updates to retire asset-tracked stock.")
        if quantity > self.get_available_quantity(item_code):
            raise StockIntegrityError("Cannot retire more than available stock.")
        item.retired_quantity += quantity
        self._assert_item_stock_consistency(item_code)
        self._log_event(
            "stock_retired",
            retirement_date or date.today(),
            responsible_user,
            None,
            item_code,
            {"quantity": quantity, "reason": reason},
        )
        self._persist()

    def get_available_quantity(self, item_code: str) -> int:
        item = self._require_item(item_code)

        if item.tracking_type == "asset":
            return sum(
                1
                for asset in self.assets.values()
                if asset.item_code == item_code and asset.is_issuable
            )

        available = item.total_quantity - self.get_issued_quantity(item_code) - item.unavailable_quantity()
        return max(available, 0)

    def get_issued_quantity(self, item_code: str) -> int:
        return sum(
            issue.outstanding_quantity
            for issue in self.issues.values()
            if issue.item_code == item_code and issue.outstanding_quantity > 0
        )

    def get_overdue_items(self, as_of_date: Optional[date] = None) -> List[Dict[str, object]]:
        as_of_date = as_of_date or date.today()
        overdue: List[Dict[str, object]] = []
        for issue in self.issues.values():
            if issue.outstanding_quantity == 0:
                continue
            if issue.due_date >= as_of_date:
                continue
            overdue.append(
                {
                    "student_enrolment": issue.student_enrolment,
                    "item_code": issue.item_code,
                    "outstanding_quantity": issue.outstanding_quantity,
                    "due_date": issue.due_date,
                    "overdue_days": (as_of_date - issue.due_date).days,
                    "issue_id": issue.issue_id,
                }
            )
        return sorted(overdue, key=lambda entry: (entry["due_date"], entry["issue_id"]))

    def get_upcoming_due_items(
        self, as_of_date: Optional[date] = None, within_days: int = 3
    ) -> List[Dict[str, object]]:
        as_of_date = as_of_date or date.today()
        end_date = as_of_date + timedelta(days=within_days)
        upcoming: List[Dict[str, object]] = []
        for issue in self.issues.values():
            if issue.outstanding_quantity == 0:
                continue
            if as_of_date <= issue.due_date <= end_date:
                upcoming.append(
                    {
                        "student_enrolment": issue.student_enrolment,
                        "item_code": issue.item_code,
                        "outstanding_quantity": issue.outstanding_quantity,
                        "due_date": issue.due_date,
                        "issue_id": issue.issue_id,
                    }
                )
        return sorted(upcoming, key=lambda entry: (entry["due_date"], entry["issue_id"]))

    def get_inventory_status(self, item_code: str, as_of_date: Optional[date] = None) -> Dict[str, int]:
        item = self._require_item(item_code)
        overdue_quantity = sum(
            entry["outstanding_quantity"]
            for entry in self.get_overdue_items(as_of_date)
            if entry["item_code"] == item_code
        )
        return {
            "total": item.total_quantity,
            "available": self.get_available_quantity(item_code),
            "issued": self.get_issued_quantity(item_code),
            "overdue": overdue_quantity,
            "damaged": item.damaged_quantity,
            "lost": item.lost_quantity,
            "maintenance": item.maintenance_quantity,
            "retired": item.retired_quantity,
        }

    def get_student_records(self, enrolment_number: str) -> List[IssueRecord]:
        return self._sorted_records(
            [
                issue
                for issue in self.issues.values()
                if issue.student_enrolment == enrolment_number
            ]
        )

    def get_programme_records(self, programme: str) -> List[IssueRecord]:
        eligible_students = {
            student.enrolment_number
            for student in self.students.values()
            if student.programme == programme
        }
        return self._sorted_records(
            [
                issue
                for issue in self.issues.values()
                if issue.student_enrolment in eligible_students
            ]
        )

    def get_item_records(self, item_code: str) -> List[IssueRecord]:
        return self._sorted_records([issue for issue in self.issues.values() if issue.item_code == item_code])

    def get_lab_records(self, location: str) -> List[IssueRecord]:
        item_codes = {
            asset.item_code
            for asset in self.assets.values()
            if asset.location == location
        }
        return self._sorted_records([issue for issue in self.issues.values() if issue.item_code in item_codes])

    def get_transaction_history(
        self,
        *,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        event_type: Optional[str] = None,
        item_code: Optional[str] = None,
        student_enrolment: Optional[str] = None,
    ) -> List[Dict[str, object]]:
        """Return transaction events with deterministic ordering and optional filters."""

        self._ensure_date(start_date, "start_date", allow_none=True)
        self._ensure_date(end_date, "end_date", allow_none=True)
        if start_date and end_date and start_date > end_date:
            raise InventoryError("start_date cannot be after end_date.")

        events: List[Dict[str, object]] = []
        for event in self.transaction_log:
            if start_date and event["date"] < start_date:
                continue
            if end_date and event["date"] > end_date:
                continue
            if event_type and event["type"] != event_type:
                continue
            if item_code and event["item_code"] != item_code:
                continue
            if student_enrolment:
                issue_id = event.get("issue_id")
                issue = self.issues.get(issue_id) if issue_id else None
                if not issue or issue.student_enrolment != student_enrolment:
                    continue
            events.append(event)
        return sorted(events, key=lambda entry: (entry["date"], entry["type"], entry.get("issue_id") or ""))

    # ==========================================
    # ENTERPRISE EXTENSIONS: KITS & BUNDLES
    # ==========================================

    def add_kit(
        self,
        kit_id: str,
        name: str,
        category: str,
        description: str,
        items: List[Dict[str, Any] | KitItem],
    ) -> Kit:
        """Create or register a bundle kit comprising multiple equipment items."""
        if not kit_id or not name:
            raise KitValidationError("kit_id and name are required.")
        if kit_id in self.kits:
            raise KitValidationError(f"Kit {kit_id} already exists.")

        parsed_items: List[KitItem] = []
        for it in items:
            code = it.item_code if isinstance(it, KitItem) else it["item_code"]
            qty = it.quantity if isinstance(it, KitItem) else int(it["quantity"])
            if qty <= 0:
                raise KitValidationError(f"Kit item quantity for {code} must be positive.")
            self._require_item(code)
            parsed_items.append(KitItem(item_code=code, quantity=qty))

        if not parsed_items:
            raise KitValidationError("A kit must contain at least one inventory item.")

        kit = Kit(
            kit_id=kit_id,
            name=name,
            category=category,
            description=description,
            items=parsed_items,
        )
        self.kits[kit_id] = kit
        self._persist()
        return kit

    def get_kit(self, kit_id: str) -> Kit:
        kit = self.kits.get(kit_id)
        if not kit:
            raise KitValidationError(f"Unknown kit: {kit_id}")
        return kit

    def list_kits(self) -> List[Kit]:
        return sorted(self.kits.values(), key=lambda k: k.kit_id)

    def is_kit_available(self, kit_id: str) -> bool:
        """Verify whether every component of the kit is currently in stock."""
        kit = self.get_kit(kit_id)
        for it in kit.items:
            if self.get_available_quantity(it.item_code) < it.quantity:
                return False
        return True

    def issue_kit(
        self,
        kit_id: str,
        student_enrolment: str,
        purpose: str,
        issuing_staff: str,
        issue_date: Optional[date] = None,
        asset_mappings: Optional[Dict[str, str]] = None,
    ) -> List[IssueRecord]:
        """Issue all components of a kit in an atomic bundle transaction."""
        kit = self.get_kit(kit_id)
        self._require_student(student_enrolment)
        asset_mappings = asset_mappings or {}

        # 1. Pre-flight check availability across all components
        for it in kit.items:
            item = self._require_item(it.item_code)
            if item.tracking_type == "asset":
                asset_id = asset_mappings.get(it.item_code)
                if not asset_id:
                    # Pick first available asset if not explicitly passed
                    avail_assets = [
                        a.asset_id for a in self.assets.values()
                        if a.item_code == it.item_code and a.is_issuable
                    ]
                    if not avail_assets:
                        raise KitValidationError(f"No available asset for kit item {it.item_code}.")
                    asset_id = avail_assets[0]
                    asset_mappings[it.item_code] = asset_id
                asset = self._require_asset(asset_id, it.item_code)
                if not asset.is_issuable:
                    raise KitValidationError(f"Asset {asset_id} is unavailable for kit issue.")
            else:
                available = self.get_available_quantity(it.item_code)
                if available < it.quantity:
                    raise KitValidationError(
                        f"Insufficient stock for kit item {it.item_code}: {available} available, {it.quantity} required."
                    )

        # 2. Issue each component
        issued_records: List[IssueRecord] = []
        full_purpose = f"Kit [{kit.name}] - {purpose}"
        for it in kit.items:
            asset_id = asset_mappings.get(it.item_code)
            rec = self.issue_item(
                student_enrolment=student_enrolment,
                item_code=it.item_code,
                quantity=it.quantity,
                purpose=full_purpose,
                issuing_staff=issuing_staff,
                issue_date=issue_date,
                asset_id=asset_id,
            )
            issued_records.append(rec)

        self._log_event(
            "kit_issued",
            issue_date or date.today(),
            issuing_staff,
            None,
            None,
            {"kit_id": kit_id, "issues": [r.issue_id for r in issued_records]},
        )
        self._persist()
        return issued_records

    # ==========================================
    # ENTERPRISE EXTENSIONS: RESERVATIONS / BOOKINGS
    # ==========================================

    def create_reservation(
        self,
        student_enrolment: str,
        item_code: str,
        quantity: int,
        start_date: date,
        end_date: date,
        purpose: str,
        asset_id: Optional[str] = None,
        notes: str = "",
    ) -> Reservation:
        self._require_student(student_enrolment)
        item = self._require_item(item_code)
        self._ensure_date(start_date, "start_date")
        self._ensure_date(end_date, "end_date")

        if start_date < date.today():
            raise ReservationValidationError("Reservation start date cannot be in the past.")
        if end_date < start_date:
            raise ReservationValidationError("End date cannot be earlier than start date.")
        if quantity <= 0:
            raise ReservationValidationError("Reservation quantity must be positive.")
        if item.tracking_type == "asset" and quantity != 1:
            raise ReservationValidationError("Asset items can only be reserved with quantity 1.")
        if asset_id:
            self._require_asset(asset_id, item_code)

        self._reservation_sequence += 1
        res_id = f"RES-{self._reservation_sequence:05d}"
        res = Reservation(
            reservation_id=res_id,
            student_enrolment=student_enrolment,
            item_code=item_code,
            quantity=quantity,
            start_date=start_date,
            end_date=end_date,
            purpose=purpose,
            status="approved",  # auto-approved by default for modern frictionless booking
            asset_id=asset_id,
            notes=notes,
            created_at=date.today(),
        )
        self.reservations[res_id] = res
        self._log_event(
            "reservation_created",
            date.today(),
            student_enrolment,
            None,
            item_code,
            {"reservation_id": res_id, "quantity": quantity, "start_date": str(start_date)},
        )
        self._persist()
        return res

    def review_reservation(
        self,
        reservation_id: str,
        approval_status: str,
        reviewing_staff: str,
        notes: str = "",
    ) -> None:
        if reservation_id not in self.reservations:
            raise ReservationValidationError("Unknown reservation.")
        if approval_status not in {"approved", "rejected"}:
            raise ReservationValidationError("approval_status must be 'approved' or 'rejected'.")
        res = self.reservations[reservation_id]
        if res.status != "pending":
            raise ReservationValidationError(f"Cannot review reservation currently in '{res.status}' status.")
        res.status = approval_status
        res.reviewed_by = reviewing_staff
        if notes:
            res.notes = f"{res.notes} | Staff: {notes}".strip(" |")
        self._persist()

    def cancel_reservation(self, reservation_id: str, cancelled_by: str, reason: str = "") -> None:
        if reservation_id not in self.reservations:
            raise ReservationValidationError("Unknown reservation.")
        res = self.reservations[reservation_id]
        if res.status in {"fulfilled", "cancelled"}:
            raise ReservationValidationError(f"Cannot cancel reservation in state '{res.status}'.")
        res.status = "cancelled"
        if reason:
            res.notes = f"{res.notes} | Cancelled: {reason}".strip(" |")
        self._persist()

    def fulfill_reservation(
        self,
        reservation_id: str,
        issuing_staff: str,
        asset_id: Optional[str] = None,
    ) -> IssueRecord:
        """Convert an approved reservation into an active checkout issue record."""
        if reservation_id not in self.reservations:
            raise ReservationValidationError("Unknown reservation.")
        res = self.reservations[reservation_id]
        if res.status not in {"pending", "approved"}:
            raise ReservationValidationError(f"Reservation is '{res.status}', cannot fulfill.")

        chosen_asset = asset_id or res.asset_id
        issue = self.issue_item(
            student_enrolment=res.student_enrolment,
            item_code=res.item_code,
            quantity=res.quantity,
            purpose=f"Reservation {res.reservation_id}: {res.purpose}",
            issuing_staff=issuing_staff,
            issue_date=date.today(),
            asset_id=chosen_asset,
        )
        res.status = "fulfilled"
        self._persist()
        return issue

    def get_reservations(
        self,
        status: Optional[str] = None,
        student_enrolment: Optional[str] = None,
    ) -> List[Reservation]:
        results = list(self.reservations.values())
        if status:
            results = [r for r in results if r.status == status]
        if student_enrolment:
            results = [r for r in results if r.student_enrolment == student_enrolment]
        return sorted(results, key=lambda r: (r.start_date, r.reservation_id))

    # ==========================================
    # ENTERPRISE EXTENSIONS: MAINTENANCE / REPAIRS
    # ==========================================

    def create_maintenance_record(
        self,
        item_code: str,
        title: str,
        issue_description: str,
        technician: str,
        cost: float = 0.0,
        asset_id: Optional[str] = None,
        started_date: Optional[date] = None,
    ) -> MaintenanceRecord:
        item = self._require_item(item_code)
        started_date = started_date or date.today()

        if item.tracking_type == "asset":
            if not asset_id:
                raise MaintenanceValidationError("Asset ID required for asset maintenance.")
            asset = self._require_asset(asset_id, item_code)
            if asset.is_issued:
                raise MaintenanceValidationError("Cannot put an issued asset into maintenance.")
            asset.condition = "maintenance"
        else:
            avail = self.get_available_quantity(item_code)
            if avail < 1:
                raise MaintenanceValidationError("No available stock to place into maintenance.")
            item.maintenance_quantity += 1
            self._assert_item_stock_consistency(item_code)

        self._maintenance_sequence += 1
        record_id = f"MNT-{self._maintenance_sequence:05d}"
        record = MaintenanceRecord(
            record_id=record_id,
            item_code=item_code,
            asset_id=asset_id,
            title=title,
            issue_description=issue_description,
            technician=technician,
            cost=cost,
            started_date=started_date,
            status="open",
        )
        self.maintenance_records[record_id] = record
        self._log_event(
            "maintenance_opened",
            started_date,
            technician,
            None,
            item_code,
            {"record_id": record_id, "title": title, "asset_id": asset_id},
        )
        self._persist()
        return record

    def complete_maintenance_record(
        self,
        record_id: str,
        resolution_condition: str = USABLE,
        completed_date: Optional[date] = None,
        technician: Optional[str] = None,
        notes: str = "",
    ) -> MaintenanceRecord:
        if record_id not in self.maintenance_records:
            raise MaintenanceValidationError(f"Unknown maintenance record: {record_id}")
        rec = self.maintenance_records[record_id]
        if rec.status == "completed":
            raise MaintenanceValidationError("Maintenance record is already completed.")
        if resolution_condition not in {USABLE, *UNUSABLE_CONDITIONS}:
            raise MaintenanceValidationError("Invalid resolution condition.")

        completed_date = completed_date or date.today()
        rec.status = "completed"
        rec.completed_date = completed_date
        if technician:
            rec.technician = technician
        if notes:
            rec.notes = notes

        item = self._require_item(rec.item_code)
        if item.tracking_type == "asset":
            asset = self._require_asset(rec.asset_id, rec.item_code)
            asset.condition = resolution_condition
        else:
            if item.maintenance_quantity > 0:
                item.maintenance_quantity -= 1
                if resolution_condition == USABLE:
                    pass  # automatically usable again
                elif resolution_condition == "damaged":
                    item.damaged_quantity += 1
                elif resolution_condition == "lost":
                    item.lost_quantity += 1
                elif resolution_condition == "retired":
                    item.retired_quantity += 1
            self._assert_item_stock_consistency(rec.item_code)

        self._log_event(
            "maintenance_completed",
            completed_date,
            rec.technician,
            None,
            rec.item_code,
            {"record_id": record_id, "resolution": resolution_condition},
        )
        self._persist()
        return rec

    def get_maintenance_records(self, status: Optional[str] = None) -> List[MaintenanceRecord]:
        records = list(self.maintenance_records.values())
        if status:
            records = [r for r in records if r.status == status]
        return sorted(records, key=lambda r: (r.started_date, r.record_id), reverse=True)

    # ==========================================
    # ENTERPRISE EXTENSIONS: ANALYTICS & SEARCH
    # ==========================================

    def get_analytics_summary(self) -> Dict[str, Any]:
        """Compute enterprise metrics, utilization rates, and operational insights."""
        total_items_count = len(self.items)
        total_units = sum(it.total_quantity for it in self.items.values())
        total_issued = sum(self.get_issued_quantity(code) for code in self.items)
        total_available = sum(self.get_available_quantity(code) for code in self.items)
        overdue_items = self.get_overdue_items()

        # Item category distribution
        category_counts: Dict[str, int] = {}
        for it in self.items.values():
            category_counts[it.category] = category_counts.get(it.category, 0) + it.total_quantity

        # Borrow count by student
        borrow_frequency: Dict[str, int] = {}
        for iss in self.issues.values():
            borrow_frequency[iss.student_enrolment] = borrow_frequency.get(iss.student_enrolment, 0) + iss.quantity

        top_borrowers = sorted(
            [
                {
                    "enrolment": enr,
                    "name": self.students[enr].name if enr in self.students else enr,
                    "count": cnt,
                }
                for enr, cnt in borrow_frequency.items()
            ],
            key=lambda x: x["count"],
            reverse=True,
        )[:5]

        # Top borrowed items
        item_borrow_counts: Dict[str, int] = {}
        for iss in self.issues.values():
            item_borrow_counts[iss.item_code] = item_borrow_counts.get(iss.item_code, 0) + iss.quantity

        top_items = sorted(
            [
                {
                    "code": code,
                    "name": self.items[code].name if code in self.items else code,
                    "count": cnt,
                }
                for code, cnt in item_borrow_counts.items()
            ],
            key=lambda x: x["count"],
            reverse=True,
        )[:5]

        utilization_rate = (total_issued / total_units * 100) if total_units > 0 else 0.0

        return {
            "total_items_count": total_items_count,
            "total_units": total_units,
            "total_issued": total_issued,
            "total_available": total_available,
            "total_overdue": len(overdue_items),
            "utilization_rate": round(utilization_rate, 1),
            "category_distribution": category_counts,
            "top_borrowers": top_borrowers,
            "top_items": top_items,
            "open_maintenance_count": len([m for m in self.maintenance_records.values() if m.status == "open"]),
            "active_reservations_count": len([r for r in self.reservations.values() if r.status in {"pending", "approved"}]),
            "active_kits_count": len(self.kits),
        }

    def search_everything(self, query: str) -> Dict[str, List[Dict[str, Any]]]:
        """Universal instant search across items, assets, students, and open issues."""
        q = (query or "").strip().lower()
        if not q:
            return {"items": [], "assets": [], "students": [], "issues": []}

        matched_items = [
            {"code": it.code, "name": it.name, "category": it.category, "available": self.get_available_quantity(it.code)}
            for it in self.items.values()
            if q in it.code.lower() or q in it.name.lower() or q in it.category.lower() or q in it.description.lower()
        ]

        matched_assets = [
            {"asset_id": a.asset_id, "item_code": a.item_code, "serial": a.serial_number, "location": a.location, "condition": a.condition}
            for a in self.assets.values()
            if q in a.asset_id.lower() or q in a.serial_number.lower() or q in a.location.lower()
        ]

        matched_students = [
            {"enrolment": s.enrolment_number, "name": s.name, "programme": s.programme}
            for s in self.students.values()
            if q in s.enrolment_number.lower() or q in s.name.lower() or q in s.programme.lower()
        ]

        matched_issues = [
            {"issue_id": iss.issue_id, "student": iss.student_enrolment, "item": iss.item_code, "outstanding": iss.outstanding_quantity}
            for iss in self.issues.values()
            if q in iss.issue_id.lower() or q in iss.student_enrolment.lower() or q in iss.item_code.lower()
        ]

        return {
            "items": matched_items[:8],
            "assets": matched_assets[:8],
            "students": matched_students[:8],
            "issues": matched_issues[:8],
        }

    # ==========================================
    # INTERNAL DOMAIN HELPERS
    # ==========================================

    def _sorted_records(self, records: List[IssueRecord]) -> List[IssueRecord]:
        return sorted(records, key=lambda issue: (issue.issue_date, issue.issue_id))

    def _assert_item_stock_consistency(self, item_code: str) -> None:
        item = self._require_item(item_code)
        if item.tracking_type == "asset":
            return
        issued = self.get_issued_quantity(item_code)
        unavailable = item.unavailable_quantity()
        if issued < 0 or unavailable < 0:
            raise StockIntegrityError("Stock values cannot be negative.")
        if issued + unavailable > item.total_quantity:
            raise StockIntegrityError("Issued + unavailable stock cannot exceed total stock.")

    def _ensure_date(self, value: Optional[date], field_name: str, allow_none: bool = False) -> None:
        if value is None and allow_none:
            return
        if not isinstance(value, date):
            raise InventoryError(f"{field_name} must be a date instance.")

    def _latest_history_date(self, issue: IssueRecord, event_type: str) -> Optional[date]:
        dates = [entry["date"] for entry in issue.history if entry.get("type") == event_type]
        if not dates:
            return None
        return max(dates)

    def _next_issue_id(self) -> str:
        self._issue_sequence += 1
        return f"ISSUE-{self._issue_sequence:05d}"

    def _require_student(self, enrolment_number: str) -> Student:
        student = self.students.get(enrolment_number)
        if not student:
            raise StudentValidationError("Items can be issued only to registered students.")
        return student

    def _require_item(self, item_code: str) -> InventoryItem:
        item = self.items.get(item_code)
        if not item:
            raise ItemValidationError("Unknown inventory item.")
        return item

    def _require_asset(self, asset_id: Optional[str], expected_item_code: Optional[str] = None) -> Asset:
        if not asset_id:
            raise AssetValidationError("Asset ID is required.")
        asset = self.assets.get(asset_id)
        if not asset:
            raise AssetValidationError("Unknown asset.")
        if expected_item_code and asset.item_code != expected_item_code:
            raise AssetValidationError("Asset does not belong to requested item.")
        return asset

    def _require_issue(self, issue_id: str) -> IssueRecord:
        issue = self.issues.get(issue_id)
        if not issue:
            raise IssueValidationError("Unknown issue record.")
        return issue

    def _log_event(
        self,
        event_type: str,
        event_date: date,
        responsible_user: str,
        issue_id: Optional[str],
        item_code: Optional[str],
        details: Dict[str, object],
    ) -> None:
        self.transaction_log.append(
            {
                "type": event_type,
                "date": event_date,
                "responsible_user": responsible_user,
                "issue_id": issue_id,
                "item_code": item_code,
                "details": details,
            }
        )
