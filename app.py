from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from datetime import datetime, date, timedelta
from openpyxl import Workbook
from sqlalchemy import func
from xhtml2pdf import pisa
import io, secrets, os
from io import BytesIO
from werkzeug.utils import secure_filename

# Authentication and Security Imports
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# Make sure the User model is imported from your models file
from models import db, User, Product, Expense, Debt, Customer, Sale, SaleItem

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = secrets.token_hex(16)
# Configuration for file uploads
UPLOAD_FOLDER = 'static/profile_pics'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

db.init_app(app)

# Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'
login_manager.login_message = "Please log in to access this page."

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()
    # Create upload folder if it doesn't exist
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)

# ============================ AUTHENTICATION & PROFILE ROUTES ============================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('inventory'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            return redirect(url_for('inventory'))
        else:
            flash('Login Unsuccessful. Please check username and password', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('inventory'))
    if request.method == 'POST':
        username = request.form.get('username')
        full_name = request.form.get('full_name') # Get the full name from the form
        password = request.form.get('password')

        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'warning')
            return redirect(url_for('register'))
            
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        # Add the full_name when creating the new user
        new_user = User(username=username, full_name=full_name, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('Account created! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

def save_picture(form_picture):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], picture_fn)
    form_picture.save(picture_path)
    return picture_fn

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        form_name = request.form.get('form_name')
        
        if form_name == 'update_profile':
            current_user.full_name = request.form.get('full_name')
            if 'profile_image' in request.files:
                picture_file = request.files['profile_image']
                if picture_file.filename != '':
                    if current_user.profile_image != 'default.jpg':
                        old_pic_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], current_user.profile_image)
                        if os.path.exists(old_pic_path):
                            os.remove(old_pic_path)
                    picture_filename = save_picture(picture_file)
                    current_user.profile_image = picture_filename
            db.session.commit()
            flash('Your profile has been updated!', 'success')
            return redirect(url_for('profile'))

        elif form_name == 'change_password':
            old_password = request.form.get('old_password')
            new_password = request.form.get('new_password')
            confirm_new_password = request.form.get('confirm_new_password')
            if not check_password_hash(current_user.password, old_password):
                flash('Current password incorrect.', 'danger')
            elif new_password != confirm_new_password:
                flash('New passwords do not match.', 'danger')
            else:
                current_user.password = generate_password_hash(new_password, method='pbkdf2:sha256')
                db.session.commit()
                flash('Your password has been updated!', 'success')
            return redirect(url_for('profile'))
            
    return render_template('profile.html')

@app.route('/backup/database')
@login_required
def backup_database():
    try:
        db_path = os.path.join(app.instance_path, 'database.db')
        if not os.path.exists(db_path):
            flash("Database file not found in the instance folder.", "danger")
            return redirect(url_for('profile'))
        return send_file(db_path, as_attachment=True)
    except Exception as e:
        flash(f"Error backing up database: {e}", "danger")
        return redirect(url_for('profile'))

# ============================ MAIN APP ROUTES ============================
@app.route('/')
@login_required
def home():
    return redirect(url_for('inventory'))

@app.route('/inventory', methods=['GET'])
@login_required
def inventory():
    products = Product.query.all()
    customers = Customer.query.all()
    cart = session.get('cart', [])
    cart_total = sum(item['total_price'] for item in cart)
    show_receipt = session.pop('show_receipt', False)
    receipt_data = {
        "items": session.pop('receipt_items', []),
        "total": session.pop('receipt_total', 0),
        "date": session.pop('receipt_date', ""),
        "customer": session.pop('receipt_customer', "Walk-in Customer")
    } if show_receipt else None
    return render_template('inventory.html', products=products, customers=customers, cart=cart, cart_total=cart_total, receipt=receipt_data)

@app.route('/add_to_cart', methods=['POST'])
@login_required
def add_to_cart():
    product_id = int(request.form['product_id'])
    quantity = int(request.form['quantity'])
    product = Product.query.get_or_404(product_id)
    if quantity > product.quantity:
        flash(f"Only {product.quantity} units of {product.name} available!", "warning")
        return redirect(url_for('inventory'))
    cart = session.get('cart', [])
    for item in cart:
        if item['product_id'] == product_id:
            item['quantity'] += quantity
            item['total_price'] = item['quantity'] * item['unit_price']
            break
    else:
        cart.append({
            'product_id': product.id,
            'product_name': product.name,
            'unit_price': product.selling_price,
            'quantity': quantity,
            'total_price': quantity * product.selling_price
        })
    session['cart'] = cart
    flash(f"{product.name} added to cart.", "success")
    return redirect(url_for('inventory'))

