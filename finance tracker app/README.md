# Personal Finance & Subscription Management System
> **University DBMS Capstone Project**  
> *Production-Ready, Database-Driven Web Application powered by MySQL Workbench & Python Flask*

---

## 1. Project Overview & Architecture

The **Personal Finance & Subscription Management System (FinTrack DBMS)** is a full-stack, database-centric financial platform engineered to manage personal income, general expenditures, category spending limits, and recurring digital subscriptions.

The core business logic is implemented **inside the database engine** using MySQL Views, Stored Functions, Stored Procedures, and Triggers, ensuring maximum data integrity, concurrency safety, and performance.

### Connection Architecture
The project is split into two interconnected environments:
1. **MySQL Server + MySQL Workbench:** Executes `workbench_setup.sql` to initialize the database schema, 3NF tables, foreign key constraints, analytical views, stored routines, transaction validation triggers, and seed data.
2. **VS Code + Python Flask Backend:** Connects to `localhost:3306` via `mysql-connector-python` to query tables, views, execute procedures, evaluate functions, and render a responsive, dark-mode SaaS UI.

```
+-------------------------------------------------------------+
|                     MySQL Database Engine                   |
|                   (schema: finance_tracker_db)              |
|                                                             |
|  +--------------------+         +------------------------+  |
|  |     7 Tables       |         |        2 Views         |  |
|  |  (Users, Budgets,  | <-----+ | vw_BudgetUtilization   |  |
|  |   Transactions...) |         | vw_CategorySpending... |  |
|  +--------------------+         +------------------------+  |
|           ^                                                 |
|           |                                                 |
|  +--------------------+         +------------------------+  |
|  | 3 Stored Functions |         |  2 Stored Procedures   |  |
|  | fn_CalculateIncome |         | sp_RecordSubPayment    |  |
|  | fn_CalculateExp... |         | sp_GenerateMonthly...  |  |
|  +--------------------+         +------------------------+  |
|           ^                                                 |
|           +---------------------+                           |
|                       2 Triggers                            |
|                 trg_ValidateTransaction                     |
|                 (Raises SQLSTATE 45000)                     |
+-------------------------------------------------------------+
                              ^
                              | mysql-connector-python (localhost:3306)
                              v
+-------------------------------------------------------------+
|                     Python Flask Backend                    |
|          app.py | db.py | config.py (Session Auth)          |
+-------------------------------------------------------------+
                              ^
                              | REST / Server-rendered HTML
                              v
+-------------------------------------------------------------+
|              Modern Frontend UI (Dark SaaS Theme)           |
|         Tailwind CSS | Vanilla JS | Chart.js Charts         |
+-------------------------------------------------------------+
```

---

## 2. Database Schema Design (3NF Normalized)

The database schema `finance_tracker_db` is normalized to the **Third Normal Form (3NF)** with strict referential integrity (`ON DELETE CASCADE` and `ON DELETE RESTRICT`) using the **InnoDB** storage engine and `DECIMAL(12,2)` precision for all monetary columns.

### 7 Relational Tables:
1. **`Users`**: Primary user registry with email uniqueness constraint, `role` (`User` / `Admin`), and password hashes (`scrypt`).
2. **`PaymentMethods`**: Payment instruments tied to users (UPI, Debit Card, Net Banking, Cash) with a composite unique constraint `(user_id, method_name)`.
3. **`Categories`**: Income and expense categories with composite unique constraint `(user_id, category_name, category_type)`.
4. **`Budgets`**: Category spending limits per month/year with composite unique key `(user_id, category_id, month, year)` preventing duplicate budgets.
5. **`Subscriptions`**: Recurring services tracking amounts, billing cycles (`Monthly`, `Yearly`), renewal dates, and status (`Active`, `Paused`, `Cancelled`).
6. **`Transactions`**: Double-entry general ledger storing transactions with date, amount, category, and payment instrument.
7. **`SubscriptionPayments`**: Connects recurring subscriptions to their realized general ledger transactions via a unique `transaction_id` foreign key.

---

## 3. Advanced DBMS Objects Implemented

### 3.1 Views (Virtual Analytical Tables)
- **`vw_CategorySpendingSummary`**: Aggregates total expenses, transaction counts, and spending shares per user, category, month, and year.
- **`vw_BudgetUtilization`**: Joins `Budgets`, `Categories`, and `Transactions` using `LEFT JOIN` to calculate `actual_spent`, `remaining_balance`, `utilization_percentage`, and dynamic `budget_status` (`Normal`, `Warning`, `Critical`, `Over Budget`).

### 3.2 Stored Functions (Deterministic & Reads SQL Data)
- **`fn_CalculateMonthlyIncome(p_user_id, p_month, p_year)`**: Computes gross income for a given month and year.
- **`fn_CalculateMonthlyExpenses(p_user_id, p_month, p_year)`**: Computes total expenses for a given month and year.
- **`fn_CalculateMonthlySavings(p_user_id, p_month, p_year)`**: Evaluates net financial savings (`Income - Expenses`).

