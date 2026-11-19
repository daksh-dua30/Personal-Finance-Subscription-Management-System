/**
 * Personal Finance & Subscription Management System
 * Client-Side Application Logic & Visualization Setup
 */

document.addEventListener('DOMContentLoaded', () => {
    initFlashMessages();
    initTransactionFormCascade();
    initBudgetEditModals();
    initSubscriptionModals();
});

// ------------------------------------------------------------------------------
// Flash Messages Auto-dismiss
// ------------------------------------------------------------------------------
function initFlashMessages() {
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.transition = 'opacity 0.5s ease-out, transform 0.5s ease-out';
            alert.style.opacity = '0';
            alert.style.transform = 'translateY(-10px)';
            setTimeout(() => alert.remove(), 500);
        }, 5000);
    });
}

// ------------------------------------------------------------------------------
// Generic Modal Controls
// ------------------------------------------------------------------------------
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('hidden');
        modal.classList.add('flex');
        document.body.style.overflow = 'hidden';
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('hidden');
        modal.classList.remove('flex');
        document.body.style.overflow = 'auto';
    }
}

// Close modals when clicking background backdrop
window.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-backdrop')) {
        e.target.parentElement.classList.add('hidden');
        e.target.parentElement.classList.remove('flex');
        document.body.style.overflow = 'auto';
    }
});

// ------------------------------------------------------------------------------
// Transaction Form Dynamic Category Cascading
// Ensures selected category strictly conforms to Income / Expense selection
// ------------------------------------------------------------------------------
function initTransactionFormCascade() {
    const typeRadios = document.querySelectorAll('input[name="transaction_type"]');
    const categorySelect = document.getElementById('tx_category_select');

    if (!categorySelect) return;

    function filterCategories(type) {
        const options = categorySelect.querySelectorAll('option');
        let firstMatchFound = false;

        options.forEach(opt => {
            const optType = opt.getAttribute('data-type');
            if (!optType) return; // Keep placeholder

            if (optType === type) {
                opt.style.display = '';
                opt.disabled = false;
                if (!firstMatchFound) {
                    opt.selected = true;
                    firstMatchFound = true;
                }
            } else {
                opt.style.display = 'none';
                opt.disabled = true;
            }
        });
    }

    typeRadios.forEach(radio => {
        radio.addEventListener('change', (e) => {
            filterCategories(e.target.value);
        });
        if (radio.checked) {
            filterCategories(radio.value);
        }
    });
}

// ------------------------------------------------------------------------------
// Budget Edit Modal Handlers
// ------------------------------------------------------------------------------
function initBudgetEditModals() {
    window.openEditBudgetModal = function(budgetId, categoryName, currentLimit, month, year) {
        const modal = document.getElementById('editBudgetModal');
        if (!modal) return;

        const form = document.getElementById('editBudgetForm');
        form.action = `/budgets/update/${budgetId}`;
        
        document.getElementById('edit_budget_cat_name').textContent = categoryName;
        document.getElementById('edit_budget_limit').value = parseFloat(currentLimit).toFixed(2);
        document.getElementById('edit_budget_month').value = month;
        document.getElementById('edit_budget_year').value = year;

        openModal('editBudgetModal');
    };
}

// ------------------------------------------------------------------------------
// Subscription Modals & Pay Now Handler
// ------------------------------------------------------------------------------
function initSubscriptionModals() {
    // Pay / Record Renewal modal
    window.openPayModal = function(subId, subName, subAmount) {
        const modal = document.getElementById('paySubscriptionModal');
        if (!modal) return;

        const form = document.getElementById('paySubscriptionForm');
        form.action = `/subscriptions/pay/${subId}`;

        document.getElementById('pay_sub_name').textContent = subName;
        document.getElementById('pay_sub_amount').textContent = `$${parseFloat(subAmount).toFixed(2)}`;
        
        openModal('paySubscriptionModal');
    };

    // Edit Subscription modal
    window.openEditSubModal = function(sub) {
        const modal = document.getElementById('editSubscriptionModal');
        if (!modal) return;

        const form = document.getElementById('editSubscriptionForm');
        form.action = `/subscriptions/update/${sub.subscription_id}`;

        document.getElementById('edit_sub_name').value = sub.subscription_name;
        document.getElementById('edit_sub_amount').value = parseFloat(sub.amount).toFixed(2);
        document.getElementById('edit_sub_cycle').value = sub.billing_cycle;
        document.getElementById('edit_sub_renewal').value = sub.next_renewal_date;
        document.getElementById('edit_sub_status').value = sub.status;

        openModal('editSubscriptionModal');
    };
}

