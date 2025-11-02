#!/usr/bin/env python3
# Vihaa Vastra Sarees – Flask CRM (templates-based)
# Notes:
# - No login
# - Uses render_template() only (no inline HTML)
# - Safe SQLite init in app.app_context()
# - Gentle server-side validation for orders (amount, status/mode coupling)
# - Logs errors to crm.log

import os
import logging
from datetime import datetime, date
from pathlib import Path

from flask import (
    Flask, request, redirect, url_for, jsonify, render_template, flash
)
from flask_sqlalchemy import SQLAlchemy

APP_NAME = "Vihaa Vastra Sarees"
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "saree_crm.db"         # keep at project root for now
INSTANCE_DIR = BASE_DIR / "instance"        # Flask instance (not strictly needed here)

# --- Flask & DB setup ----------------------------------------------------------
app = Flask(APP_NAME)
app.secret_key = os.environ.get("FLASK_SECRET", "vv-sarees-secret")

# SQLite URI
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# --- Logging -------------------------------------------------------------------
log_file = BASE_DIR / "crm.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler()
    ],
)
log = logging.getLogger("crm")

# --- Models --------------------------------------------------------------------
class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.String(64), unique=True, nullable=False)  # human ID (e.g., CUST0001)
    name = db.Column(db.String(120), nullable=False)
    insta = db.Column(db.String(120))
    phone = db.Column(db.String(32))
    city = db.Column(db.String(120))
    ctype = db.Column(db.String(64))   # Regular / VIP etc
    notes = db.Column(db.Text)

    def __repr__(self):
        return f"<Customer {self.customer_id} {self.name}>"


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.String(64), unique=True, nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    customer_id = db.Column(db.String(64), db.ForeignKey('customer.customer_id'), nullable=False)

    saree_type = db.Column(db.String(120))
    amount = db.Column(db.Integer, default=0)

    purchase_type = db.Column(db.String(16))        # Online / Offline
    payment_status = db.Column(db.String(16))       # Pending / Paid
    payment_mode = db.Column(db.String(16))         # UPI / Cash / Pending (auto)
    delivery_status = db.Column(db.String(16))      # Pending / Shipped / Delivered / Cancelled

    remarks = db.Column(db.Text)

    customer = db.relationship('Customer', backref='orders', primaryjoin="Customer.customer_id==Order.customer_id")

    def __repr__(self):
        return f"<Order {self.order_id} {self.customer_id} {self.amount}>"


class FollowUp(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.String(64), db.ForeignKey('customer.customer_id'), nullable=False)
    followup_date = db.Column(db.Date, nullable=False, default=date.today)
    notes = db.Column(db.Text)
    status = db.Column(db.String(32))  # Open / Done

    customer = db.relationship('Customer', primaryjoin="Customer.customer_id==FollowUp.customer_id")


# --- Helpers -------------------------------------------------------------------
def parse_date(dstr: str):
    """Accepts 'YYYY-MM-DD' (from input type=date) or 'DD/MM/YYYY'."""
    if not dstr:
        return date.today()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(dstr, fmt).date()
        except ValueError:
            pass
    return date.today()

def next_human_id(prefix: str, table, field: str, width=5):
    """Generate next human-readable id like ORD20251101-00001."""
    today = date.today().strftime("%Y%m%d")
    like = f"{prefix}{today}-%"
    # fetch latest today
    latest = (
        db.session.query(table)
        .filter(getattr(table, field).like(like))
        .order_by(getattr(table, field).desc())
        .first()
    )
    if not latest:
        seq = 1
    else:
        try:
            seq = int(latest.__dict__[field].split("-")[-1]) + 1
        except Exception:
            seq = 1
    return f"{prefix}{today}-{str(seq).zfill(width)}"

