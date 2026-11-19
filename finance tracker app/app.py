import os
import csv
import io
from datetime import datetime, date
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for, 
    flash, session, jsonify, Response, g
)
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
from mysql.connector import Error

from config import Config
from db import get_db_cursor, execute_query, execute_procedure, check_db_health

app = Flask(__name__)
app.config.from_object(Config)

# ------------------------------------------------------------------------------
# Authentication Helper Decorators
# ------------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please sign in to access your financial dashboard.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please sign in first.', 'warning')
            return redirect(url_for('login'))
        if session.get('user_role') != 'Admin':
            flash('Access restricted to administrators only.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# ------------------------------------------------------------------------------
# Context Processors (Inject Global Template Variables)
# ------------------------------------------------------------------------------

@app.context_processor
def inject_global_data():
    now = datetime.now()
    return {
        'current_year': now.year,
        'current_month': now.month,
        'current_date_str': now.strftime('%Y-%m-%d'),
        'user_name': session.get('user_name', 'Guest'),
        'user_role': session.get('user_role', 'User'),
        'is_authenticated': 'user_id' in session
    }

# ------------------------------------------------------------------------------
# Error Handlers
# ------------------------------------------------------------------------------

@app.errorhandler(RuntimeError)
def handle_db_connection_error(error):
    error_msg = str(error)
    if "MySQL" in error_msg or "workbench_setup.sql" in error_msg or "Authentication Failed" in error_msg:
        return render_template(
            'db_error.html', 
            error_message=error_msg,
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            user=Config.DB_USER,
            database=Config.DB_NAME
        ), 503
    return render_template('base.html', error_text=error_msg), 500

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

# ------------------------------------------------------------------------------
# Authentication Routes (Login, Register, Logout)
# ------------------------------------------------------------------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Please provide both email and password.', 'danger')
            return render_template('login.html')

        try:
            user = execute_query(
                "SELECT user_id, name, email, password_hash, role FROM Users WHERE email = %s",
                (email,),
                fetch='one'
            )

            if user and check_password_hash(user['password_hash'], password):
                session['user_id'] = user['user_id']
                session['user_name'] = user['name']
                session['user_email'] = user['email']
                session['user_role'] = user['role']
                flash(f'Welcome back, {user["name"]}!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid email address or password. Please try again.', 'danger')
        except Exception as e:
            flash(f'Authentication error: {str(e)}', 'danger')

    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    name = request.form.get('reg_name', '').strip()
    email = request.form.get('reg_email', '').strip().lower()
    password = request.form.get('reg_password', '')
    confirm_password = request.form.get('reg_confirm_password', '')

    if not name or not email or not password:
        flash('All registration fields are required.', 'danger')
        return redirect(url_for('login'))

    if password != confirm_password:
        flash('Passwords do not match.', 'danger')
        return redirect(url_for('login'))

    if len(password) < 6:
        flash('Password must be at least 6 characters long.', 'danger')
        return redirect(url_for('login'))

    try:
        # Check if email is already registered
        existing = execute_query("SELECT user_id FROM Users WHERE email = %s", (email,), fetch='one')
        if existing:
            flash('An account with this email already exists. Please sign in.', 'warning')
            return redirect(url_for('login'))

        hashed = generate_password_hash(password)
        
        with get_db_cursor(commit=True) as (cursor, conn):
            # 1. Insert new user
            cursor.execute(
                "INSERT INTO Users (name, email, password_hash, role) VALUES (%s, %s, %s, 'User')",
                (name, email, hashed)
            )
            new_user_id = cursor.lastrowid

            # 2. Provision default payment instruments
            default_methods = [('UPI',), ('Debit Card',), ('Net Banking',), ('Cash',)]
            cursor.executemany(
                f"INSERT INTO PaymentMethods (user_id, method_name) VALUES ({new_user_id}, %s)",
                default_methods
            )

            # 3. Provision default categories (3 Income, 6 Expense)
            default_categories = [
                ('Salary', 'Income'),
                ('Freelance & Consulting', 'Income'),
                ('Dividends & Investments', 'Income'),
                ('Housing & Rent', 'Expense'),
                ('Groceries & Dining', 'Expense'),
                ('Utilities & Internet', 'Expense'),
                ('Entertainment & Streaming', 'Expense'),
                ('Transportation & Fuel', 'Expense'),
                ('Healthcare & Fitness', 'Expense')
            ]
            cursor.executemany(
                f"INSERT INTO Categories (user_id, category_name, category_type) VALUES ({new_user_id}, %s, %s)",
                default_categories
            )

        flash('Registration successful! You can now sign in with your credentials.', 'success')
        return redirect(url_for('login'))

    except Exception as e:
        flash(f'Registration failed: {str(e)}', 'danger')
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out securely.', 'info')
    return redirect(url_for('login'))

# ------------------------------------------------------------------------------
# Dashboard Module
# ------------------------------------------------------------------------------

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    user_id = session['user_id']
    now = datetime.now()
    cur_month = now.month
    cur_year = now.year

    try:
        # 1. Query Stored Functions for KPI calculations
        kpi_row = execute_query(
            """
            SELECT 
                fn_CalculateMonthlyIncome(%s, %s, %s) AS gross_income,
                fn_CalculateMonthlyExpenses(%s, %s, %s) AS total_expenses,
                fn_CalculateMonthlySavings(%s, %s, %s) AS net_savings
            """,
            (user_id, cur_month, cur_year,
             user_id, cur_month, cur_year,
             user_id, cur_month, cur_year),
            fetch='one'
        )

        gross_income = float(kpi_row['gross_income'] or 0.0)
        total_expenses = float(kpi_row['total_expenses'] or 0.0)
        net_savings = float(kpi_row['net_savings'] or 0.0)
        savings_rate = round((net_savings / gross_income * 100), 1) if gross_income > 0 else 0.0

        # 2. Query Monthly Subscription Load
        sub_load_row = execute_query(
            """
            SELECT 
                COUNT(*) AS active_count,
                COALESCE(SUM(
                    CASE 
                        WHEN billing_cycle = 'Monthly' THEN amount 
                        WHEN billing_cycle = 'Yearly' THEN ROUND(amount / 12.0, 2)
                        ELSE 0.00
                    END
                ), 0.00) AS monthly_burden
            FROM Subscriptions
            WHERE user_id = %s AND status = 'Active'
            """,
            (user_id,),
            fetch='one'
        )
        active_subs_count = sub_load_row['active_count'] or 0
        monthly_sub_burden = float(sub_load_row['monthly_burden'] or 0.0)

        # 3. Upcoming Renewals within 7 days
        upcoming_renewals = execute_query(
            """
            SELECT 
                subscription_id, 
                subscription_name, 
                amount, 
                billing_cycle, 
                next_renewal_date,
                DATEDIFF(next_renewal_date, CURDATE()) AS days_left
            FROM Subscriptions
            WHERE user_id = %s 
              AND status = 'Active'
              AND next_renewal_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY)
            ORDER BY next_renewal_date ASC
            """,
            (user_id,),
            fetch='all'
        ) or []

        # 4. Category Spending Breakdown (from View: vw_CategorySpendingSummary)
        category_spending = execute_query(
            """
            SELECT category_name, total_spent, transaction_count
            FROM vw_CategorySpendingSummary
            WHERE user_id = %s AND month = %s AND year = %s
            ORDER BY total_spent DESC
            """,
            (user_id, cur_month, cur_year),
            fetch='all'
        ) or []

        # 5. Budget Utilization Quick Status (from View: vw_BudgetUtilization)
        budget_utilization = execute_query(
            """
            SELECT 
                budget_id, category_name, limit_amount, 
                actual_spent, remaining_balance, 
                utilization_percentage, budget_status
            FROM vw_BudgetUtilization
            WHERE user_id = %s AND month = %s AND year = %s
            ORDER BY utilization_percentage DESC
            LIMIT 5
            """,
            (user_id, cur_month, cur_year),
            fetch='all'
        ) or []

        # 6. Recent Transactions (last 6 ledger entries)
        recent_transactions = execute_query(
            """
            SELECT 
                t.transaction_id, 
                t.amount, 
                t.transaction_type, 
                t.transaction_date, 
                t.description,
                c.category_name, 
                pm.method_name
            FROM Transactions t
            JOIN Categories c ON t.category_id = c.category_id
            JOIN PaymentMethods pm ON t.payment_method_id = pm.payment_method_id
            WHERE t.user_id = %s
            ORDER BY t.transaction_date DESC, t.transaction_id DESC
            LIMIT 6
            """,
            (user_id,),
            fetch='all'
        ) or []

        # 7. 6-Month Cash Flow Trend Data for Chart
        trend_data = execute_query(
            """
            SELECT 
                DATE_FORMAT(t.transaction_date, '%b %Y') AS month_label,
                YEAR(t.transaction_date) AS yr,
                MONTH(t.transaction_date) AS mo,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'Income' THEN t.amount ELSE 0 END), 0) AS income,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'Expense' THEN t.amount ELSE 0 END), 0) AS expense
            FROM Transactions t
            WHERE t.user_id = %s
              AND t.transaction_date >= DATE_SUB(CURDATE(), INTERVAL 5 MONTH)
            GROUP BY yr, mo, month_label
            ORDER BY yr ASC, mo ASC
            """,
            (user_id,),
            fetch='all'
        ) or []

        # Payment methods & expense categories for quick modal
        payment_methods = execute_query(
            "SELECT payment_method_id, method_name FROM PaymentMethods WHERE user_id = %s ORDER BY method_name",
            (user_id,),
            fetch='all'
        ) or []

        categories = execute_query(
            "SELECT category_id, category_name, category_type FROM Categories WHERE user_id = %s ORDER BY category_type, category_name",
            (user_id,),
            fetch='all'
        ) or []

        return render_template(
            'dashboard.html',
            gross_income=gross_income,
            total_expenses=total_expenses,
            net_savings=net_savings,
            savings_rate=savings_rate,
            active_subs_count=active_subs_count,
            monthly_sub_burden=monthly_sub_burden,
            upcoming_renewals=upcoming_renewals,
            category_spending=category_spending,
            budget_utilization=budget_utilization,
            recent_transactions=recent_transactions,
            trend_data=trend_data,
            payment_methods=payment_methods,
            categories=categories
        )

    except Exception as e:
        flash(f'Failed to load dashboard data: {str(e)}', 'danger')
        return render_template('dashboard.html', 
            gross_income=0, total_expenses=0, net_savings=0, savings_rate=0,
            active_subs_count=0, monthly_sub_burden=0, upcoming_renewals=[],
            category_spending=[], budget_utilization=[], recent_transactions=[],
            trend_data=[], payment_methods=[], categories=[])

# ------------------------------------------------------------------------------
# Transactions Module (CRUD, Trigger Verification, Filtering)
# ------------------------------------------------------------------------------

@app.route('/transactions')
@login_required
def transactions():
    user_id = session['user_id']
    
    # Query Filters
    tx_type = request.args.get('type', '')
    category_id = request.args.get('category_id', '')
    pm_id = request.args.get('payment_method_id', '')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    search = request.args.get('search', '').strip()

    sql = """
        SELECT 
            t.transaction_id, 
            t.amount, 
            t.transaction_type, 
            t.transaction_date, 
            t.description,
            t.created_at,
            c.category_id,
            c.category_name, 
            pm.payment_method_id,
            pm.method_name,
            sp.payment_id AS subscription_payment_id
        FROM Transactions t
        JOIN Categories c ON t.category_id = c.category_id
        JOIN PaymentMethods pm ON t.payment_method_id = pm.payment_method_id
        LEFT JOIN SubscriptionPayments sp ON t.transaction_id = sp.transaction_id
        WHERE t.user_id = %s
    """
    params = [user_id]

    if tx_type in ('Income', 'Expense'):
        sql += " AND t.transaction_type = %s"
        params.append(tx_type)

    if category_id:
        sql += " AND t.category_id = %s"
        params.append(category_id)

    if pm_id:
        sql += " AND t.payment_method_id = %s"
        params.append(pm_id)

    if start_date:
        sql += " AND t.transaction_date >= %s"
        params.append(start_date)

    if end_date:
        sql += " AND t.transaction_date <= %s"
        params.append(end_date)

    if search:
        sql += " AND (t.description LIKE %s OR c.category_name LIKE %s)"
        params.extend([f"%{search}%", f"%{search}%"])

    sql += " ORDER BY t.transaction_date DESC, t.transaction_id DESC"

    transactions_list = execute_query(sql, tuple(params), fetch='all') or []

    # Get categories & payment methods for filter dropdowns & modal
    categories = execute_query(
        "SELECT category_id, category_name, category_type FROM Categories WHERE user_id = %s ORDER BY category_type, category_name",
        (user_id,),
        fetch='all'
    ) or []

    payment_methods = execute_query(
        "SELECT payment_method_id, method_name FROM PaymentMethods WHERE user_id = %s ORDER BY method_name",
        (user_id,),
        fetch='all'
    ) or []

    # Summary totals for current filter
    total_income = sum(float(t['amount']) for t in transactions_list if t['transaction_type'] == 'Income')
    total_expense = sum(float(t['amount']) for t in transactions_list if t['transaction_type'] == 'Expense')

    return render_template(
        'transactions.html',
        transactions=transactions_list,
        categories=categories,
        payment_methods=payment_methods,
        selected_type=tx_type,
        selected_category=category_id,
        selected_pm=pm_id,
        start_date=start_date,
        end_date=end_date,
        search=search,
        total_income=total_income,
        total_expense=total_expense
    )

@app.route('/transactions/add', methods=['POST'])
@login_required
def add_transaction():
    user_id = session['user_id']
    try:
        category_id = int(request.form.get('category_id'))
        payment_method_id = int(request.form.get('payment_method_id'))
        amount = float(request.form.get('amount', 0))
        transaction_type = request.form.get('transaction_type')
        transaction_date = request.form.get('transaction_date') or date.today().strftime('%Y-%m-%d')
        description = request.form.get('description', '').strip()

        # Execute insertion - Triggers will enforce amount > 0 and category parity
        execute_query(
            """
            INSERT INTO Transactions 
                (user_id, category_id, payment_method_id, amount, transaction_type, transaction_date, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, category_id, payment_method_id, amount, transaction_type, transaction_date, description),
            commit=True
        )
        flash(f'Successfully logged {transaction_type} of ${amount:.2f}!', 'success')

    except mysql.connector.Error as err:
        # Gracefully handle database constraint & validation errors
        if err.sqlstate == '45000' or 'Transaction Error:' in err.msg:
            clean_msg = err.msg.replace('Transaction Error: ', '')
            flash(f'Validation Error: {clean_msg}', 'danger')
        else:
            flash(f'Database Error: {err.msg}', 'danger')
    except ValueError as ve:
        flash(f'Invalid input format: {str(ve)}', 'danger')
    except Exception as e:
        flash(f'Failed to add transaction: {str(e)}', 'danger')

    return redirect(url_for('transactions'))

@app.route('/transactions/delete/<int:transaction_id>', methods=['POST'])
@login_required
def delete_transaction(transaction_id):
    user_id = session['user_id']
    try:
        # Check ownership
        tx = execute_query(
            "SELECT transaction_id, description FROM Transactions WHERE transaction_id = %s AND user_id = %s",
            (transaction_id, user_id),
            fetch='one'
        )
        if not tx:
            flash('Transaction not found or unauthorized.', 'danger')
            return redirect(url_for('transactions'))

        execute_query(
            "DELETE FROM Transactions WHERE transaction_id = %s AND user_id = %s",
            (transaction_id, user_id),
            commit=True
        )
        flash('Transaction removed successfully.', 'info')
    except mysql.connector.Error as err:
        flash(f'Database Error [{err.errno}]: {err.msg}', 'danger')
    except Exception as e:
        flash(f'Could not delete transaction: {str(e)}', 'danger')

    return redirect(url_for('transactions'))

# ------------------------------------------------------------------------------
# Budget Management Module (View: vw_BudgetUtilization)
# ------------------------------------------------------------------------------

@app.route('/budgets')
@login_required
def budgets():
    user_id = session['user_id']
    now = datetime.now()
    
    selected_month = int(request.args.get('month', now.month))
    selected_year = int(request.args.get('year', now.year))

    try:
        # Query MySQL View: vw_BudgetUtilization
        budgets_list = execute_query(
            """
            SELECT 
                budget_id, 
                category_id, 
                category_name, 
                month, 
                year, 
                limit_amount, 
                actual_spent, 
                remaining_balance, 
                utilization_percentage, 
                budget_status
            FROM vw_BudgetUtilization
            WHERE user_id = %s AND month = %s AND year = %s
            ORDER BY utilization_percentage DESC, limit_amount DESC
            """,
            (user_id, selected_month, selected_year),
            fetch='all'
        ) or []

        # Expense categories for the budget creation dropdown
        expense_categories = execute_query(
            "SELECT category_id, category_name FROM Categories WHERE user_id = %s AND category_type = 'Expense' ORDER BY category_name",
            (user_id,),
            fetch='all'
        ) or []

        # Totals for summary
        total_budgeted = sum(float(b['limit_amount']) for b in budgets_list)
        total_spent = sum(float(b['actual_spent']) for b in budgets_list)
        overall_utilization = round((total_spent / total_budgeted * 100), 1) if total_budgeted > 0 else 0.0

        return render_template(
            'budgets.html',
            budgets=budgets_list,
            expense_categories=expense_categories,
            selected_month=selected_month,
            selected_year=selected_year,
            total_budgeted=total_budgeted,
            total_spent=total_spent,
            overall_utilization=overall_utilization
        )
    except Exception as e:
        flash(f'Failed to load budget utilization: {str(e)}', 'danger')
        return render_template('budgets.html', budgets=[], expense_categories=[],
                               selected_month=selected_month, selected_year=selected_year,
                               total_budgeted=0, total_spent=0, overall_utilization=0)

@app.route('/budgets/add', methods=['POST'])
@login_required
def add_budget():
    user_id = session['user_id']
    try:
        category_id = int(request.form.get('category_id'))
        month = int(request.form.get('month'))
        year = int(request.form.get('year'))
        limit_amount = float(request.form.get('limit_amount'))

        if limit_amount <= 0:
            flash('Budget limit must be greater than zero.', 'danger')
            return redirect(url_for('budgets', month=month, year=year))

        execute_query(
            """
            INSERT INTO Budgets (user_id, category_id, month, year, limit_amount)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, category_id, month, year, limit_amount),
            commit=True
        )
        flash('Monthly budget limit configured successfully!', 'success')
    except mysql.connector.Error as err:
        if err.errno == 1062:  # ER_DUP_ENTRY
            flash('A budget for this category and month/year already exists. Please update the existing budget instead.', 'warning')
        else:
            flash(f'Database Error [{err.errno}]: {err.msg}', 'danger')
    except Exception as e:
        flash(f'Error creating budget: {str(e)}', 'danger')

    return redirect(url_for('budgets', month=request.form.get('month'), year=request.form.get('year')))