@app.route('/remove_from_cart/<int:index>')
@login_required
def remove_from_cart(index):
    cart = session.get('cart', [])
    if 0 <= index < len(cart):
        removed = cart.pop(index)
        session['cart'] = cart
        flash(f"Removed {removed['product_name']} from cart.", "info")
    return redirect(url_for('inventory'))

@app.route('/update_cart_quantity', methods=['POST'])
@login_required
def update_cart_quantity():
    product_id = int(request.form['product_id'])
    quantity = int(request.form['quantity'])
    cart = session.get('cart', [])
    for item in cart:
        if item['product_id'] == product_id:
            item['quantity'] = quantity
            item['total_price'] = quantity * item['unit_price']
            break
    session['cart'] = cart
    flash("Quantity updated.", "success")
    return redirect(url_for('inventory'))

@app.route('/finalize_purchase', methods=['POST'])
@login_required
def finalize_purchase():
    customer_type = request.form['customer_type']
    customer_id = request.form.get('customer_id')
    cart = session.get('cart', [])
    if not cart:
        flash("Cart is empty!", "warning")
        return redirect(url_for('inventory'))
    customer_name = "Walk-in Customer"
    if customer_type == 'registered' and customer_id:
        customer_obj = Customer.query.get(int(customer_id))
        if customer_obj:
            customer_name = customer_obj.name
    sale = Sale(
        customer_id=int(customer_id) if customer_type == 'registered' and customer_id else None,
        total_amount=sum(item['total_price'] for item in cart),
        date=datetime.now()
    )
    db.session.add(sale)
    db.session.commit()
    for item in cart:
        sale_item = SaleItem(
            sale_id=sale.id,
            product_id=item['product_id'],
            quantity=item['quantity'],
            unit_price=item['unit_price']
        )
        db.session.add(sale_item)
        product = Product.query.get(item['product_id'])
        product.quantity -= item['quantity']
    db.session.commit()
    session['receipt_items'] = cart
    session['receipt_total'] = sale.total_amount
    session['receipt_date'] = sale.date.strftime("%Y-%m-%d %H:%M:%S")
    session['receipt_customer'] = customer_name
    session['show_receipt'] = True
    session.pop('cart', None)
    flash("Purchase completed successfully!", "success")
    return redirect(url_for('inventory'))

# ============================ PRODUCTS PAGE ============================
@app.route('/products', methods=['GET', 'POST'])
@login_required
def products():
    if request.method == 'POST':
        name = request.form['name']
        quantity = int(request.form['quantity'])
        selling_price = float(request.form['selling_price'])
        cost_price = float(request.form['cost_price'])
        new_product = Product(name=name, quantity=quantity, selling_price=selling_price, cost_price=cost_price)
        db.session.add(new_product)
        db.session.commit()
        return redirect(url_for('products'))
    all_products = Product.query.all()
    return render_template('products.html', products=all_products)

@app.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    if request.method == 'POST':
        product.name = request.form['name']
        product.quantity = int(request.form['quantity'])
        product.selling_price = float(request.form['selling_price'])
        product.cost_price = float(request.form['cost_price'])
        db.session.commit()
        flash(f"Product '{product.name}' updated successfully.", "success")
        return redirect(url_for('products')) 
    return render_template('edit_product.html', product=product)

@app.route('/delete_product/<int:product_id>', methods=['POST'])
@login_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    if SaleItem.query.filter_by(product_id=product.id).first():
        flash(f"Cannot delete '{product.name}' as it has been sold before.", "danger")
        return redirect(url_for('products'))
    db.session.delete(product)
    db.session.commit()
    flash(f"Product '{product.name}' has been deleted.", "success")
    return redirect(url_for('products')) 

