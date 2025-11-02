import random, string, datetime
from itertools import count
from saree_crm_flask_app import app, db, Customer, Order

# -------- helpers --------
def rand_name():
    first = ["Anita","Bhavya","Charu","Divya","Eesha","Farah","Gita","Hema","Ishita","Jaya","Kajal",
             "Lakshmi","Meera","Nisha","Oviya","Pooja","Rani","Sarita","Tanya","Uma","Varsha","Yamini","Zara"]
    last  = ["Agarwal","Bhat","Chandra","Desai","Iyer","Jain","Kapoor","Khanna","Menon","Nair",
             "Patel","Rao","Reddy","Shah","Sharma","Singh","Verma"]
    return f"{random.choice(first)} {random.choice(last)}"

def rand_phone():
    return "9" + "".join(random.choice(string.digits) for _ in range(9))

def rand_type():
    return random.choice(["Silk","Cotton","Chiffon","Georgette","Linen","Kanchipuram","Banarasi","Organza","Paithani","Kota"])

def rand_purchase_type():
    return random.choice(["Online","Offline"])

def rand_amount():
    return random.choice([799,999,1199,1299,1499,1699,1799,1999,2199,2499,2799,2999,3299,3499,3999])

def rand_date_within(days_back=90):
    return (datetime.date.today() - datetime.timedelta(days=random.randint(0, days_back)))

def seq_order_id(start=10000):
    for i in count(start):
        yield f"ORD{datetime.date.today().strftime('%Y%m%d')}-{i}"

def pick_payment():
    # 70% Paid, 30% Pending
    paid = random.random() < 0.7
    if paid:
        return "Paid", random.choice(["UPI","Cash"])
    return "Pending", "Pending"

def pick_delivery(pay_status):
    if pay_status == "Pending":
        return random.choices(["Pending","Cancelled"], weights=[95,5])[0]
    return random.choices(["Delivered","Shipped","Pending"], weights=[70,25,5])[0]

def model_columns(model):
    return set(c.name for c in model.__table__.columns)

def filtered_kwargs(allowed, data):
    return {k:v for k,v in data.items() if k in allowed}

# -------- seeding --------
def ensure_demo_customers(target=60):
    cols = model_columns(Customer)
    existing = Customer.query.count()
    to_add = max(0, target - existing)
    created = 0
    for _ in range(to_add):
        candidate = {
            "name": rand_name(),
            "phone": rand_phone(),
            # optional fields if they exist in your model
            "email": f"user{random.randint(1000,9999)}@example.com",
            "remarks": random.choice(["","Regular","Referred","New"]),
            "city": random.choice(["Hyderabad","Secunderabad","Warangal","Vijayawada","Guntur","Nizamabad"]),
        }
        c = Customer(**filtered_kwargs(cols, candidate))
        db.session.add(c)
        created += 1
    if created:
        db.session.commit()
    # newest first to match your UI
    try:
        return Customer.query.order_by(Customer.id.desc()).all()
    except Exception:
        # if no "id" use whatever exists (fallback: no order)
        return Customer.query.all()

def seed_orders(customers, n=250):
    if not customers:
        return 0
    order_cols = model_columns(Order)

    # figure out customer PK/FK names
    # When creating Order, use FK field name if present; otherwise use 'customer_id' if exists.
    fk_field = "customer_id" if "customer_id" in order_cols else None

    start_id = (db.session.query(db.func.count(Order.id)).scalar() or 0) + 10000
    gen_oid = seq_order_id(start=start_id)

    batch = 0
    created = 0
    for _ in range(n):
        cust = random.choice(customers)
        # determine actual customer identifier value
        cust_pk_val = getattr(cust, "customer_id", getattr(cust, "id", None))

        pay_status, pay_mode = pick_payment()
        candidate = {
            "order_id": next(gen_oid) if "order_id" in order_cols else None,
            "date": rand_date_within(90) if "date" in order_cols else None,
            "saree_type": rand_type() if "saree_type" in order_cols else None,
            "amount": int(rand_amount()) if "amount" in order_cols else None,
            "purchase_type": rand_purchase_type() if "purchase_type" in order_cols else None,
            "payment_status": pay_status if "payment_status" in order_cols else None,
            "payment_mode": pay_mode if "payment_mode" in order_cols else None,
            "delivery_status": pick_delivery(pay_status) if "delivery_status" in order_cols else None,
            "remarks": random.choice(["","Gift","Urgent","Repeat buyer","First-time buyer"]) if "remarks" in order_cols else None,
        }

        # set FK if we found one
        if fk_field and cust_pk_val is not None:
            candidate[fk_field] = cust_pk_val

        # drop None keys and keys not in model
        clean = {k:v for k,v in candidate.items() if v is not None}
        clean = filtered_kwargs(order_cols, clean)

        o = Order(**clean)
        db.session.add(o)
        batch += 1
        created += 1
        if batch >= 100:
            db.session.commit()
            batch = 0
    if batch:
        db.session.commit()
    return created

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        customers = ensure_demo_customers(60)
        made = seed_orders(customers, 250)
        print(f"✅ Seed complete: customers_total={Customer.query.count()} orders_added={made}")