### 3.3 Stored Procedures (Atomic Transactions & Business Logic)
- **`sp_RecordSubscriptionPayment(p_subscription_id, p_payment_method_id, p_category_id, p_payment_date)`**:
  - Uses `START TRANSACTION` and `COMMIT` with an exception handler `ROLLBACK`.
  - Atomically logs an expense into `Transactions`.
  - Inserts the link into `SubscriptionPayments`.
  - Automatically advances `next_renewal_date` by **1 month** (for Monthly) or **1 year** (for Yearly).
- **`sp_GenerateMonthlyReport(p_user_id, p_month, p_year)`**:
  - Computes gross income, total expenses, net savings, savings rate %, active subscription count, and normalized monthly subscription burden.

### 3.4 Triggers (Data Integrity Enforcement)
- **`trg_ValidateTransaction` & `trg_ValidateTransactionUpdate`** (`BEFORE INSERT / UPDATE ON Transactions`):
  - Enforces that `amount` is strictly greater than `0.00`.
  - Enforces that `transaction_type` matches the category's `category_type` (e.g. an Income category cannot be assigned to an Expense transaction).
  - Raises standard MySQL error: `SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '...'`.
  - The Flask backend intercepts `SQLSTATE 45000` and displays clean flash alert notifications to the user.

---

## 4. Quick Start & Setup Instructions

### Environment 1: MySQL Workbench Setup
1. Launch **MySQL Workbench** and connect to your local MySQL Server (`localhost:3306`).
2. Open the file `workbench_setup.sql` in MySQL Workbench:
   - `File` &rarr; `Open SQL Script...` &rarr; Select `workbench_setup.sql`.
3. Click the **Execute (Lightning Bolt)** icon to run the complete script.
4. Verify the output log shows successful table creation, views, stored functions, procedures, triggers, and seed data insertion.

### Environment 2: VS Code / Terminal (Flask Web App)
1. Open this project folder in VS Code or your terminal:
   ```bash
   cd "finance tracker app"
   ```
2. Configure your MySQL credentials in `config.py` (or create a `.env` file from `.env.example`):
   ```python
   DB_USER = 'root'
   DB_PASSWORD = 'YOUR_MYSQL_PASSWORD'  # Set your MySQL root password here
   DB_NAME = 'finance_tracker_db'
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Start the Flask application:
   ```bash
   python app.py
   ```
5. Open your browser and navigate to:
   ```text
   http://127.0.0.1:5001
   ```

---

## 5. Seed Demonstration Accounts

The SQL script automatically seeds two pre-configured accounts:

| Role | Email Address | Password | Description |
| :--- | :--- | :--- | :--- |
| **Standard User** | `alex@example.com` | `Password123!` | Populated with 20 transactions across 2 months, 5 active budgets, 5 subscriptions, and historical payment logs. |
| **Administrator** | `admin@example.com` | `Admin123!` | Access to the administrative database telemetry portal. |

*You can also register a brand-new account directly via the UI; the registration endpoint automatically provisions default categories and payment methods.*

---

## 6. Faculty Demonstration Checklist

To demonstrate all DBMS requirements during viva / project presentation:

1. **Demonstrate Stored Functions in MySQL Workbench:**
   ```sql
   USE finance_tracker_db;
   SELECT 
       fn_CalculateMonthlyIncome(1, MONTH(CURDATE()), YEAR(CURDATE())) AS Monthly_Income,
       fn_CalculateMonthlyExpenses(1, MONTH(CURDATE()), YEAR(CURDATE())) AS Monthly_Expenses,
       fn_CalculateMonthlySavings(1, MONTH(CURDATE()), YEAR(CURDATE())) AS Net_Savings;
   ```
2. **Demonstrate Analytical Views:**
   ```sql
   SELECT * FROM vw_BudgetUtilization WHERE user_id = 1;
   SELECT * FROM vw_CategorySpendingSummary WHERE user_id = 1;
   ```
3. **Demonstrate Stored Procedure Atomic Execution:**
   - In the Web UI under **Subscriptions**, click the **"Record Renewal"** button for *Spotify* or *Netflix*.
   - Notice that the web app calls `sp_RecordSubscriptionPayment`:
     - An expense transaction is logged.
     - A payment row is inserted in `SubscriptionPayments`.
     - The subscription's `next_renewal_date` is automatically pushed forward by 1 month.
4. **Demonstrate Trigger Enforcement (SQLSTATE 45000):**
   - In MySQL Workbench or via the Web UI, attempt to add an expense with amount `-50.00` or assign an Income category (Salary) with transaction type `Expense`.
   - The trigger `trg_ValidateTransaction` immediately aborts the insert with `SIGNAL SQLSTATE '45000'`, and the Web UI displays the caught error.