def validate_order_form(form, is_update=False):
    """Server-side guardrails for order create/update."""
    errors = []

    cust_id = (form.get("customer_id") or "").strip()
    if not cust_id:
        errors.append("Customer is required.")

    amount_raw = (form.get("amount") or "").strip()
    try:
        amt = int(amount_raw)
    except Exception:
        errors.append("Amount must be a whole number.")
        amt = 0

    purchase_type = (form.get("purchase_type") or "").strip()
    if purchase_type not in ("Online", "Offline"):
        errors.append("Purchase Type must be Online or Offline.")

    payment_status = (form.get("payment_status") or "").strip()
    if payment_status not in ("Pending", "Paid"):
        errors.append("Payment Status must be Pending or Paid.")

    payment_mode = (form.get("payment_mode") or "").strip()
    # coupling: if Pending => mode must be 'Pending' and ignored/disabled
    if payment_status == "Pending":
        payment_mode = "Pending"
    else:
        if payment_mode not in ("UPI", "Cash"):
            errors.append("Payment Mode must be UPI or Cash when status is Paid.")

    delivery_status = (form.get("delivery_status") or "").strip()
    if delivery_status not in ("Pending", "Shipped", "Delivered", "Cancelled"):
        errors.append("Delivery Status must be one of Pending/Shipped/Delivered/Cancelled.")

    dt = parse_date(form.get("date"))

    return {
        "customer_id": cust_id,
        "amount": amt,
        "purchase_type": purchase_type,
        "payment_status": payment_status,
        "payment_mode": payment_mode,
        "delivery_status": delivery_status,
        "date": dt,
        "saree_type": (form.get("saree_type") or "").strip(),
        "remarks": (form.get("remarks") or "").strip(),
    }, errors

# --- Error pages ---------------------------------------------------------------
@app.errorhandler(Exception)
def on_any_error(e):
    log.exception("Unhandled exception")
    # Friendly error page that still returns proper 500
    return render_template("errors/500.html") if (BASE_DIR/"templates/errors/500.html").exists() else ("Internal Server Error", 500)

# --- Routes: basics ------------------------------------------------------------
@app.route("/")
def root():
    return redirect(url_for("dashboard"))

# ...existing code...
@app.route("/dashboard")
def dashboard():
    from datetime import date

    try:
        today = date.today()

        # Totals
        total_orders = db.session.query(db.func.count(Order.id)).scalar() or 0
        total_paid = (
            db.session.query(db.func.coalesce(db.func.sum(Order.amount), 0))
            .filter(Order.payment_status == "Paid")
            .scalar()
            or 0
        )
        total_pending = (
            db.session.query(db.func.coalesce(db.func.sum(Order.amount), 0))
            .filter(Order.payment_status == "Pending")
            .scalar()
            or 0
        )
        pending_followups = (
            db.session.query(db.func.count(FollowUp.id))
            .filter(FollowUp.status == "Open")
            .scalar()
            or 0
        )

        # Last 6 months labels & counts
        labels = []
        data_points = []
        for i in range(5, -1, -1):
            # compute year/month for (today - i months)
            m = (today.month - i - 1) % 12 + 1
            y = today.year + ((today.month - i - 1) // 12)
            month_start = date(y, m, 1)
            if m == 12:
                next_month = date(y + 1, 1, 1)
            else:
                next_month = date(y, m + 1, 1)

            cnt = (
                db.session.query(db.func.count(Order.id))
                .filter(Order.date >= month_start, Order.date < next_month)
                .scalar()
                or 0
            )
            labels.append(month_start.strftime("%b %Y"))
            data_points.append(cnt)

        # Payment mode split (Paid only)
        mode_rows = (
            db.session.query(Order.payment_mode, db.func.count(Order.id))
            .filter(Order.payment_status == "Paid")
            .group_by(Order.payment_mode)
            .all()
        )
        payment_mode_split = {m or "Unknown": int(c) for (m, c) in mode_rows}

    except Exception:
        # Don't break page if DB missing or schema differs; show zeros
        log.exception("Dashboard generation failed")
        total_orders = total_paid = total_pending = pending_followups = 0
        labels = []
        data_points = []
        payment_mode_split = {}

    log.debug(
        "Dashboard context: total_orders=%s total_paid=%s total_pending=%s pending_followups=%s",
        total_orders,
        total_paid,
        total_pending,
        pending_followups,
    )

    return render_template(
        "dashboard.html",
        business=APP_NAME,
        total_orders=total_orders,
        total_paid=total_paid,
        total_pending=total_pending,
        pending_followups=pending_followups,
        orders_chart_labels=labels,
        orders_chart_data=data_points,
        payment_mode_split=payment_mode_split,
    )
# ...existing code...

# --- Customers -----------------------------------------------------------------
@app.route("/customers", methods=["GET", "POST"])
def customers():
    if request.method == "POST":
        cust_id = (request.form.get("customer_id") or "").strip()
        name = (request.form.get("name") or "").strip()
        if not cust_id or not name:
            flash("Customer ID and Name are required.", "danger")
            return redirect(url_for("customers"))

        c = Customer(
            customer_id=cust_id,
            name=name,
            insta=(request.form.get("insta") or "").strip(),
            phone=(request.form.get("phone") or "").strip(),
            city=(request.form.get("city") or "").strip(),
            ctype=(request.form.get("ctype") or "").strip(),
            notes=(request.form.get("notes") or "").strip(),
        )
        try:
            db.session.add(c)
            db.session.commit()
            flash("Customer added.", "success")
        except Exception as e:
            db.session.rollback()
            log.exception("Add customer failed")
            flash("Error adding customer (maybe duplicate ID).", "danger")
        return redirect(url_for("customers"))

    q = (request.args.get("q") or "").strip()
    query = Customer.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                Customer.customer_id.ilike(like),
                Customer.name.ilike(like),
                Customer.phone.ilike(like),
                Customer.city.ilike(like),
            )
        )
    # recently added first (id desc)
    items = query.order_by(Customer.id.desc()).all()
    return render_template("customers.html", business=APP_NAME, customers=items, q=q)