# ============================ CUSTOMERS ============================
@app.route('/customers', methods=['GET', 'POST'])
@login_required
def customers():
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form.get('phone')
        new_customer = Customer(name=name, phone=phone)
        db.session.add(new_customer)
        db.session.commit()
        flash("Customer added successfully!", "success")
        return redirect(url_for('customers'))
    all_customers = Customer.query.all()
    return render_template('customers.html', customers=all_customers)

@app.route('/edit_customer/<int:customer_id>', methods=['GET', 'POST'])
@login_required
def edit_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    if request.method == 'POST':
        customer.name = request.form['name']
        customer.phone = request.form['phone']
        db.session.commit()
        flash("Customer updated successfully!", "success")
        return redirect(url_for('customers'))
    return render_template('edit_customer.html', customer=customer)

@app.route('/delete_customer/<int:customer_id>', methods=['POST'])
@login_required
def delete_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    if customer.sales:
        flash("Cannot delete customer with existing sales records.", "danger")
        return redirect(url_for('customers'))
    db.session.delete(customer)
    db.session.commit()
    flash("Customer deleted.", "success")
    return redirect(url_for('customers'))

# ============================ DEBTS ============================
@app.route('/debts', methods=['GET', 'POST'])
@login_required
def debts():
    if request.method == 'POST':
        customer_name = request.form['customer_name']
        amount = float(request.form['amount'])
        new_debt = Debt(
            customer_name=customer_name, 
            original_amount=amount, 
            status='pending', 
            date=datetime.now()
        )
        db.session.add(new_debt)
        db.session.commit()
        flash("New debt added successfully.", "success")
        return redirect(url_for('debts'))
    all_debts = Debt.query.order_by(Debt.status, Debt.date.desc()).all()
    return render_template('debts.html', debts=all_debts)

@app.route('/pay_debt/<int:debt_id>', methods=['POST'])
@login_required
def pay_debt(debt_id):
    debt = Debt.query.get_or_404(debt_id)
    payment_amount = float(request.form['payment_amount'])
    if payment_amount <= 0:
        flash("Payment amount must be positive.", "danger")
        return redirect(url_for('debts'))
    if payment_amount > debt.balance:
        flash(f"Payment cannot be more than the remaining balance of ₦{debt.balance:.2f}.", "danger")
        return redirect(url_for('debts'))
    debt.amount_paid += payment_amount
    if debt.balance <= 0:
        debt.status = 'paid'
        debt.amount_paid = debt.original_amount
        flash("Debt has been fully paid!", "success")
    else:
        flash(f"Payment of ₦{payment_amount:.2f} recorded successfully.", "success")
    db.session.commit()
    return redirect(url_for('debts'))

@app.route('/edit_debt/<int:debt_id>', methods=['GET', 'POST'])
@login_required
def edit_debt(debt_id):
    debt = Debt.query.get_or_404(debt_id)
    if request.method == 'POST':
        debt.customer_name = request.form['customer_name']
        debt.original_amount = float(request.form['original_amount'])
        debt.amount_paid = float(request.form['amount_paid'])
        if debt.balance <= 0:
            debt.status = 'paid'
        else:
            debt.status = 'pending'
        db.session.commit()
        flash("Debt updated successfully.", "success")
        return redirect(url_for('debts'))
    return render_template('edit_debt.html', debt=debt)

@app.route('/delete_debt/<int:debt_id>', methods=['POST'])
@login_required
def delete_debt(debt_id):
    debt = Debt.query.get_or_404(debt_id)
    db.session.delete(debt)
    db.session.commit()
    flash("Debt record deleted.", "info")
    return redirect(url_for('debts'))

# ============================ EXPENSES ============================
@app.route('/expenses', methods=['GET', 'POST'])
@login_required
def expenses():
    if request.method == 'POST':
        description = request.form['description']
        amount = float(request.form['amount'])
        category = request.form['category']
        new_expense = Expense(description=description, amount=amount, category=category, date=datetime.now())
        db.session.add(new_expense)
        db.session.commit()
        return redirect(url_for('expenses'))
    all_expenses = Expense.query.order_by(Expense.date.desc()).all()
    return render_template('expenses.html', expenses=all_expenses)

