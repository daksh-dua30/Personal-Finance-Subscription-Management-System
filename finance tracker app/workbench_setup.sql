-- ==============================================================================
-- PERSONAL FINANCE & SUBSCRIPTION MANAGEMENT SYSTEM
-- University DBMS Capstone Project - Database Setup Script
-- Target Environment: MySQL 8.0+ / MySQL Workbench
-- Engine: InnoDB | Character Set: utf8mb4 | Normalization: 3NF
-- ==============================================================================

-- Enable stored function creation without SUPER privilege if binary logging is on
SET GLOBAL log_bin_trust_function_creators = 1;

-- Clean initialization: recreate database
DROP DATABASE IF EXISTS finance_tracker_db;
CREATE DATABASE finance_tracker_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE finance_tracker_db;

-- ==============================================================================
-- 1. TABLE DEFINITIONS (DDL)
-- ==============================================================================

-- 1.1 Users Table
-- Stores user accounts, authentication credentials, and system roles.
CREATE TABLE Users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('User', 'Admin') NOT NULL DEFAULT 'User',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 1.2 Payment Methods Table
-- Tracks payment instruments available per user (e.g. UPI, Debit Card, Net Banking, Cash).
CREATE TABLE PaymentMethods (
    payment_method_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    method_name VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_pm_user FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE,
    CONSTRAINT uq_user_payment_method UNIQUE (user_id, method_name)
) ENGINE=InnoDB;

-- 1.3 Categories Table
-- Classifies transactions into Income or Expense categories.
CREATE TABLE Categories (
    category_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    category_name VARCHAR(100) NOT NULL,
    category_type ENUM('Income', 'Expense') NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_cat_user FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE,
    CONSTRAINT uq_user_category UNIQUE (user_id, category_name, category_type)
) ENGINE=InnoDB;

