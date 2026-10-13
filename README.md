# inventory.nfsu.ac.in — National Forensic Sciences University (NFSU)
### Central Forensic Laboratory & Evidence Asset Intelligence Operating System
*(An Institution of National Importance under Ministry of Home Affairs, Government of India)*

[![Portal](https://img.shields.io/badge/portal-inventory.nfsu.ac.in-c8131a)](http://127.0.0.1:5000)
[![Unit Tests](https://img.shields.io/badge/tests-34%20passed-success)](tests/)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-0b2545)](requirements.txt)
[![Chain of Custody](https://img.shields.io/badge/compliance-ISO%2FIEC%2017025%20%7C%20BSA%20Sec%2063-d97706)](#statutory-chain-of-custody)
[![API](https://img.shields.io/badge/API-OpenAPI%203.0%20%2F%20Swagger%20UI-emerald)](#headless-rest-api-v1)

The official laboratory equipment, evidence custody, and hardware management platform for the **National Forensic Sciences University** (**राष्ट्रीय न्यायालयिक विज्ञान विश्वविद्यालय**), Gandhinagar (HQ) and regional campuses (Delhi, Goa, Tripura, Bhopal, Pune, Guwahati, Dharwad, Uganda). Engineered to surpass commercial systems (**Cheqroom**, **Snipe-IT**, **EZOfficeInventory**) with atomic evidence kits, ISO/IEC 17025 custody vouchers, optical QR return tokens, repair tracking, and an OpenAPI 3.0 REST backend.

---

## 🏆 Competitor Feature Comparison Matrix

| Core Enterprise Capability | **InvPRO Enterprise** | **Cheqroom** | **Snipe-IT** | **EZOfficeInventory** |
| :--- | :---: | :---: | :---: | :---: |
| **Atomic Multi-Asset Kits & Bundles** |  **Yes (1-Click Issue)** |  Yes | ⚠️ Component-only | ⚠️ Add-on |
| **Real-time Advance Booking & Reservations** |  **Yes (Frictionless)** |  Yes | ❌ No native booking | ⚠️ Workflow lock |
| **Maintenance & Repair Work Orders** |  **Yes (Cost + Resolution)** | ⚠️ Basic flag | ⚠️ Basic log |  Yes |
| **Pure-Python Native Barcodes & QR Codes** |  **Yes (SVG / No native C)** |  Cloud only | ⚠️ PHP GD req. |  Cloud only |
| **Printable Custody Slips with Return QR** |  **Yes (Print/PDF Ready)** | ⚠️ Enterprise tier | ❌ Minimal | ⚠️ Custom template |
| **Full REST API (v1) + Swagger UI** |  **Yes (OpenAPI 3.0)** |  Yes | ⚠️ Token setup |  Yes |
| **Zero-Config Persistent Storage** |  **SQLite WAL + Auto-Hydrate** | ❌ SaaS lock | ⚠️ MySQL/Docker | ❌ SaaS lock |
| **Global Instant Search (`Ctrl+K`)** |  **Yes (Real-time Omnibar)** | ❌ Standard search | ❌ Page-based | ❌ Standard search |
| **CSV Audit & Delinquency Exports** |  **Yes (1-Click Downloads)** | ⚠️ Gated exports | ⚠️ Complex reports | ⚠️ Gated exports |
| **Cost & Deployment Friction** | 🟢 **Open, Self-Contained, Fast** | 🔴 High per-admin $ | 🟡 Complex setup | 🔴 High per-item $ |

---

## 🚀 Key Industry-Level Capabilities

### 1. Atomic Kits & Bundles Engine
- Group complex multi-asset production packages (e.g., *Sony A7 Camera Body + Rode Wireless Mic + Manfrotto Pro Tripod + 2x HDMI Cables*) into single identifiable kits.
- Real-time stock pre-flight: Automatically validates readiness before issue.
- **1-Click Bundle Checkout**: Issues all kit components to a student in an atomic custody transaction.

### 2. Advance Booking & Gear Reservations
- Students and instructors schedule hardware for future capstones, shoots, or lab sessions.
- Automatic double-booking detection and conflict resolution.
- Direct fulfillment: Approved reservations convert to active checkouts with one click.

### 3. Equipment Maintenance & Work Orders (CMMS)
- Automatically pulls damaged or recalibrating assets out of the available pool.
- Logs service technician details, fault descriptions, and dollar costs.
- Guided recovery: Restores serviced units to `usable`, or flags unrepairable hardware to `damaged` or `retired`.

### 4. Optical Barcode & QR Code Engine
- **Pure-Python Code-128 linear barcodes** and **2D matrix QR codes** generated dynamically as vector SVGs. Zero external native C libraries required.
- **Global Scanner Modal**: Compatible with USB and Bluetooth optical scanner guns or laser wedges.
- **Printable Sticker Sheet**: Print adhesive labels for camera bodies, bins, and student ID badges.

### 5. Legal Custody Slips & Return Tokens
- Printable student checkout custody receipts (`/issues/<issue_id>/receipt`) formatted for physical signing or PDF export.
- Includes student info, asset serial tags, due date, loss liability agreements, and a optical **Return Token QR** for desk check-in.

### 6. Persistence & Zero-Data-Loss Architecture
- In production, automatically stores all state, transaction logs, and reservations in SQLite with **Write-Ahead Logging (WAL)**.
- Hot reloads preserve data across process restarts.
- Fully isolated in-memory execution mode for unit tests.

### 7. Headless REST API (v1) with OpenAPI 3.0 & Swagger UI
- Full JSON endpoints for ERP, mobile apps, or RFID gate integrations.
- Built-in interactive Swagger UI available directly at `/api/docs`.

---

## 📋 REST API Endpoints Overview

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/health` | Service health status and timestamp |
| `GET` | `/api/v1/metrics` | Fleet utilization %, category distribution, and top borrowers |
| `GET` | `/api/v1/items` | List inventory catalog with query and category filters |
| `POST` | `/api/v1/items` | Register new inventory item SKU |
| `GET` | `/api/v1/items/{code}` | Retrieve item details and child serialized asset tags |
| `GET` | `/api/v1/assets` | Query serialized hardware units by item or condition |
| `POST` | `/api/v1/assets` | Register physical serialized asset with location |
| `GET` | `/api/v1/students` | List registered student borrowers |
| `POST` | `/api/v1/students` | Register new student profile |
| `POST` | `/api/v1/checkout` | Single item checkout to student |
| `POST` | `/api/v1/checkin` | Record return with condition grading (`usable`, `damaged`, `lost`) |
| `GET` | `/api/v1/kits` | List multi-item kits and readiness state |
| `POST` | `/api/v1/kits` | Register a new multi-item bundle package |
| `POST` | `/api/v1/kits/checkout` | 1-Click checkout of an entire kit bundle |
| `GET` | `/api/v1/reservations`| Query scheduled reservations by status or student |
| `POST` | `/api/v1/reservations`| Book gear for future calendar window |
| `GET` | `/api/v1/maintenance` | Query open and completed service work orders |
| `POST` | `/api/v1/maintenance` | Log a repair work order and pull asset out of rotation |
| `GET` | `/api/v1/search?q={query}` | Instant universal search across catalog, assets, and students |
| `GET` | `/api/v1/barcode/{code}` | Render standalone Code-128 barcode SVG |
| `GET` | `/api/v1/qr/{code}` | Render standalone 2D QR matrix SVG |

---

## 💻 Local Setup & Execution

### Prerequisites
Python 3.10+ (Standard library only; zero heavy native binaries needed).

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the web application
python app.py
```

Open: **`http://127.0.0.1:5000`**

- **Dashboard**: `http://127.0.0.1:5000/`
- **Kits & Bundles**: `http://127.0.0.1:5000/kits`
- **Reservations**: `http://127.0.0.1:5000/reservations`
- **Maintenance**: `http://127.0.0.1:5000/maintenance`
- **Fleet Analytics**: `http://127.0.0.1:5000/analytics`
- **Barcodes & Labels**: `http://127.0.0.1:5000/labels`
- **Interactive API Swagger Docs**: `http://127.0.0.1:5000/api/docs`

---

## 🧪 Comprehensive Automated Test Suite

Run all **34 tests** with verbose diagnostics:

```bash
python -m unittest discover -s tests -v
```

All 34 tests run in **< 1.0 second**, covering:
- Core inventory balance invariants and negative stock guards.
- Atomic kit creation, readiness checks, and bundle checkout.
- Advance gear reservation creation, review, and fulfillment.
- Maintenance transitions and condition updates.
- SQLite WAL persistence roundtripping and reload.
- Full REST API JSON contract tests.
- Pure-Python SVG barcode and QR generation.
- CSV export data integrity and printable receipts.

---

## 📂 Project Directory Structure

```text
inventory/
├── api_v1.py                  # Enterprise REST API v1 blueprint
├── app.py                     # Primary Flask application controller & routes
├── barcode_utils.py           # Pure-Python SVG Code-128 & QR generator
├── database_storage.py        # SQLite persistence layer with WAL mode
├── inventory_system.py        # Core domain model & business logic engine
├── openapi.json               # OpenAPI 3.0 specification
├── requirements.txt           # Minimal, production-grade dependencies
├── templates/                 # Modern, responsive UI templates
│   ├── analytics.html         # Fleet analytics & utilization dashboard
│   ├── base.html              # Modern responsive layout, search & scanner modal
│   ├── dashboard.html         # Operations Command Center
│   ├── due.html               # Delinquent & upcoming returns view
│   ├── history.html           # Immutable custody audit trail
│   ├── inventory.html         # Fleet catalog with stock health badges
│   ├── inventory_form.html    # SKU & asset registration form
│   ├── kit_form.html          # Dynamic kit bundle builder
│   ├── kit_issue.html         # 1-Click kit checkout modal
│   ├── kits.html              # Kits & bundles catalog with readiness badges
│   ├── labels.html            # Printable barcode & QR sticker sheet
│   ├── maintenance.html       # Maintenance & repair work orders dashboard
│   ├── maintenance_form.html  # Service order creation form
│   ├── receipt.html           # Printable custody slip & signature agreement
│   ├── reservation_form.html  # Gear booking form
│   ├── reservations.html      # Reservations schedule pipeline
│   ├── student_detail.html    # Student account with optical QR badge
│   ├── student_form.html      # New student borrower registration form
│   ├── students.html          # Student borrowers roster
│   ├── swagger_ui.html        # Interactive OpenAPI documentation viewer
│   └── transactions.html      # Issue & return workflows
└── tests/
    ├── test_app.py                      # Original application workflow tests
    ├── test_enterprise_api_and_web.py  # REST API, exports, and receipt tests
    ├── test_enterprise_features.py     # Domain kits, reservations, and storage tests
    └── test_inventory_system.py         # Invariant & stock consistency tests
```