@app.route("/customers/new")
def customer_form():
    return render_template("customer_form.html", business=APP_NAME)

# --- Orders --------------------------------------------------------------------
@app.route("/orders", methods=["GET", "POST"])
def orders():
    if request.method == "POST":
        data, errors = validate_order_form(request.form)
        if errors:
            for e in errors: flash(e, "danger")
            return redirect(url_for("orders"))

        # order_id: if blank, auto-generate
        order_id = (request.form.get("order_id") or "").strip() or next_human_id("ORD", Order, "order_id")

        o = Order(
            order_id=order_id,
            date=data["date"],
            customer_id=data["customer_id"],
            saree_type=data["saree_type"],
            amount=data["amount"],
            purchase_type=data["purchase_type"],
            payment_status=data["payment_status"],
            payment_mode=data["payment_mode"],
            delivery_status=data["delivery_status"],
            remarks=data["remarks"],
        )
        try:
            db.session.add(o)
            db.session.commit()
            flash("Order added.", "success")
        except Exception:
            db.session.rollback()
            log.exception("Add order failed")
            flash("Error adding order (duplicate ID?).", "danger")

        return redirect(url_for("orders"))

    # GET
    q = (request.args.get("q") or "").strip()
    qry = Order.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(
            db.or_(
                Order.order_id.ilike(like),
                Order.customer_id.ilike(like),
                Order.saree_type.ilike(like),
                Order.payment_status.ilike(like),
                Order.delivery_status.ilike(like),
            )
        )
    # newest first by date then id
    orders_list = qry.order_by(Order.date.desc(), Order.id.desc()).all()

    # For the order form dropdown: customers recent-first
    customers = Customer.query.order_by(Customer.id.desc()).all()
    return render_template("orders.html", business=APP_NAME, orders=orders_list, customers=customers, q=q)

@app.route("/orders/new")
def order_form():
    customers = Customer.query.order_by(Customer.id.desc()).all()
    return render_template("order_form.html", business=APP_NAME, customers=customers)