@app.route('/edit_expense/<int:expense_id>', methods=['GET', 'POST'])
@login_required
def edit_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    if request.method == 'POST':
        expense.description = request.form['description']
        expense.amount = float(request.form['amount'])
        expense.category = request.form['category']
        db.session.commit()
        return redirect(url_for('expenses'))
    return render_template('edit_expense.html', expense=expense)

@app.route('/delete_expense/<int:expense_id>', methods=['POST'])
@login_required
def delete_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    db.session.delete(expense)
    db.session.commit()
    return redirect(url_for('expenses'))

# ============================ REPORTS ============================
@app.route('/reports')
@login_required
def reports():
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    try:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else date.today()
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else date(end_date.year, end_date.month, 1)
    except ValueError:
        flash("Invalid date format. Please use YYYY-MM-DD.", "danger")
        start_date = date(date.today().year, date.today().month, 1)
        end_date = date.today()
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())
    sales_query = Sale.query.filter(Sale.date.between(start_datetime, end_datetime))
    expenses_query = Expense.query.filter(Expense.date.between(start_datetime, end_datetime))
    gross_revenue = sales_query.with_entities(func.sum(Sale.total_amount)).scalar() or 0.0
    cogs = 0.0
    for sale in sales_query.all():
        for item in sale.items:
            product = Product.query.get(item.product_id)
            if product:
                cogs += (product.cost_price * item.quantity)
    total_expenses = expenses_query.with_entities(func.sum(Expense.amount)).scalar() or 0.0
    gross_profit = gross_revenue - cogs
    net_profit = gross_profit - total_expenses
    pending_debt = db.session.query(func.sum(Debt.original_amount - Debt.amount_paid)).filter(Debt.status == 'pending').scalar() or 0.0
    report_data = {
        "gross_revenue": gross_revenue, "cogs": cogs,
        "gross_profit": gross_profit, "total_expenses": total_expenses,
        "net_profit": net_profit, "pending_debt": pending_debt
    }
    return render_template('reports.html', report=report_data, start_date=start_date.isoformat(), end_date=end_date.isoformat())

# ============================ EXPORT SALES ============================
@app.route('/export_sales')
@login_required
def export_sales():
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    sales_query = Sale.query
    
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.combine(datetime.strptime(end_date_str, '%Y-%m-%d').date(), datetime.max.time())
            sales_query = sales_query.filter(Sale.date.between(start_date, end_date))
        except ValueError:
            flash("Invalid date format for export. Exporting all sales.", "warning")

    sales = sales_query.order_by(Sale.date.desc()).all()
    
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sales Report"

    sheet.append(["Date", "Customer", "Total Amount"])
    for sale in sales:
        customer_name = sale.customer.name if sale.customer else "Walk-in Customer"
        sheet.append([
            sale.date.strftime("%Y-%m-%d %H:%M:%S"),
            customer_name,
            f"{sale.total_amount:.2f}"
        ])

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    
    filename = f"sales_report_{start_date_str}_to_{end_date_str}.xlsx" if start_date_str and end_date_str else "sales_report_all.xlsx"

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )

# ============================ INVOICES ============================
@app.route('/invoices')
@login_required
def invoices():
    customer_filter = request.args.get('customer', '').strip().lower()
    date_filter = request.args.get('date')
    query = Sale.query.order_by(Sale.date.desc())
    if customer_filter:
        query = query.join(Customer).filter(func.lower(Customer.name).contains(customer_filter))
    if date_filter:
        try:
            parsed_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            query = query.filter(func.date(Sale.date) == parsed_date)
        except ValueError:
            flash("Invalid date format", "danger")
    sales = query.all()
    return render_template('invoices.html', sales=sales)

@app.route('/download_receipt/<int:sale_id>')
@login_required
def download_receipt(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    return render_template('receipt_download.html', sale=sale)

@app.route('/download_receipt_pdf/<int:sale_id>')
@login_required
def download_receipt_pdf(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    html = render_template('receipt_download.html', sale=sale)
    pdf = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=pdf)
    if pisa_status.err:
        return "PDF generation failed"
    pdf.seek(0)
    return send_file(pdf, mimetype='application/pdf', as_attachment=True, download_name=f"receipt_{sale.id}.pdf")

# ============================ MAIN ============================
if __name__ == '__main__':
    app.run(debug=True)
