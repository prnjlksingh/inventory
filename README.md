# Inventory Management MVP (Hackathon Edition)

A demo-friendly inventory management app with a polished Flask UI and essential backend safeguards.

## What this MVP includes

- Dashboard with **total, available, issued, overdue, damaged, and lost** metrics
- Inventory list with search/filter and stock status badges
- Add/edit inventory item form
- Student list + student detail records
- Issue and return workflows with clear success/error feedback
- Overdue and upcoming returns view
- Transaction/activity history
- Seeded demo data available automatically at startup

## Essential business safeguards kept

- Cannot issue unavailable stock
- Student and item must exist for issue
- Return quantity cannot exceed outstanding quantity
- Asset-tracked item issue requires a valid available asset

## Local setup and run

```bash
cd /home/runner/work/inventory/inventory
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

Open: `http://127.0.0.1:5000`

> No authentication is enabled for this MVP, so no demo credentials are required.

## Run tests

```bash
cd /home/runner/work/inventory/inventory
python -m unittest discover -s tests -q
```

## Demo data

Demo data is seeded automatically when the app starts. It includes:

- Multiple students
- Quantity and asset-tracked inventory items
- Open/overdue/upcoming issues
- Damaged/lost examples
- Pre-populated activity history

## 3-minute hackathon demo flow

1. Open **Dashboard** to show inventory health and due-risk snapshot.
2. Go to **Inventory** and filter/search items.
3. Open **Students** and show one student’s active records.
4. Open **Issue & Return**:
   - Issue an item to a student
   - Record a return
5. Revisit **Dashboard** and **History** to show updates reflected instantly.

## Scope note

This repository is intentionally focused on MVP workflows and UI polish for demo readiness. Advanced rule engines and enterprise-hardening workflows are intentionally de-prioritized for the hackathon phase.
