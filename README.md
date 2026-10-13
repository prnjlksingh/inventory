# Department Inventory System

Lightweight Python inventory domain engine for department issue/return workflows with:

- quantity-tracked consumables/equipment
- individually tracked assets
- 15-day issue/renewal due-cycle rules
- audit/event history and reporting helpers

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

No third-party dependencies are required.

## Run tests

```bash
python -m unittest discover -s tests -q
```

## Core domain rules

- A student must be registered before issue.
- `issue_date` defaults to today; `due_date = issue_date + 15 days`.
- Renewal request **does not** change due date.
- Approved renewal extends from current due date by 15 days.
- Renewal review requires a pending renewal request.
- Returns cannot exceed outstanding quantity or predate issue date.
- Asset-tracked issues require exactly one asset and exclusive issuance.
- Quantity stock invariants are enforced: `issued + unavailable <= total`.

## Basic usage

```python
from datetime import date
from inventory_system import DepartmentInventorySystem

system = DepartmentInventorySystem()
system.register_student("Alice", "ENR-001", "M.Sc. DFIS", "I", "alice@example.com")
system.add_inventory_item("USB-CBL", "USB Cable", "Cable", "Reusable cable", "Type-C", 20)

issue = system.issue_item(
    student_enrolment="ENR-001",
    item_code="USB-CBL",
    quantity=2,
    purpose="Lab work",
    issuing_staff="coord",
    issue_date=date(2026, 10, 1),
)

system.request_renewal(issue.issue_id, request_date=date(2026, 10, 10), requested_by="ENR-001")
system.review_renewal(
    issue.issue_id,
    approval_status="approved",
    approval_date=date(2026, 10, 11),
    approving_staff="coord",
)
```

## API overview

Key methods:

- Student/item/asset setup:
  - `register_student`
  - `add_inventory_item`
  - `add_asset`
- Transactional operations:
  - `issue_item`
  - `record_return` (supports partial returns)
  - `request_renewal`
  - `review_renewal`
  - `record_stock_adjustment`
  - `retire_stock`
- Condition + stock helpers:
  - `update_asset_condition`
  - `get_available_quantity`
  - `get_issued_quantity`
  - `get_inventory_status`
- Reporting:
  - `get_overdue_items`
  - `get_upcoming_due_items`
  - `get_student_records`
  - `get_programme_records`
  - `get_item_records`
  - `get_lab_records`
  - `get_transaction_history`

## Error handling

All domain exceptions inherit from `InventoryError` with specialized subclasses:

- `StudentValidationError`
- `ItemValidationError`
- `AssetValidationError`
- `IssueValidationError`
- `ReturnValidationError`
- `RenewalValidationError`
- `StockIntegrityError`