-- 1.4 Budgets Table
-- Sets monthly spending ceilings for specific expense categories.
CREATE TABLE Budgets (
    budget_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    category_id INT NOT NULL,
    month INT NOT NULL CHECK (month BETWEEN 1 AND 12),
    year INT NOT NULL CHECK (year >= 2000),
    limit_amount DECIMAL(12,2) NOT NULL CHECK (limit_amount > 0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_budget_user FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_budget_category FOREIGN KEY (category_id) REFERENCES Categories(category_id) ON DELETE CASCADE,
    CONSTRAINT uq_user_category_budget_period UNIQUE (user_id, category_id, month, year)
) ENGINE=InnoDB;

-- 1.5 Subscriptions Table
-- Manages recurring digital/physical services, billing intervals, and renewal schedules.
CREATE TABLE Subscriptions (
    subscription_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    subscription_name VARCHAR(100) NOT NULL,
    amount DECIMAL(12,2) NOT NULL CHECK (amount > 0),
    billing_cycle ENUM('Monthly', 'Yearly') NOT NULL DEFAULT 'Monthly',
    next_renewal_date DATE NOT NULL,
    status ENUM('Active', 'Paused', 'Cancelled') NOT NULL DEFAULT 'Active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_sub_user FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- 1.6 Transactions Table
-- Central double-entry general ledger tracking all monetary inflows and outflows.
CREATE TABLE Transactions (
    transaction_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    category_id INT NOT NULL,
    payment_method_id INT NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    transaction_type ENUM('Income', 'Expense') NOT NULL,
    transaction_date DATE NOT NULL,
    description VARCHAR(255) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_tx_user FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_tx_category FOREIGN KEY (category_id) REFERENCES Categories(category_id) ON DELETE RESTRICT,
    CONSTRAINT fk_tx_payment_method FOREIGN KEY (payment_method_id) REFERENCES PaymentMethods(payment_method_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

-- 1.7 Subscription Payments Table
-- Connects a recurring subscription to its realized transaction ledger record.
CREATE TABLE SubscriptionPayments (
    payment_id INT AUTO_INCREMENT PRIMARY KEY,
    subscription_id INT NOT NULL,
    transaction_id INT NOT NULL UNIQUE,
    payment_date DATE NOT NULL,
    amount DECIMAL(12,2) NOT NULL CHECK (amount > 0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_sp_subscription FOREIGN KEY (subscription_id) REFERENCES Subscriptions(subscription_id) ON DELETE CASCADE,
    CONSTRAINT fk_sp_transaction FOREIGN KEY (transaction_id) REFERENCES Transactions(transaction_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Indexes for Query Performance & Analytical Lookups
CREATE INDEX idx_tx_user_date ON Transactions(user_id, transaction_date);
CREATE INDEX idx_tx_user_type_date ON Transactions(user_id, transaction_type, transaction_date);
CREATE INDEX idx_budget_period ON Budgets(user_id, year, month);
CREATE INDEX idx_sub_renewal ON Subscriptions(user_id, status, next_renewal_date);

-- ==============================================================================
-- 2. VIEWS (VIRTUAL TABLES FOR ANALYTICS & REPORTING)
-- ==============================================================================

-- 2.1 View: Category Spending Summary
-- Aggregates monthly expense spending per category and user
CREATE OR REPLACE VIEW vw_CategorySpendingSummary AS
SELECT 
    t.user_id,
    c.category_id,
    c.category_name,
    MONTH(t.transaction_date) AS month,
    YEAR(t.transaction_date) AS year,
    COUNT(t.transaction_id) AS transaction_count,
    COALESCE(SUM(t.amount), 0.00) AS total_spent
FROM Transactions t
JOIN Categories c ON t.category_id = c.category_id
WHERE t.transaction_type = 'Expense'
GROUP BY t.user_id, c.category_id, c.category_name, MONTH(t.transaction_date), YEAR(t.transaction_date);

-- 2.2 View: Budget Utilization
-- Computes real-time spending versus set limits, remaining balances, and status
CREATE OR REPLACE VIEW vw_BudgetUtilization AS
SELECT 
    b.budget_id,
    b.user_id,
    b.category_id,
    c.category_name,
    b.month,
    b.year,
    b.limit_amount,
    COALESCE(SUM(t.amount), 0.00) AS actual_spent,
    ROUND(b.limit_amount - COALESCE(SUM(t.amount), 0.00), 2) AS remaining_balance,
    ROUND(
        CASE 
            WHEN b.limit_amount > 0 THEN (COALESCE(SUM(t.amount), 0.00) / b.limit_amount) * 100.00
            ELSE 0.00
        END, 2
    ) AS utilization_percentage,
    CASE 
        WHEN COALESCE(SUM(t.amount), 0.00) > b.limit_amount THEN 'Over Budget'
        WHEN COALESCE(SUM(t.amount), 0.00) >= (b.limit_amount * 0.90) THEN 'Critical'
        WHEN COALESCE(SUM(t.amount), 0.00) >= (b.limit_amount * 0.70) THEN 'Warning'
        ELSE 'Normal'
    END AS budget_status
FROM Budgets b
JOIN Categories c ON b.category_id = c.category_id
LEFT JOIN Transactions t ON t.user_id = b.user_id 
                         AND t.category_id = b.category_id 
                         AND t.transaction_type = 'Expense'
                         AND MONTH(t.transaction_date) = b.month 
                         AND YEAR(t.transaction_date) = b.year
GROUP BY b.budget_id, b.user_id, b.category_id, c.category_name, b.month, b.year, b.limit_amount;

-- ==============================================================================
-- 3. STORED FUNCTIONS
-- ==============================================================================

DELIMITER $$

-- 3.1 Function: Calculate Monthly Income
CREATE FUNCTION fn_CalculateMonthlyIncome(
    p_user_id INT,
    p_month INT,
    p_year INT
) 
RETURNS DECIMAL(12,2)
READS SQL DATA
DETERMINISTIC
BEGIN
    DECLARE v_total_income DECIMAL(12,2);
    
    SELECT COALESCE(SUM(amount), 0.00)
    INTO v_total_income
    FROM Transactions
    WHERE user_id = p_user_id
      AND transaction_type = 'Income'
      AND MONTH(transaction_date) = p_month
      AND YEAR(transaction_date) = p_year;
      
    RETURN v_total_income;
END$$

-- 3.2 Function: Calculate Monthly Expenses
CREATE FUNCTION fn_CalculateMonthlyExpenses(
    p_user_id INT,
    p_month INT,
    p_year INT
) 
RETURNS DECIMAL(12,2)
READS SQL DATA
DETERMINISTIC
BEGIN
    DECLARE v_total_expenses DECIMAL(12,2);
    
    SELECT COALESCE(SUM(amount), 0.00)
    INTO v_total_expenses
    FROM Transactions
    WHERE user_id = p_user_id
      AND transaction_type = 'Expense'
      AND MONTH(transaction_date) = p_month
      AND YEAR(transaction_date) = p_year;
      
    RETURN v_total_expenses;
END$$

-- 3.3 Function: Calculate Monthly Savings (Income - Expenses)
CREATE FUNCTION fn_CalculateMonthlySavings(
    p_user_id INT,
    p_month INT,
    p_year INT
) 
RETURNS DECIMAL(12,2)
READS SQL DATA
DETERMINISTIC
BEGIN
    DECLARE v_income DECIMAL(12,2);
    DECLARE v_expenses DECIMAL(12,2);
    
    SET v_income = fn_CalculateMonthlyIncome(p_user_id, p_month, p_year);
    SET v_expenses = fn_CalculateMonthlyExpenses(p_user_id, p_month, p_year);
    
    RETURN (v_income - v_expenses);
END$$

DELIMITER ;

-- ==============================================================================
-- 4. TRIGGERS (DATA INTEGRITY ENFORCEMENT)
-- ==============================================================================

DELIMITER $$

-- 4.1 Trigger: Validate Transaction before INSERT
-- Ensures amount is strictly positive and transaction_type matches category category_type
CREATE TRIGGER trg_ValidateTransaction
BEFORE INSERT ON Transactions
FOR EACH ROW
BEGIN
    DECLARE v_cat_type VARCHAR(10);
    DECLARE v_cat_user INT;

    -- Integrity Check 1: Non-zero, positive monetary amount
    IF NEW.amount <= 0.00 THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Transaction Error: Amount must be strictly greater than 0.00.';
    END IF;

    -- Integrity Check 2: Category existence and ownership
    SELECT category_type, user_id INTO v_cat_type, v_cat_user
    FROM Categories
    WHERE category_id = NEW.category_id;

    IF v_cat_type IS NULL THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Transaction Error: The specified category does not exist.';
    END IF;

    IF v_cat_user <> NEW.user_id THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Transaction Error: Category belongs to another user.';
    END IF;

    -- Integrity Check 3: Type parity (Income vs Expense)
    IF NEW.transaction_type <> v_cat_type THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Transaction Error: Transaction type does not match assigned category type.';
    END IF;
END$$

-- 4.2 Trigger: Validate Transaction before UPDATE
CREATE TRIGGER trg_ValidateTransactionUpdate
BEFORE UPDATE ON Transactions
FOR EACH ROW
BEGIN
    DECLARE v_cat_type VARCHAR(10);
    DECLARE v_cat_user INT;

    IF NEW.amount <= 0.00 THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Transaction Error: Amount must be strictly greater than 0.00.';
    END IF;

    SELECT category_type, user_id INTO v_cat_type, v_cat_user
    FROM Categories
    WHERE category_id = NEW.category_id;

    IF v_cat_type IS NULL THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Transaction Error: The specified category does not exist.';
    END IF;

    IF v_cat_user <> NEW.user_id THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Transaction Error: Category belongs to another user.';
    END IF;

    IF NEW.transaction_type <> v_cat_type THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Transaction Error: Transaction type does not match assigned category type.';
    END IF;
END$$

DELIMITER ;

-- ==============================================================================
-- 5. STORED PROCEDURES (BUSINESS LOGIC EXECUTION)
-- ==============================================================================

DELIMITER $$

-- 5.1 Stored Procedure: Record Subscription Payment
-- Atomically writes expense to Transactions, logs SubscriptionPayments, and advances renewal date
CREATE PROCEDURE sp_RecordSubscriptionPayment(
    IN p_subscription_id INT,
    IN p_payment_method_id INT,
    IN p_category_id INT,
    IN p_payment_date DATE
)
proc_label: BEGIN
    DECLARE v_user_id INT;
    DECLARE v_sub_name VARCHAR(100);
    DECLARE v_amount DECIMAL(12,2);
    DECLARE v_billing_cycle ENUM('Monthly', 'Yearly');
    DECLARE v_current_renewal DATE;
    DECLARE v_new_renewal DATE;
    DECLARE v_tx_id INT;
    DECLARE v_effective_date DATE;

    -- Rollback handler on any SQL exception
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    -- Determine effective payment date
    IF p_payment_date IS NULL THEN
        SET v_effective_date = CURDATE();
    ELSE
        SET v_effective_date = p_payment_date;
    END IF;

    -- Retrieve subscription details
    SELECT user_id, subscription_name, amount, billing_cycle, next_renewal_date
    INTO v_user_id, v_sub_name, v_amount, v_billing_cycle, v_current_renewal
    FROM Subscriptions
    WHERE subscription_id = p_subscription_id;

    IF v_user_id IS NULL THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Procedure Error: Subscription not found.';
    END IF;

    -- Calculate next renewal date based on cycle
    IF v_billing_cycle = 'Monthly' THEN
        SET v_new_renewal = DATE_ADD(v_current_renewal, INTERVAL 1 MONTH);
    ELSE
        SET v_new_renewal = DATE_ADD(v_current_renewal, INTERVAL 1 YEAR);
    END IF;

    -- Begin Atomic Transaction
    START TRANSACTION;

        -- 1. Insert into general transaction ledger
        INSERT INTO Transactions (
            user_id, 
            category_id, 
            payment_method_id, 
            amount, 
            transaction_type, 
            transaction_date, 
            description
        ) VALUES (
            v_user_id,
            p_category_id,
            p_payment_method_id,
            v_amount,
            'Expense',
            v_effective_date,
            CONCAT('Subscription Renewal: ', v_sub_name)
        );

        SET v_tx_id = LAST_INSERT_ID();

        -- 2. Link payment record to subscription and transaction
        INSERT INTO SubscriptionPayments (
            subscription_id, 
            transaction_id, 
            payment_date, 
            amount
        ) VALUES (
            p_subscription_id,
            v_tx_id,
            v_effective_date,
            v_amount
        );

        -- 3. Update subscription's next renewal date
        UPDATE Subscriptions
        SET next_renewal_date = v_new_renewal
        WHERE subscription_id = p_subscription_id;

    COMMIT;

    -- Return success confirmation row
    SELECT 
        v_tx_id AS new_transaction_id,
        p_subscription_id AS subscription_id,
        v_sub_name AS subscription_name,
        v_amount AS amount_paid,
        v_new_renewal AS next_renewal_date,
        'Payment recorded successfully' AS message;
END proc_label$$

-- 5.2 Stored Procedure: Generate Monthly Financial Report
CREATE PROCEDURE sp_GenerateMonthlyReport(
    IN p_user_id INT,
    IN p_month INT,
    IN p_year INT
)
BEGIN
    DECLARE v_gross_income DECIMAL(12,2);
    DECLARE v_total_expenses DECIMAL(12,2);
    DECLARE v_net_savings DECIMAL(12,2);
    DECLARE v_savings_rate DECIMAL(6,2);
    DECLARE v_active_subs INT;
    DECLARE v_monthly_sub_load DECIMAL(12,2);
    DECLARE v_tx_count INT;

    -- Compute core metrics using Stored Functions
    SET v_gross_income = fn_CalculateMonthlyIncome(p_user_id, p_month, p_year);
    SET v_total_expenses = fn_CalculateMonthlyExpenses(p_user_id, p_month, p_year);
    SET v_net_savings = fn_CalculateMonthlySavings(p_user_id, p_month, p_year);

    -- Compute Savings Rate percentage
    IF v_gross_income > 0 THEN
        SET v_savings_rate = ROUND((v_net_savings / v_gross_income) * 100.0, 2);
    ELSE
        SET v_savings_rate = 0.00;
    END IF;

    -- Count active subscriptions
    SELECT COUNT(*)
    INTO v_active_subs
    FROM Subscriptions
    WHERE user_id = p_user_id AND status = 'Active';

    -- Compute normalized monthly subscription burden
    SELECT COALESCE(SUM(
        CASE 
            WHEN billing_cycle = 'Monthly' THEN amount
            WHEN billing_cycle = 'Yearly' THEN ROUND(amount / 12.0, 2)
            ELSE 0.00
        END
    ), 0.00)
    INTO v_monthly_sub_load
    FROM Subscriptions
    WHERE user_id = p_user_id AND status = 'Active';

    -- Count total transactions in period
    SELECT COUNT(*)
    INTO v_tx_count
    FROM Transactions
    WHERE user_id = p_user_id
      AND MONTH(transaction_date) = p_month
      AND YEAR(transaction_date) = p_year;

    -- Return comprehensive summary metrics
    SELECT 
        p_user_id AS user_id,
        p_month AS report_month,
        p_year AS report_year,
        v_gross_income AS gross_income,
        v_total_expenses AS total_expenses,
        v_net_savings AS net_savings,
        v_savings_rate AS savings_rate_percentage,
        v_active_subs AS active_subscriptions_count,
        v_monthly_sub_load AS monthly_subscription_burden,
        v_tx_count AS total_transactions;
END$$

DELIMITER ;

-- ==============================================================================
-- 6. SEED DATA GENERATION
-- ==============================================================================

-- 6.1 Seed Users
-- Password for Alex Rivera: Password123!
-- Password for Sarah Connor: Admin123!
-- Hashed via Werkzeug (scrypt standard algorithm)
INSERT INTO Users (user_id, name, email, password_hash, role) VALUES
(1, 'Alex Rivera', 'alex@example.com', 'scrypt:32768:8:1$0CAvXC6ZW8srwctZ$6ec4e70cbe43c3d334a986500a53a5fb3e71751174c7230d6564c22aac0a234cb576f55c750abec154fe59617f0ed7b0a64ef5a438a64ea915b3e30fe045d92e', 'User'),
(2, 'Sarah Connor', 'admin@example.com', 'scrypt:32768:8:1$emNHoiCi5J6efMAv$c9a9a4acd9cb59610397226698378ea4b1ba16a0210568deafe575e2738497ab1d855fbeb97695b2904f8f6d34650077318e51857c24e1b30535a3d77bed6810', 'Admin');

-- 6.2 Seed Payment Methods (4 per user)
INSERT INTO PaymentMethods (payment_method_id, user_id, method_name) VALUES
(1, 1, 'UPI'),
(2, 1, 'Debit Card'),
(3, 1, 'Net Banking'),
(4, 1, 'Cash'),
(5, 2, 'UPI'),
(6, 2, 'Credit Card'),
(7, 2, 'Net Banking'),
(8, 2, 'Cash');

-- 6.3 Seed Categories (9 standard financial categories for User 1)
INSERT INTO Categories (category_id, user_id, category_name, category_type) VALUES
-- Income Categories
(1, 1, 'Salary', 'Income'),
(2, 1, 'Freelance & Consulting', 'Income'),
(3, 1, 'Dividends & Investments', 'Income'),
-- Expense Categories
(4, 1, 'Housing & Rent', 'Expense'),
(5, 1, 'Groceries & Dining', 'Expense'),
(6, 1, 'Utilities & Internet', 'Expense'),
(7, 1, 'Entertainment & Streaming', 'Expense'),
(8, 1, 'Transportation & Fuel', 'Expense'),
(9, 1, 'Healthcare & Fitness', 'Expense'),
-- Categories for Admin / User 2
(10, 2, 'Corporate Salary', 'Income'),
(11, 2, 'Living Expenses', 'Expense');

-- 6.4 Seed Budgets (5 expense categories for Alex Rivera - current month & year)
INSERT INTO Budgets (budget_id, user_id, category_id, month, year, limit_amount) VALUES
(1, 1, 4, MONTH(CURDATE()), YEAR(CURDATE()), 1600.00), -- Housing & Rent
(2, 1, 5, MONTH(CURDATE()), YEAR(CURDATE()), 600.00),  -- Groceries & Dining
(3, 1, 6, MONTH(CURDATE()), YEAR(CURDATE()), 250.00),  -- Utilities & Internet
(4, 1, 7, MONTH(CURDATE()), YEAR(CURDATE()), 150.00),  -- Entertainment & Streaming
(5, 1, 8, MONTH(CURDATE()), YEAR(CURDATE()), 200.00);  -- Transportation & Fuel

-- 6.5 Seed Subscriptions (5 recurring services with varying renewal dates)
-- Uses dynamic dates so demonstration works cleanly at any point in time
INSERT INTO Subscriptions (subscription_id, user_id, subscription_name, amount, billing_cycle, next_renewal_date, status) VALUES
(1, 1, 'Spotify Premium', 11.99, 'Monthly', DATE_ADD(CURDATE(), INTERVAL 3 DAY), 'Active'),
(2, 1, 'Netflix Standard', 15.49, 'Monthly', DATE_ADD(CURDATE(), INTERVAL 5 DAY), 'Active'),
(3, 1, 'GitHub Copilot', 10.00, 'Monthly', DATE_ADD(CURDATE(), INTERVAL 14 DAY), 'Active'),
(4, 1, 'Amazon Prime', 139.00, 'Yearly', DATE_ADD(CURDATE(), INTERVAL 45 DAY), 'Active'),
(5, 1, 'Gym Membership', 45.00, 'Monthly', DATE_ADD(CURDATE(), INTERVAL 28 DAY), 'Paused');

-- 6.6 Seed Transactions (20 realistic transactions across Current Month and Previous Month)
-- Current Month Transactions
INSERT INTO Transactions (transaction_id, user_id, category_id, payment_method_id, amount, transaction_type, transaction_date, description) VALUES
-- Income
(1, 1, 1, 3, 5200.00, 'Income', DATE_SUB(CURDATE(), INTERVAL 25 DAY), 'Monthly Base Salary Direct Deposit'),
(2, 1, 2, 1, 850.00, 'Income', DATE_SUB(CURDATE(), INTERVAL 12 DAY), 'Client Web Design Consulting Project'),
(3, 1, 3, 3, 120.00, 'Income', DATE_SUB(CURDATE(), INTERVAL 8 DAY), 'Quarterly Stock Dividend Payout'),
-- Housing & Utilities Expenses
(4, 1, 4, 3, 1500.00, 'Expense', DATE_SUB(CURDATE(), INTERVAL 24 DAY), 'Monthly Apartment Rent Payment'),
(5, 1, 6, 1, 115.50, 'Expense', DATE_SUB(CURDATE(), INTERVAL 20 DAY), 'High-speed Fiber Internet Bill'),
(6, 1, 6, 2, 78.40, 'Expense', DATE_SUB(CURDATE(), INTERVAL 18 DAY), 'City Electric & Water Utility Bill'),
-- Groceries & Food Expenses
(7, 1, 5, 2, 142.30, 'Expense', DATE_SUB(CURDATE(), INTERVAL 22 DAY), 'Whole Foods Bi-weekly Grocery Run'),
(8, 1, 5, 1, 48.75, 'Expense', DATE_SUB(CURDATE(), INTERVAL 15 DAY), 'Organic Farmers Market Produce'),
(9, 1, 5, 4, 34.50, 'Expense', DATE_SUB(CURDATE(), INTERVAL 10 DAY), 'Weekend Coffee & Brunch with Friends'),
(10, 1, 5, 1, 125.60, 'Expense', DATE_SUB(CURDATE(), INTERVAL 4 DAY), 'Trader Joe Groceries & Supplies'),
-- Transportation Expenses
(11, 1, 8, 2, 58.00, 'Expense', DATE_SUB(CURDATE(), INTERVAL 19 DAY), 'Fuel Station Refill'),
(12, 1, 8, 1, 24.50, 'Expense', DATE_SUB(CURDATE(), INTERVAL 11 DAY), 'Metro Transit Monthly Pass Reload'),
(13, 1, 8, 2, 62.00, 'Expense', DATE_SUB(CURDATE(), INTERVAL 3 DAY), 'Highway Tolls & Fuel Top-up'),
-- Entertainment & Subscriptions realized
(14, 1, 7, 2, 11.99, 'Expense', DATE_SUB(CURDATE(), INTERVAL 27 DAY), 'Subscription Renewal: Spotify Premium'),
(15, 1, 7, 2, 15.49, 'Expense', DATE_SUB(CURDATE(), INTERVAL 25 DAY), 'Subscription Renewal: Netflix Standard'),
(16, 1, 7, 2, 10.00, 'Expense', DATE_SUB(CURDATE(), INTERVAL 16 DAY), 'Subscription Renewal: GitHub Copilot'),
(17, 1, 7, 1, 42.00, 'Expense', DATE_SUB(CURDATE(), INTERVAL 6 DAY), 'Movie Theater Tickets & Snacks'),
-- Healthcare Expense
(18, 1, 9, 2, 35.00, 'Expense', DATE_SUB(CURDATE(), INTERVAL 9 DAY), 'Pharmacy Prescription Co-pay'),
-- Previous Month Historical Transactions
(19, 1, 1, 3, 5200.00, 'Income', DATE_SUB(CURDATE(), INTERVAL 55 DAY), 'Previous Month Base Salary Deposit'),
(20, 1, 4, 3, 1500.00, 'Expense', DATE_SUB(CURDATE(), INTERVAL 54 DAY), 'Previous Month Apartment Rent');

-- 6.7 Seed Subscription Payments (linking realized subscription expenses to Subscriptions)
INSERT INTO SubscriptionPayments (payment_id, subscription_id, transaction_id, payment_date, amount) VALUES
(1, 1, 14, DATE_SUB(CURDATE(), INTERVAL 27 DAY), 11.99),
(2, 2, 15, DATE_SUB(CURDATE(), INTERVAL 25 DAY), 15.49),
(3, 3, 16, DATE_SUB(CURDATE(), INTERVAL 16 DAY), 10.00);

-- Reset auto-increment counters to avoid collision with live additions
ALTER TABLE Users AUTO_INCREMENT = 3;
ALTER TABLE PaymentMethods AUTO_INCREMENT = 9;
ALTER TABLE Categories AUTO_INCREMENT = 12;
ALTER TABLE Budgets AUTO_INCREMENT = 6;
ALTER TABLE Subscriptions AUTO_INCREMENT = 6;
ALTER TABLE Transactions AUTO_INCREMENT = 21;
ALTER TABLE SubscriptionPayments AUTO_INCREMENT = 4;

-- ==============================================================================
-- 7. VERIFICATION & FACULTY DEMONSTRATION QUERIES
-- (Uncomment and execute in MySQL Workbench to verify database state)
-- ==============================================================================

/*
-- [Test 1] Verify Tables and Record Counts
SELECT 'Users' AS Table_Name, COUNT(*) AS Total_Rows FROM Users
UNION ALL
SELECT 'PaymentMethods', COUNT(*) FROM PaymentMethods
UNION ALL
SELECT 'Categories', COUNT(*) FROM Categories
UNION ALL
SELECT 'Budgets', COUNT(*) FROM Budgets
UNION ALL
SELECT 'Subscriptions', COUNT(*) FROM Subscriptions
UNION ALL
SELECT 'Transactions', COUNT(*) FROM Transactions
UNION ALL
SELECT 'SubscriptionPayments', COUNT(*) FROM SubscriptionPayments;

-- [Test 2] Test View: vw_BudgetUtilization
SELECT 
    category_name, 
    limit_amount, 
    actual_spent, 
    remaining_balance, 
    utilization_percentage, 
    budget_status
FROM vw_BudgetUtilization
WHERE user_id = 1 AND month = MONTH(CURDATE()) AND year = YEAR(CURDATE());

-- [Test 3] Test View: vw_CategorySpendingSummary
SELECT * FROM vw_CategorySpendingSummary 
WHERE user_id = 1 
ORDER BY total_spent DESC;

-- [Test 4] Test Stored Functions (Income, Expense, Savings)
SELECT 
    fn_CalculateMonthlyIncome(1, MONTH(CURDATE()), YEAR(CURDATE())) AS Monthly_Income,
    fn_CalculateMonthlyExpenses(1, MONTH(CURDATE()), YEAR(CURDATE())) AS Monthly_Expenses,
    fn_CalculateMonthlySavings(1, MONTH(CURDATE()), YEAR(CURDATE())) AS Net_Savings;

-- [Test 5] Test Stored Procedure: sp_GenerateMonthlyReport
CALL sp_GenerateMonthlyReport(1, MONTH(CURDATE()), YEAR(CURDATE()));

-- [Test 6] Test Stored Procedure: sp_RecordSubscriptionPayment
-- Calls procedure for Spotify (sub_id = 1), PaymentMethod (Debit Card = 2), Category (Entertainment = 7)
-- Notice that next_renewal_date will automatically advance by 1 month!
-- CALL sp_RecordSubscriptionPayment(1, 2, 7, CURDATE());

-- [Test 7] Test Trigger Validation: Amount <= 0 (Should fail with SQLSTATE 45000)
-- INSERT INTO Transactions (user_id, category_id, payment_method_id, amount, transaction_type, transaction_date)
-- VALUES (1, 4, 2, -50.00, 'Expense', CURDATE());

-- [Test 8] Test Trigger Validation: Type Mismatch (Income category assigned Expense type - Should fail)
-- INSERT INTO Transactions (user_id, category_id, payment_method_id, amount, transaction_type, transaction_date)
-- VALUES (1, 1, 2, 100.00, 'Expense', CURDATE());
*/