@app.route("/orders/edit/<order_id>", methods=["GET", "POST"])
def edit_order(order_id):
    order = Order.query.filter_by(order_id=order_id).first()
    if not order:
        flash("Order not found.", "danger")
        return redirect(url_for("orders"))

    if request.method == "POST":
        data, errors = validate_order_form(request.form, is_update=True)
        if errors:
            for e in errors: flash(e, "danger")
            return redirect(url_for("edit_order", order_id=order_id))

        try:
            order.date = data["date"]
            order.customer_id = data["customer_id"]
            order.saree_type = data["saree_type"]
            order.amount = data["amount"]
            order.purchase_type = data["purchase_type"]
            order.payment_status = data["payment_status"]
            order.payment_mode = data["payment_mode"]
            order.delivery_status = data["delivery_status"]
            order.remarks = data["remarks"]

            db.session.commit()
            flash("Order updated.", "success")
        except Exception:
            db.session.rollback()
            log.exception("Update order failed")
            flash("Error updating order.", "danger")

        return redirect(url_for("orders"))

    customers = Customer.query.order_by(Customer.id.desc()).all()
    return render_template("order_form.html", business=APP_NAME, customers=customers, order=order)

# --- Follow-ups ----------------------------------------------------------------
@app.route("/followups", methods=["GET", "POST"])
def followups():
    if request.method == "POST":
        c_id = (request.form.get("customer_id") or "").strip()
        if not c_id:
            flash("Customer is required.", "danger")
            return redirect(url_for("followups"))
        f = FollowUp(
            customer_id=c_id,
            followup_date=parse_date(request.form.get("followup_date")),
            notes=(request.form.get("notes") or "").strip(),
            status=(request.form.get("status") or "Open").strip(),
        )
        try:
            db.session.add(f)
            db.session.commit()
            flash("Follow-up added.", "success")
        except Exception:
            db.session.rollback()
            log.exception("Add followup failed")
            flash("Error adding follow-up.", "danger")
        return redirect(url_for("followups"))

    q = (request.args.get("q") or "").strip()
    qry = FollowUp.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(
            db.or_(
                FollowUp.customer_id.ilike(like),
                FollowUp.notes.ilike(like),
                FollowUp.status.ilike(like),
            )
        )
    items = qry.order_by(FollowUp.followup_date.desc(), FollowUp.id.desc()).all()
    customers = Customer.query.order_by(Customer.id.desc()).all()
    return render_template("followups.html", business=APP_NAME, followups=items, customers=customers, q=q)

# --- Payments ------------------------------------------------------------------
@app.route("/payments")
def payments():
    # Totals (all-time & current month)
    today = date.today()
    month_start = date(today.year, today.month, 1)

    paid_total = db.session.query(db.func.coalesce(db.func.sum(Order.amount), 0))\
        .filter(Order.payment_status == "Paid").scalar() or 0
    pending_total = db.session.query(db.func.coalesce(db.func.sum(Order.amount), 0))\
        .filter(Order.payment_status == "Pending").scalar() or 0

    paid_month = db.session.query(db.func.coalesce(db.func.sum(Order.amount), 0))\
        .filter(Order.payment_status == "Paid", Order.date >= month_start).scalar() or 0
    pending_month = db.session.query(db.func.coalesce(db.func.sum(Order.amount), 0))\
        .filter(Order.payment_status == "Pending", Order.date >= month_start).scalar() or 0

    # Mode split (Paid only)
    mode_rows = (
        db.session.query(Order.payment_mode, db.func.count(Order.id))
        .filter(Order.payment_status == "Paid", Order.payment_mode.in_(("UPI", "Cash")))
        .group_by(Order.payment_mode)
        .all()
    )
    mode_split = {m or "Unknown": c for (m, c) in mode_rows}

    return render_template(
        "payments.html",
        business=APP_NAME,
        paid_total=paid_total,
        pending_total=pending_total,
        paid_month=paid_month,
        pending_month=pending_month,
        mode_split=mode_split,
    )

# --- Reports & Settings (basic placeholders that use your templates) -----------
@app.route("/reports")
def reports():
    return render_template("reports.html", business=APP_NAME)

@app.route("/settings", methods=["GET", "POST"])
def settings():
    # (Optional: future global settings)
    if request.method == "POST":
        flash("Settings saved.", "success")
        return redirect(url_for("settings"))
    return render_template("settings.html", business=APP_NAME)

# --- App init ------------------------------------------------------------------
if __name__ == "__main__":
    # Ensure DB & tables exist
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=False)