@app.route('/budgets/update/<int:budget_id>', methods=['POST'])
@login_required
def update_budget(budget_id):
    user_id = session['user_id']
    try:
        new_limit = float(request.form.get('limit_amount', 0))
        month = request.form.get('month')
        year = request.form.get('year')

        if new_limit <= 0:
            flash('Limit amount must be greater than zero.', 'danger')
            return redirect(url_for('budgets', month=month, year=year))

        execute_query(
            "UPDATE Budgets SET limit_amount = %s WHERE budget_id = %s AND user_id = %s",
            (new_limit, budget_id, user_id),
            commit=True
        )
        flash('Budget limit updated successfully!', 'success')
        return redirect(url_for('budgets', month=month, year=year))
    except Exception as e:
        flash(f'Failed to update budget: {str(e)}', 'danger')
        return redirect(url_for('budgets'))

@app.route('/budgets/delete/<int:budget_id>', methods=['POST'])
@login_required
def delete_budget(budget_id):
    user_id = session['user_id']
    month = request.form.get('month')
    year = request.form.get('year')
    try:
        execute_query(
            "DELETE FROM Budgets WHERE budget_id = %s AND user_id = %s",
            (budget_id, user_id),
            commit=True
        )
        flash('Budget removed successfully.', 'info')
    except Exception as e:
        flash(f'Could not delete budget: {str(e)}', 'danger')
    return redirect(url_for('budgets', month=month, year=year))