// ------------------------------------------------------------------------------
// Chart.js Visualization Initializers
// ------------------------------------------------------------------------------

/**
 * Initializes the Cash Flow Trend Bar/Line Chart
 */
function initCashFlowChart(canvasId, trendData) {
    const ctx = document.getElementById(canvasId);
    if (!ctx || !trendData || trendData.length === 0) return;

    const labels = trendData.map(d => d.month_label);
    const incomeData = trendData.map(d => parseFloat(d.income));
    const expenseData = trendData.map(d => parseFloat(d.expense));

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Gross Income',
                    data: incomeData,
                    backgroundColor: 'rgba(16, 185, 129, 0.85)', // Emerald
                    borderColor: 'rgb(16, 185, 129)',
                    borderWidth: 1,
                    borderRadius: 6,
                    maxBarThickness: 32
                },
                {
                    label: 'Total Expenses',
                    data: expenseData,
                    backgroundColor: 'rgba(244, 63, 94, 0.85)', // Rose
                    borderColor: 'rgb(244, 63, 94)',
                    borderWidth: 1,
                    borderRadius: 6,
                    maxBarThickness: 32
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        color: '#94a3b8',
                        font: { family: "'Inter', sans-serif", size: 12, weight: '500' },
                        usePointStyle: true,
                        pointStyle: 'circle'
                    }
                },
                tooltip: {
                    backgroundColor: '#0f172a',
                    titleColor: '#f8fafc',
                    bodyColor: '#cbd5e1',
                    borderColor: '#334155',
                    borderWidth: 1,
                    padding: 12,
                    callbacks: {
                        label: function(context) {
                            return ` ${context.dataset.label}: $${context.parsed.y.toLocaleString(undefined, {minimumFractionDigits: 2})}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.04)' },
                    ticks: { color: '#64748b', font: { family: "'Inter', sans-serif" } }
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.06)' },
                    ticks: {
                        color: '#64748b',
                        font: { family: "'Inter', sans-serif" },
                        callback: function(val) { return `$${val}`; }
                    }
                }
            }
        }
    });
}

/**
 * Initializes the Category Spending Donut Chart
 */
function initCategoryDonutChart(canvasId, categoryData) {
    const ctx = document.getElementById(canvasId);
    if (!ctx || !categoryData || categoryData.length === 0) return;

    const labels = categoryData.map(c => c.category_name);
    const dataValues = categoryData.map(c => parseFloat(c.total_spent));

    const colorPalette = [
        '#6366f1', // Indigo
        '#ec4899', // Pink
        '#06b6d4', // Cyan
        '#f59e0b', // Amber
        '#10b981', // Emerald
        '#8b5cf6', // Purple
        '#f43f5e', // Rose
        '#3b82f6', // Blue
        '#14b8a6'  // Teal
    ];

    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: dataValues,
                backgroundColor: colorPalette.slice(0, labels.length),
                borderColor: '#0f172a',
                borderWidth: 3,
                hoverOffset: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '72%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#94a3b8',
                        font: { family: "'Inter', sans-serif", size: 11 },
                        usePointStyle: true,
                        pointStyle: 'circle',
                        padding: 16
                    }
                },
                tooltip: {
                    backgroundColor: '#0f172a',
                    titleColor: '#f8fafc',
                    bodyColor: '#cbd5e1',
                    borderColor: '#334155',
                    borderWidth: 1,
                    padding: 12,
                    callbacks: {
                        label: function(context) {
                            const val = context.raw || 0;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const pct = total > 0 ? ((val / total) * 100).toFixed(1) : 0;
                            return ` ${context.label}: $${val.toLocaleString(undefined, {minimumFractionDigits: 2})} (${pct}%)`;
                        }
                    }
                }
            }
        }
    });
}

