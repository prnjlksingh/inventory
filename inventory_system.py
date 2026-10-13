from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional


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


class DepartmentInventorySystem:
    """In-memory domain service for department inventory issue workflows."""

    def __init__(self) -> None:
        self.students: Dict[str, Student] = {}
        self.items: Dict[str, InventoryItem] = {}
        self.assets: Dict[str, Asset] = {}
        self.issues: Dict[str, IssueRecord] = {}
        self.transaction_log: List[Dict[str, object]] = []
        self.storage_locations: set[str] = set()
        self.issue_limits: Dict[str, int] = {}
        self.renewal_limits: Dict[str, int] = {}
        self._issue_sequence = 0

    def add_storage_location(self, location: str) -> None:
        self.storage_locations.add(location)

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
        if self.get_issued_quantity(item_code) > item.total_quantity + quantity_delta - item.unavailable_quantity():
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