# ------------------------------------------------------------------------------
# Subscription Management Module (Procedure: sp_RecordSubscriptionPayment)
# ------------------------------------------------------------------------------

@app.route('/subscriptions')
@login_required
def subscriptions():
    user_id = session['user_id']
    try:
        # All subscriptions for user with days remaining
        subs_list = execute_query(
            """
            SELECT 
                subscription_id, 
                subscription_name, 
                amount, 
                billing_cycle, 
                next_renewal_date, 
                status, 
                created_at,
                DATEDIFF(next_renewal_date, CURDATE()) AS days_left
            FROM Subscriptions
            WHERE user_id = %s
            ORDER BY 
                CASE status WHEN 'Active' THEN 1 WHEN 'Paused' THEN 2 ELSE 3 END,
                next_renewal_date ASC
            """,
            (user_id,),
            fetch='all'
        ) or []

        # Subscription payment history ledger
        payment_history = execute_query(
            """
            SELECT 
                sp.payment_id,
                sp.amount,
                sp.payment_date,
                s.subscription_name,
                pm.method_name,
                t.transaction_id
            FROM SubscriptionPayments sp
            JOIN Subscriptions s ON sp.subscription_id = s.subscription_id
            JOIN Transactions t ON sp.transaction_id = t.transaction_id
            JOIN PaymentMethods pm ON t.payment_method_id = pm.payment_method_id
            WHERE s.user_id = %s
            ORDER BY sp.payment_date DESC, sp.payment_id DESC
            LIMIT 15
            """,
            (user_id,),
            fetch='all'
        ) or []

        # Options for modal
        payment_methods = execute_query(
            "SELECT payment_method_id, method_name FROM PaymentMethods WHERE user_id = %s ORDER BY method_name",
            (user_id,),
            fetch='all'
        ) or []

        expense_categories = execute_query(
            "SELECT category_id, category_name FROM Categories WHERE user_id = %s AND category_type = 'Expense' ORDER BY category_name",
            (user_id,),
            fetch='all'
        ) or []

        # Monthly load calculation
        monthly_load = sum(
            float(s['amount']) if s['billing_cycle'] == 'Monthly' else round(float(s['amount']) / 12, 2)
            for s in subs_list if s['status'] == 'Active'
        )

        return render_template(
            'subscriptions.html',
            subscriptions=subs_list,
            payment_history=payment_history,
            payment_methods=payment_methods,
            expense_categories=expense_categories,
            monthly_load=monthly_load
        )
    except Exception as e:
        flash(f'Failed to load subscriptions: {str(e)}', 'danger')
        return render_template('subscriptions.html', subscriptions=[], payment_history=[],
                               payment_methods=[], expense_categories=[], monthly_load=0)

