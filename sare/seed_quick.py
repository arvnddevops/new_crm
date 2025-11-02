import random, string, datetime
from saree_crm_flask_app import app, db, Customer, Order

def has_col(model, name): return name in model.__table__.columns
def unique_customer_code(prefix="CUST"):
    # generate CUST000001, CUST000002, ... until free
    n = 1
    while True:
        code = f"{prefix}{n:06d}"
        if not Customer.query.filter_by(customer_id=code).first():
            return code
        n += 1

def rand_name():
    first = ["Anita","Bhavya","Charu","Divya","Eesha","Farah","Gita","Hema","Ishita","Jaya","Kajal",
             "Lakshmi","Meera","Nisha","Oviya","Pooja","Rani","Sarita","Tanya","Uma","Varsha","Yamini","Zara"]
    last  = ["Agarwal","Bhat","Chandra","Desai","Iyer","Jain","Kapoor","Khanna","Menon","Nair",
             "Patel","Rao","Reddy","Shah","Sharma","Singh","Verma"]
    return f"{random.choice(first)} {random.choice(last)}"

def rand_phone(): return "9" + "".join(random.choice(string.digits) for _ in range(9))
def rand_city():  return random.choice(["Hyderabad","Secunderabad","Warangal","Vijayawada","Guntur","Nizamabad"])
def rand_amount(): return random.choice([799,999,1199,1299,1499,1699,1799,1999,2199,2499,2799,2999,3299,3499,3999])
def rand_type(): return random.choice(["Silk","Cotton","Chiffon","Georgette","Linen","Kanchipuram","Banarasi","Organza","Paithani","Kota"])
def rand_purchase(): return random.choice(["Online","Offline"])
def rand_date(days=90): 
    from datetime import date, timedelta
    return date.today() - timedelta(days=random.randint(0, days))

with app.app_context():
    db.create_all()

    # ---- Create ~60 customers with required customer_id ----
    with app.app_context():
        need = max(0, 60 - Customer.query.count())
        added_customers = []
        for _ in range(need):
            payload = {}
            if has_col(Customer, "customer_id"):
                payload["customer_id"] = unique_customer_code()
            # Add only columns that actually exist
            if has_col(Customer, "name"):  payload["name"]  = rand_name()
            if has_col(Customer, "phone"): payload["phone"] = rand_phone()
            if has_col(Customer, "city"):  payload["city"]  = rand_city()
            if has_col(Customer, "remarks"): payload["remarks"] = random.choice(["","Regular","Referred","New"])
            c = Customer(**payload)
            db.session.add(c)
            added_customers.append(c)
        if added_customers:
            db.session.commit()
        customers = Customer.query.all()

    # ---- Create ~200 orders referencing FK ----
    with app.app_context():
        order_cols = set(Order.__table__.columns.keys())
        fk = "customer_id" if "customer_id" in order_cols else None

        created = 0
        for _ in range(200):
            cust = random.choice(customers)
            data = {}
            # FK
            if fk:
                # use customer.customer_id if that’s the FK; else try id
                val = getattr(cust, "customer_id", getattr(cust, "id", None))
                data[fk] = val
            # typical fields if present
            if "order_id" in order_cols:
                today = datetime.date.today().strftime("%Y%m%d")
                data["order_id"] = f"ORD{today}-{random.randint(10000,99999)}"
            if "date" in order_cols: data["date"] = rand_date()
            if "saree_type" in order_cols: data["saree_type"] = rand_type()
            if "amount" in order_cols: data["amount"] = int(rand_amount())
            if "purchase_type" in order_cols: data["purchase_type"] = rand_purchase()
            if "payment_status" in order_cols:
                paid = random.random() < 0.7
                data["payment_status"] = "Paid" if paid else "Pending"
            if "payment_mode" in order_cols:
                data["payment_mode"] = "UPI" if data.get("payment_status") == "Paid" else "Pending"
            if "delivery_status" in order_cols:
                if data.get("payment_status") == "Paid":
                    data["delivery_status"] = random.choice(["Delivered","Shipped","Pending"])
                else:
                    data["delivery_status"] = random.choice(["Pending","Cancelled"])
            if "remarks" in order_cols: data["remarks"] = random.choice(["","Gift","Urgent","Repeat buyer","First-time buyer"])
            db.session.add(Order(**data))
            created += 1
            if created % 100 == 0: db.session.commit()
        db.session.commit()
        print(f"✅ Seed complete. customers={len(customers)} orders_added={created}")