@app.route('/subscriptions/add', methods=['POST'])
@login_required
def add_subscription():
    user_id = session['user_id']
    try:
        sub_name = request.form.get('subscription_name', '').strip()
        amount = float(request.form.get('amount', 0))
        billing_cycle = request.form.get('billing_cycle', 'Monthly')
        next_renewal_date = request.form.get('next_renewal_date')
        status = request.form.get('status', 'Active')

        if not sub_name or amount <= 0 or not next_renewal_date:
            flash('Please provide a valid subscription name, positive amount, and renewal date.', 'danger')
            return redirect(url_for('subscriptions'))

        execute_query(
            """
            INSERT INTO Subscriptions (user_id, subscription_name, amount, billing_cycle, next_renewal_date, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (user_id, sub_name, amount, billing_cycle, next_renewal_date, status),
            commit=True
        )
        flash(f'Subscription "{sub_name}" added successfully!', 'success')
    except Exception as e:
        flash(f'Error adding subscription: {str(e)}', 'danger')

    return redirect(url_for('subscriptions'))

@app.route('/subscriptions/pay/<int:subscription_id>', methods=['POST'])
@login_required
def pay_subscription(subscription_id):
    """
    Executes MySQL Stored Procedure `sp_RecordSubscriptionPayment` to atomically:
    1. Log transaction into `Transactions` ledger as Expense
    2. Record payment in `SubscriptionPayments`
    3. Advance subscription `next_renewal_date` by interval (Monthly/Yearly)
    """
    user_id = session['user_id']
    try:
        payment_method_id = int(request.form.get('payment_method_id'))
        category_id = int(request.form.get('category_id'))
        payment_date = request.form.get('payment_date') or date.today().strftime('%Y-%m-%d')

        # Verify subscription belongs to user
        sub = execute_query(
            "SELECT subscription_id, subscription_name FROM Subscriptions WHERE subscription_id = %s AND user_id = %s",
            (subscription_id, user_id),
            fetch='one'
        )
        if not sub:
            flash('Subscription not found or unauthorized.', 'danger')
            return redirect(url_for('subscriptions'))

        # Call MySQL Stored Procedure
        result = execute_procedure(
            'sp_RecordSubscriptionPayment',
            (subscription_id, payment_method_id, category_id, payment_date)
        )

        if result and len(result) > 0:
            rec = result[0]
            new_date = rec.get('next_renewal_date')
            flash(
                f"Renewal recorded! Logged transaction #{rec.get('new_transaction_id')} for {rec.get('subscription_name')}. "
                f"Next renewal advanced to {new_date}.",
                'success'
            )
        else:
            flash(f"Subscription renewal recorded successfully!", 'success')

    except mysql.connector.Error as err:
        flash(f'Stored Procedure Error [{err.errno}]: {err.msg}', 'danger')
    except Exception as e:
        flash(f'Failed to record subscription payment: {str(e)}', 'danger')

    return redirect(url_for('subscriptions'))

@app.route('/subscriptions/update/<int:subscription_id>', methods=['POST'])
@login_required
def update_subscription(subscription_id):
    user_id = session['user_id']
    try:
        sub_name = request.form.get('subscription_name', '').strip()
        amount = float(request.form.get('amount', 0))
        billing_cycle = request.form.get('billing_cycle')
        next_renewal_date = request.form.get('next_renewal_date')
        status = request.form.get('status')

        execute_query(
            """
            UPDATE Subscriptions
            SET subscription_name = %s, amount = %s, billing_cycle = %s,
                next_renewal_date = %s, status = %s
            WHERE subscription_id = %s AND user_id = %s
            """,
            (sub_name, amount, billing_cycle, next_renewal_date, status, subscription_id, user_id),
            commit=True
        )
        flash('Subscription updated successfully!', 'success')
    except Exception as e:
        flash(f'Failed to update subscription: {str(e)}', 'danger')

    return redirect(url_for('subscriptions'))

@app.route('/subscriptions/delete/<int:subscription_id>', methods=['POST'])
@login_required
def delete_subscription(subscription_id):
    user_id = session['user_id']
    try:
        execute_query(
            "DELETE FROM Subscriptions WHERE subscription_id = %s AND user_id = %s",
            (subscription_id, user_id),
            commit=True
        )
        flash('Subscription deleted.', 'info')
    except Exception as e:
        flash(f'Failed to delete subscription: {str(e)}', 'danger')

    return redirect(url_for('subscriptions'))

# ------------------------------------------------------------------------------
# Reports & Analytics Module (Procedure: sp_GenerateMonthlyReport & Views)
# ------------------------------------------------------------------------------

@app.route('/reports')
@login_required
def reports():
    user_id = session['user_id']
    now = datetime.now()

    selected_month = int(request.args.get('month', now.month))
    selected_year = int(request.args.get('year', now.year))

    try:
        # 1. Execute Stored Procedure: sp_GenerateMonthlyReport
        proc_results = execute_procedure('sp_GenerateMonthlyReport', (user_id, selected_month, selected_year))
        report_summary = proc_results[0] if proc_results else {
            'gross_income': 0.0,
            'total_expenses': 0.0,
            'net_savings': 0.0,
            'savings_rate_percentage': 0.0,
            'active_subscriptions_count': 0,
            'monthly_subscription_burden': 0.0,
            'total_transactions': 0
        }

        # 2. Query View: vw_CategorySpendingSummary for the selected period
        category_spending = execute_query(
            """
            SELECT category_name, total_spent, transaction_count
            FROM vw_CategorySpendingSummary
            WHERE user_id = %s AND month = %s AND year = %s
            ORDER BY total_spent DESC
            """,
            (user_id, selected_month, selected_year),
            fetch='all'
        ) or []

        # 3. Query View: vw_BudgetUtilization for the selected period
        budget_performance = execute_query(
            """
            SELECT 
                category_name, limit_amount, actual_spent, 
                remaining_balance, utilization_percentage, budget_status
            FROM vw_BudgetUtilization
            WHERE user_id = %s AND month = %s AND year = %s
            ORDER BY utilization_percentage DESC
            """,
            (user_id, selected_month, selected_year),
            fetch='all'
        ) or []

        # 4. Detailed Transactions for this report period
        period_transactions = execute_query(
            """
            SELECT 
                t.transaction_id, t.amount, t.transaction_type, 
                t.transaction_date, t.description,
                c.category_name, pm.method_name
            FROM Transactions t
            JOIN Categories c ON t.category_id = c.category_id
            JOIN PaymentMethods pm ON t.payment_method_id = pm.payment_method_id
            WHERE t.user_id = %s 
              AND MONTH(t.transaction_date) = %s 
              AND YEAR(t.transaction_date) = %s
            ORDER BY t.transaction_date DESC
            """,
            (user_id, selected_month, selected_year),
            fetch='all'
        ) or []

        return render_template(
            'reports.html',
            summary=report_summary,
            category_spending=category_spending,
            budget_performance=budget_performance,
            period_transactions=period_transactions,
            selected_month=selected_month,
            selected_year=selected_year
        )
    except Exception as e:
        flash(f'Failed to generate financial report: {str(e)}', 'danger')
        return render_template(
            'reports.html',
            summary={}, category_spending=[], budget_performance=[],
            period_transactions=[], selected_month=selected_month, selected_year=selected_year
        )

@app.route('/reports/export-csv')
@login_required
def export_csv():
    user_id = session['user_id']
    now = datetime.now()
    month = int(request.args.get('month', now.month))
    year = int(request.args.get('year', now.year))

    transactions_data = execute_query(
        """
        SELECT 
            t.transaction_id,
            t.transaction_date,
            t.transaction_type,
            c.category_name,
            pm.method_name,
            t.amount,
            t.description
        FROM Transactions t
        JOIN Categories c ON t.category_id = c.category_id
        JOIN PaymentMethods pm ON t.payment_method_id = pm.payment_method_id
        WHERE t.user_id = %s 
          AND MONTH(t.transaction_date) = %s 
          AND YEAR(t.transaction_date) = %s
        ORDER BY t.transaction_date ASC
        """,
        (user_id, month, year),
        fetch='all'
    ) or []

    si = io.StringIO()
    writer = csv.writer(si)
    writer.writerow(['Transaction ID', 'Date', 'Type', 'Category', 'Payment Method', 'Amount ($)', 'Description'])

    for tx in transactions_data:
        writer.writerow([
            tx['transaction_id'],
            tx['transaction_date'].strftime('%Y-%m-%d') if hasattr(tx['transaction_date'], 'strftime') else tx['transaction_date'],
            tx['transaction_type'],
            tx['category_name'],
            tx['method_name'],
            f"{float(tx['amount']):.2f}",
            tx['description'] or ''
        ])

    output = Response(si.getvalue(), mimetype='text/csv')
    output.headers["Content-Disposition"] = f"attachment; filename=financial_statement_{year}_{month:02d}.csv"
    return output

# ------------------------------------------------------------------------------
# Categories & Payment Methods Management (User Settings)
# ------------------------------------------------------------------------------

@app.route('/settings')
@login_required
def settings():
    user_id = session['user_id']
    try:
        categories = execute_query(
            "SELECT category_id, category_name, category_type FROM Categories WHERE user_id = %s ORDER BY category_type, category_name",
            (user_id,),
            fetch='all'
        ) or []

        payment_methods = execute_query(
            "SELECT payment_method_id, method_name FROM PaymentMethods WHERE user_id = %s ORDER BY method_name",
            (user_id,),
            fetch='all'
        ) or []

        user_info = execute_query(
            "SELECT user_id, name, email, role, created_at FROM Users WHERE user_id = %s",
            (user_id,),
            fetch='one'
        )

        return render_template(
            'settings.html',
            categories=categories,
            payment_methods=payment_methods,
            user_info=user_info
        )
    except Exception as e:
        flash(f'Failed to load settings: {str(e)}', 'danger')
        return render_template('settings.html', categories=[], payment_methods=[], user_info={})

@app.route('/settings/category/add', methods=['POST'])
@login_required
def add_category():
    user_id = session['user_id']
    name = request.form.get('category_name', '').strip()
    cat_type = request.form.get('category_type')

    if not name or cat_type not in ('Income', 'Expense'):
        flash('Valid category name and type are required.', 'danger')
        return redirect(url_for('settings'))

    try:
        execute_query(
            "INSERT INTO Categories (user_id, category_name, category_type) VALUES (%s, %s, %s)",
            (user_id, name, cat_type),
            commit=True
        )
        flash(f'Category "{name}" added successfully!', 'success')
    except mysql.connector.Error as err:
        if err.errno == 1062:
            flash('A category with this name and type already exists.', 'warning')
        else:
            flash(f'Database Error: {err.msg}', 'danger')
    except Exception as e:
        flash(f'Failed to add category: {str(e)}', 'danger')

    return redirect(url_for('settings'))

@app.route('/settings/category/delete/<int:category_id>', methods=['POST'])
@login_required
def delete_category(category_id):
    user_id = session['user_id']
    try:
        cat = execute_query(
            "SELECT category_name FROM Categories WHERE category_id = %s AND user_id = %s",
            (category_id, user_id),
            fetch='one'
        )
        if not cat:
            flash('Category not found or unauthorized.', 'danger')
            return redirect(url_for('settings'))

        # Check if any transactions reference this category
        linked_tx = execute_query(
            "SELECT COUNT(*) AS count FROM Transactions WHERE category_id = %s",
            (category_id,),
            fetch='one'
        )
        if linked_tx and linked_tx['count'] > 0:
            flash(f'Cannot delete "{cat["category_name"]}": {linked_tx["count"]} transaction(s) are linked to it.', 'warning')
            return redirect(url_for('settings'))

        execute_query(
            "DELETE FROM Categories WHERE category_id = %s AND user_id = %s",
            (category_id, user_id),
            commit=True
        )
        flash(f'Category "{cat["category_name"]}" removed successfully.', 'info')
    except mysql.connector.Error as err:
        flash(f'Database Error: {err.msg}', 'danger')
    except Exception as e:
        flash(f'Failed to delete category: {str(e)}', 'danger')

    return redirect(url_for('settings'))

@app.route('/settings/payment-method/add', methods=['POST'])
@login_required
def add_payment_method():
    user_id = session['user_id']
    method_name = request.form.get('method_name', '').strip()

    if not method_name:
        flash('Payment method name cannot be empty.', 'danger')
        return redirect(url_for('settings'))

    try:
        execute_query(
            "INSERT INTO PaymentMethods (user_id, method_name) VALUES (%s, %s)",
            (user_id, method_name),
            commit=True
        )
        flash(f'Payment instrument "{method_name}" added!', 'success')
    except mysql.connector.Error as err:
        if err.errno == 1062:
            flash('This payment method is already registered in your account.', 'warning')
        else:
            flash(f'Database Error: {err.msg}', 'danger')
    except Exception as e:
        flash(f'Failed to add payment method: {str(e)}', 'danger')

    return redirect(url_for('settings'))

@app.route('/settings/payment-method/delete/<int:payment_method_id>', methods=['POST'])
@login_required
def delete_payment_method(payment_method_id):
    user_id = session['user_id']
    try:
        pm = execute_query(
            "SELECT method_name FROM PaymentMethods WHERE payment_method_id = %s AND user_id = %s",
            (payment_method_id, user_id),
            fetch='one'
        )
        if not pm:
            flash('Payment method not found or unauthorized.', 'danger')
            return redirect(url_for('settings'))

        # Check if any transactions reference this payment method
        linked_tx = execute_query(
            "SELECT COUNT(*) AS count FROM Transactions WHERE payment_method_id = %s",
            (payment_method_id,),
            fetch='one'
        )
        if linked_tx and linked_tx['count'] > 0:
            flash(f'Cannot delete "{pm["method_name"]}": {linked_tx["count"]} transaction(s) are linked to it.', 'warning')
            return redirect(url_for('settings'))

        execute_query(
            "DELETE FROM PaymentMethods WHERE payment_method_id = %s AND user_id = %s",
            (payment_method_id, user_id),
            commit=True
        )
        flash(f'Payment method "{pm["method_name"]}" removed successfully.', 'info')
    except mysql.connector.Error as err:
        flash(f'Database Error: {err.msg}', 'danger')
    except Exception as e:
        flash(f'Failed to delete payment method: {str(e)}', 'danger')

    return redirect(url_for('settings'))

# ------------------------------------------------------------------------------
# Admin Overview Route
# ------------------------------------------------------------------------------

@app.route('/admin')
@admin_required
def admin_overview():
    try:
        users = execute_query(
            """
            SELECT 
                u.user_id, u.name, u.email, u.role, u.created_at,
                (SELECT COUNT(*) FROM Transactions t WHERE t.user_id = u.user_id) AS total_transactions,
                (SELECT COUNT(*) FROM Subscriptions s WHERE s.user_id = u.user_id) AS total_subscriptions
            FROM Users u
            ORDER BY u.created_at DESC
            """,
            fetch='all'
        ) or []

        db_stats = execute_query(
            """
            SELECT 
                (SELECT COUNT(*) FROM Users) AS users_count,
                (SELECT COUNT(*) FROM Transactions) AS tx_count,
                (SELECT COUNT(*) FROM Subscriptions) AS sub_count,
                (SELECT COUNT(*) FROM Budgets) AS budget_count,
                (SELECT COUNT(*) FROM SubscriptionPayments) AS sub_payments_count
            """,
            fetch='one'
        ) or {}

        return render_template('admin.html', users=users, stats=db_stats)
    except Exception as e:
        flash(f'Admin portal error: {str(e)}', 'danger')
        return render_template('admin.html', users=[], stats={})

# ------------------------------------------------------------------------------
# API Endpoints (For Asynchronous UI Operations)
# ------------------------------------------------------------------------------

@app.route('/api/categories-by-type')
@login_required
def api_categories_by_type():
    user_id = session['user_id']
    cat_type = request.args.get('type')
    
    if cat_type in ('Income', 'Expense'):
        categories = execute_query(
            "SELECT category_id, category_name FROM Categories WHERE user_id = %s AND category_type = %s ORDER BY category_name",
            (user_id, cat_type),
            fetch='all'
        ) or []
    else:
        categories = execute_query(
            "SELECT category_id, category_name, category_type FROM Categories WHERE user_id = %s ORDER BY category_name",
            (user_id,),
            fetch='all'
        ) or []
    return jsonify(categories)

# ------------------------------------------------------------------------------
# Entry Point
# ------------------------------------------------------------------------------

if __name__ == '__main__':
    print("=" * 70)
    print(" FinTrack - Personal Finance & Subscription Management Platform")
    print(f" Connecting to MySQL at {Config.DB_HOST}:{Config.DB_PORT} as {Config.DB_USER}")
    print("=" * 70)
    app.run(host='0.0.0.0', port=5001, debug=True)

