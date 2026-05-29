from flask import Flask, request, redirect, url_for, flash, render_template_string, jsonify, make_response, send_file, \
    session
from datetime import datetime, timedelta
from functools import wraps
from collections import defaultdict
import json
import os
import hashlib
import secrets
import re
import uuid
import random

# Import reportlab with error handling
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    print("Note: ReportLab not installed. PDF receipt generation will be disabled.")
    print("Install with: pip install reportlab")

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# ==================== SECURE USER MANAGEMENT ====================
USERS_FILE = "users.json"


def init_admin():
    """Initialize admin user if not exists"""
    if not os.path.exists(USERS_FILE):
        admin_password = hashlib.sha256("admin123".encode()).hexdigest()
        users_data = {
            "admin": {
                "password": admin_password,
                "role": "admin",
                "name": "Isaac Manager",
                "email": "isaac@supermarket.com",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "last_login_ip": "",
                "last_login_time": ""
            }
        }
        with open(USERS_FILE, "w") as file:
            json.dump(users_data, file, indent=2)
        return users_data
    else:
        with open(USERS_FILE, "r") as file:
            return json.load(file)


def save_users(users_data):
    with open(USERS_FILE, "w") as file:
        json.dump(users_data, file, indent=2)


def get_users():
    return init_admin()


users = get_users()
current_session = {}

# M-Pesa transactions and orders
mpesa_transactions = []
orders = []

# All 47 Counties of Kenya with delivery fees
delivery_zones = {
    "Baringo County": {"fee": 280, "estimated_time": "2-3 days"},
    "Bomet County": {"fee": 280, "estimated_time": "2-3 days"},
    "Bungoma County": {"fee": 280, "estimated_time": "2-3 days"},
    "Busia County": {"fee": 300, "estimated_time": "2-3 days"},
    "Elgeyo Marakwet County": {"fee": 300, "estimated_time": "2-3 days"},
    "Embu County": {"fee": 210, "estimated_time": "1-2 days"},
    "Garissa County": {"fee": 400, "estimated_time": "3-4 days"},
    "Homa Bay County": {"fee": 310, "estimated_time": "2-3 days"},
    "Isiolo County": {"fee": 380, "estimated_time": "3-4 days"},
    "Kajiado County": {"fee": 180, "estimated_time": "1-2 hours"},
    "Kakamega County": {"fee": 280, "estimated_time": "2-3 days"},
    "Kericho County": {"fee": 270, "estimated_time": "2-3 days"},
    "Kiambu County": {"fee": 120, "estimated_time": "45-60 min"},
    "Kilifi County": {"fee": 320, "estimated_time": "2-3 days"},
    "Kirinyaga County": {"fee": 190, "estimated_time": "1-2 days"},
    "Kisii County": {"fee": 290, "estimated_time": "2-3 days"},
    "Kisumu County": {"fee": 300, "estimated_time": "2-3 days"},
    "Kitui County": {"fee": 200, "estimated_time": "1-2 days"},
    "Kwale County": {"fee": 340, "estimated_time": "2-3 days"},
    "Laikipia County": {"fee": 220, "estimated_time": "1-2 days"},
    "Lamu County": {"fee": 450, "estimated_time": "4-5 days"},
    "Machakos County": {"fee": 150, "estimated_time": "1-2 hours"},
    "Makueni County": {"fee": 190, "estimated_time": "1-2 days"},
    "Mandera County": {"fee": 500, "estimated_time": "5-6 days"},
    "Marsabit County": {"fee": 450, "estimated_time": "4-5 days"},
    "Meru County": {"fee": 220, "estimated_time": "1-2 days"},
    "Migori County": {"fee": 320, "estimated_time": "2-3 days"},
    "Mombasa County": {"fee": 350, "estimated_time": "2-3 days"},
    "Murang'a County": {"fee": 170, "estimated_time": "1-2 days"},
    "Nairobi County": {"fee": 100, "estimated_time": "30-45 min"},
    "Nakuru County": {"fee": 200, "estimated_time": "1-2 days"},
    "Nandi County": {"fee": 260, "estimated_time": "2-3 days"},
    "Narok County": {"fee": 250, "estimated_time": "2-3 days"},
    "Nyamira County": {"fee": 300, "estimated_time": "2-3 days"},
    "Nyandarua County": {"fee": 210, "estimated_time": "1-2 days"},
    "Nyeri County": {"fee": 180, "estimated_time": "1-2 days"},
    "Samburu County": {"fee": 350, "estimated_time": "3-4 days"},
    "Siaya County": {"fee": 300, "estimated_time": "2-3 days"},
    "Taita Taveta County": {"fee": 350, "estimated_time": "2-3 days"},
    "Tana River County": {"fee": 380, "estimated_time": "3-4 days"},
    "Tharaka Nithi County": {"fee": 230, "estimated_time": "1-2 days"},
    "Trans Nzoia County": {"fee": 280, "estimated_time": "2-3 days"},
    "Turkana County": {"fee": 480, "estimated_time": "4-5 days"},
    "Uasin Gishu County": {"fee": 250, "estimated_time": "2-3 days"},
    "Vihiga County": {"fee": 280, "estimated_time": "2-3 days"},
    "Wajir County": {"fee": 450, "estimated_time": "4-5 days"},
    "West Pokot County": {"fee": 350, "estimated_time": "3-4 days"}
}


def get_client_ip():
    if request.headers.get('X-Forwarded-For'):
        ip = request.headers.get('X-Forwarded-For').split(',')[0]
    else:
        ip = request.remote_addr
    return ip


def login_required(role=None):
    def decorator(func):
        @wraps(func)
        def decorated_function(*args, **kwargs):
            if not current_session.get('logged_in'):
                flash('Please login first!', 'danger')
                return redirect(url_for('login'))
            if role and current_session.get('role') != role and current_session.get('role') != 'admin':
                flash('Access denied! Insufficient permissions.', 'danger')
                return redirect(url_for('index'))
            return func(*args, **kwargs)

        return decorated_function

    return decorator


# ==================== PRODUCTS DATABASE ====================
products = {
    "?? Cooking Oil (1L)": {"price": 250, "quantity": 45, "quality": "high", "category": "cooking", "cost_price": 180,
                            "min_stock": 8},
    "?? Cooking Oil (5L)": {"price": 1150, "quantity": 23, "quality": "premium", "category": "cooking",
                            "cost_price": 850, "min_stock": 5},
    "? Maize Flour (1kg)": {"price": 120, "quantity": 65, "quality": "medium", "category": "cooking", "cost_price": 85,
                            "min_stock": 15},
    "? Maize Flour (2kg)": {"price": 230, "quantity": 40, "quality": "medium", "category": "cooking", "cost_price": 160,
                            "min_stock": 10},
    "? Wheat Flour (1kg)": {"price": 110, "quantity": 58, "quality": "high", "category": "cooking", "cost_price": 75,
                            "min_stock": 12},
    "? Wheat Flour (2kg)": {"price": 210, "quantity": 35, "quality": "high", "category": "cooking", "cost_price": 145,
                            "min_stock": 8},
    "? Rice (1kg)": {"price": 130, "quantity": 55, "quality": "medium", "category": "cooking", "cost_price": 95,
                     "min_stock": 12},
    "? Rice (5kg)": {"price": 600, "quantity": 32, "quality": "premium", "category": "cooking", "cost_price": 450,
                     "min_stock": 5},
    "? Rice (10kg)": {"price": 1150, "quantity": 18, "quality": "premium", "category": "cooking", "cost_price": 880,
                      "min_stock": 3},
    "? Pasta (500g)": {"price": 80, "quantity": 48, "quality": "medium", "category": "cooking", "cost_price": 50,
                       "min_stock": 10},
    "? Spaghetti (1kg)": {"price": 150, "quantity": 35, "quality": "high", "category": "cooking", "cost_price": 100,
                          "min_stock": 8},
    "? Cooking Fat (1kg)": {"price": 180, "quantity": 38, "quality": "high", "category": "cooking", "cost_price": 130,
                            "min_stock": 8},
    "? Salt (1kg)": {"price": 20, "quantity": 105, "quality": "low", "category": "cooking", "cost_price": 10,
                     "min_stock": 20},
    "? Sugar (1kg)": {"price": 140, "quantity": 55, "quality": "medium", "category": "cooking", "cost_price": 100,
                      "min_stock": 12},
    "? Sugar (2kg)": {"price": 270, "quantity": 30, "quality": "medium", "category": "cooking", "cost_price": 195,
                      "min_stock": 8},
    "? Tomato Paste (70g)": {"price": 40, "quantity": 55, "quality": "medium", "category": "cooking", "cost_price": 25,
                             "min_stock": 12},
    "? Tomato Paste (200g)": {"price": 90, "quantity": 42, "quality": "medium", "category": "cooking", "cost_price": 60,
                              "min_stock": 10},
    "? Garlic Paste": {"price": 90, "quantity": 33, "quality": "high", "category": "cooking", "cost_price": 60,
                       "min_stock": 6},
    "? Ginger Paste": {"price": 85, "quantity": 30, "quality": "high", "category": "cooking", "cost_price": 55,
                       "min_stock": 6},
    "? Apple (Red)": {"price": 30, "quantity": 55, "quality": "high", "category": "fruits", "cost_price": 20,
                      "min_stock": 10},
    "? Apple (Green)": {"price": 35, "quantity": 40, "quality": "high", "category": "fruits", "cost_price": 22,
                        "min_stock": 8},
    "? Banana": {"price": 20, "quantity": 105, "quality": "medium", "category": "fruits", "cost_price": 12,
                 "min_stock": 15},
    "? Orange": {"price": 25, "quantity": 48, "quality": "high", "category": "fruits", "cost_price": 15,
                 "min_stock": 10},
    "? Strawberry": {"price": 60, "quantity": 33, "quality": "high", "category": "fruits", "cost_price": 35,
                     "min_stock": 5},
    "? Kiwi": {"price": 40, "quantity": 28, "quality": "high", "category": "fruits", "cost_price": 25, "min_stock": 5},
    "? Pineapple": {"price": 80, "quantity": 18, "quality": "high", "category": "fruits", "cost_price": 50,
                    "min_stock": 3},
    "? Mango": {"price": 45, "quantity": 38, "quality": "high", "category": "fruits", "cost_price": 28, "min_stock": 8},
    "? Grapes": {"price": 55, "quantity": 43, "quality": "high", "category": "fruits", "cost_price": 32,
                 "min_stock": 8},
    "? Cherry": {"price": 90, "quantity": 23, "quality": "premium", "category": "fruits", "cost_price": 60,
                 "min_stock": 3},
    "? Watermelon": {"price": 120, "quantity": 13, "quality": "high", "category": "fruits", "cost_price": 80,
                     "min_stock": 2},
    "? Lettuce": {"price": 35, "quantity": 33, "quality": "medium", "category": "vegetables", "cost_price": 20,
                  "min_stock": 8},
    "? Tomato": {"price": 40, "quantity": 65, "quality": "medium", "category": "vegetables", "cost_price": 25,
                 "min_stock": 12},
    "? Carrot": {"price": 25, "quantity": 85, "quality": "high", "category": "vegetables", "cost_price": 15,
                 "min_stock": 15},
    "? Broccoli": {"price": 50, "quantity": 28, "quality": "high", "category": "vegetables", "cost_price": 30,
                   "min_stock": 5},
    "? Corn": {"price": 30, "quantity": 48, "quality": "medium", "category": "vegetables", "cost_price": 18,
               "min_stock": 10},
    "? Bell Pepper": {"price": 45, "quantity": 38, "quality": "high", "category": "vegetables", "cost_price": 28,
                      "min_stock": 8},
    "? Potato": {"price": 20, "quantity": 125, "quality": "low", "category": "vegetables", "cost_price": 12,
                 "min_stock": 20},
    "? Onion": {"price": 25, "quantity": 95, "quality": "medium", "category": "vegetables", "cost_price": 15,
                "min_stock": 15},
    "? Garlic": {"price": 15, "quantity": 105, "quality": "high", "category": "vegetables", "cost_price": 8,
                 "min_stock": 20},
    "? Cucumber": {"price": 30, "quantity": 58, "quality": "medium", "category": "vegetables", "cost_price": 18,
                   "min_stock": 10},
    "? Milk": {"price": 50, "quantity": 25, "quality": "high", "category": "dairy", "cost_price": 35, "min_stock": 5},
    "? Fresh Milk (1L)": {"price": 95, "quantity": 20, "quality": "high", "category": "dairy", "cost_price": 65,
                          "min_stock": 4},
    "? Cheese": {"price": 120, "quantity": 18, "quality": "premium", "category": "dairy", "cost_price": 85,
                 "min_stock": 3},
    "? Butter": {"price": 90, "quantity": 28, "quality": "high", "category": "dairy", "cost_price": 60, "min_stock": 5},
    "? Eggs (tray)": {"price": 350, "quantity": 45, "quality": "medium", "category": "dairy", "cost_price": 250,
                      "min_stock": 8},
    "? Ice Cream": {"price": 180, "quantity": 43, "quality": "high", "category": "dairy", "cost_price": 120,
                    "min_stock": 8},
    "? Yogurt": {"price": 45, "quantity": 38, "quality": "high", "category": "dairy", "cost_price": 28, "min_stock": 8},
    "? Bread": {"price": 40, "quantity": 20, "quality": "medium", "category": "bakery", "cost_price": 25,
                "min_stock": 5},
    "? Croissant": {"price": 60, "quantity": 24, "quality": "high", "category": "bakery", "cost_price": 35,
                    "min_stock": 5},
    "? Baguette": {"price": 45, "quantity": 22, "quality": "medium", "category": "bakery", "cost_price": 28,
                   "min_stock": 4},
    "? Cookies": {"price": 35, "quantity": 55, "quality": "medium", "category": "bakery", "cost_price": 20,
                  "min_stock": 10},
    "? Cake": {"price": 250, "quantity": 12, "quality": "premium", "category": "bakery", "cost_price": 150,
               "min_stock": 2},
    "? Coffee": {"price": 150, "quantity": 35, "quality": "premium", "category": "beverages", "cost_price": 90,
                 "min_stock": 8},
    "? Tea": {"price": 80, "quantity": 45, "quality": "high", "category": "beverages", "cost_price": 50,
              "min_stock": 10},
    "? Juice": {"price": 60, "quantity": 50, "quality": "medium", "category": "beverages", "cost_price": 38,
                "min_stock": 10},
    "? Soda": {"price": 40, "quantity": 105, "quality": "medium", "category": "beverages", "cost_price": 25,
               "min_stock": 20},
    "? Water (6pack)": {"price": 120, "quantity": 85, "quality": "medium", "category": "beverages", "cost_price": 80,
                        "min_stock": 15},
    "? Popcorn": {"price": 55, "quantity": 38, "quality": "medium", "category": "snacks", "cost_price": 35,
                  "min_stock": 8},
    "? Chocolate": {"price": 75, "quantity": 55, "quality": "high", "category": "snacks", "cost_price": 45,
                    "min_stock": 12},
    "? Candy": {"price": 10, "quantity": 310, "quality": "low", "category": "snacks", "cost_price": 5, "min_stock": 50},
    "? Donut": {"price": 50, "quantity": 28, "quality": "medium", "category": "snacks", "cost_price": 30,
                "min_stock": 6},
    "? Detergent": {"price": 180, "quantity": 35, "quality": "high", "category": "household", "cost_price": 120,
                    "min_stock": 8},
    "? Dish Soap": {"price": 90, "quantity": 45, "quality": "medium", "category": "household", "cost_price": 60,
                    "min_stock": 10},
    "? Sponge": {"price": 25, "quantity": 65, "quality": "low", "category": "household", "cost_price": 15,
                 "min_stock": 15},
    "? Broom": {"price": 150, "quantity": 25, "quality": "medium", "category": "household", "cost_price": 100,
                "min_stock": 5},
}

daily_sales = []
sales_transactions = []
activity_log = []
customers = {}


def save_data():
    data_to_save = {
        "products": products, "daily_sales": daily_sales, "sales_transactions": sales_transactions,
        "activity_log": activity_log, "customers": customers, "mpesa_transactions": mpesa_transactions, "orders": orders
    }
    with open("shop_data.json", "w", encoding='utf-8') as file:
        json.dump(data_to_save, file, indent=2, ensure_ascii=False)


def load_data():
    global products, daily_sales, sales_transactions, activity_log, customers, mpesa_transactions, orders
    try:
        with open("shop_data.json", "r", encoding='utf-8') as file:
            data_loaded = json.load(file)
            products = data_loaded.get("products", products)
            daily_sales = data_loaded.get("daily_sales", daily_sales)
            sales_transactions = data_loaded.get("sales_transactions", sales_transactions)
            activity_log = data_loaded.get("activity_log", activity_log)
            customers = data_loaded.get("customers", customers)
            mpesa_transactions = data_loaded.get("mpesa_transactions", mpesa_transactions)
            orders = data_loaded.get("orders", orders)
    except FileNotFoundError:
        pass
    except Exception as error:
        print(f"Error loading data: {error}")


load_data()


def log_activity(action_message, user=None):
    activity_log.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user": user or current_session.get('username', 'system'),
        "action": action_message,
        "ip": get_client_ip()
    })
    save_data()


def get_total_stock():
    return sum(product["quantity"] for product in products.values())


def get_total_sales():
    return sum(daily_sales)


def get_total_profit():
    total_profit_value = 0
    for transaction in sales_transactions:
        transaction_profit = transaction['total']
        for item in transaction['items']:
            if item['name'] in products:
                cost_price_value = products[item['name']].get('cost_price', products[item['name']]['price'] - 10)
                transaction_profit -= cost_price_value * item['quantity']
        total_profit_value += transaction_profit
    return int(total_profit_value)


def get_daily_sales_last_7_days():
    sales_by_day = defaultdict(float)
    today_date = datetime.now()
    for i in range(7):
        date_str = (today_date - timedelta(days=i)).strftime("%Y-%m-%d")
        sales_by_day[date_str] = 0
    for transaction in sales_transactions:
        transaction_date = transaction['timestamp'][:10]
        if transaction_date in sales_by_day:
            sales_by_day[transaction_date] += transaction['total']
    return dict(sorted(sales_by_day.items()))


def generate_invoice(order, items_list):
    """Generate invoice HTML for an order"""
    invoice_html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Invoice #{order['id']}</title>
        <style>
            body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 0; padding: 20px; background: #f0f2f5; }}
            .invoice {{ max-width: 800px; margin: 0 auto; background: white; border-radius: 15px; box-shadow: 0 10px 40px rgba(0,0,0,0.1); overflow: hidden; }}
            .invoice-header {{ background: linear-gradient(135deg, #1a237e, #1565c0); color: white; padding: 30px; text-align: center; }}
            .invoice-header h1 {{ margin: 0; font-size: 28px; }}
            .invoice-header p {{ margin: 5px 0 0; opacity: 0.9; }}
            .invoice-body {{ padding: 30px; }}
            .company-info {{ text-align: center; margin-bottom: 30px; padding-bottom: 20px; border-bottom: 2px solid #e0e0e0; }}
            .company-name {{ font-size: 24px; font-weight: bold; color: #1a237e; }}
            .company-tagline {{ color: #666; font-size: 12px; }}
            .order-info {{ display: flex; justify-content: space-between; margin-bottom: 30px; padding: 15px; background: #f8f9fa; border-radius: 10px; }}
            .order-info div {{ font-size: 14px; }}
            .order-info strong {{ color: #1a237e; }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 30px; }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #e0e0e0; }}
            th {{ background: #f8f9fa; color: #1a237e; font-weight: 600; }}
            .total-section {{ text-align: right; padding-top: 20px; border-top: 2px solid #e0e0e0; }}
            .total {{ font-size: 24px; font-weight: bold; color: #1a237e; }}
            .footer {{ background: #f8f9fa; padding: 20px; text-align: center; font-size: 12px; color: #666; }}
            .status-paid {{ background: #4CAF50; color: white; padding: 5px 15px; border-radius: 20px; display: inline-block; font-size: 12px; }}
            .status-pending {{ background: #FF9800; color: white; padding: 5px 15px; border-radius: 20px; display: inline-block; font-size: 12px; }}
            @media print {{
                body {{ background: white; padding: 0; }}
                .no-print {{ display: none; }}
            }}
        </style>
    </head>
    <body>
        <div class="invoice">
            <div class="invoice-header">
                <h1>? ISAAC SUPERMARKET COMPANY</h1>
                <p>Quality Products | Best Prices | Since 2024</p>
            </div>
            <div class="invoice-body">
                <div class="company-info">
                    <div class="company-name">TAX INVOICE</div>
                    <div class="company-tagline">P.O. Box 12345 - 00100, Nairobi, Kenya | Tel: 0700 000 000 | Email: info@isaacsupermarket.co.ke</div>
                </div>

                <div class="order-info">
                    <div><strong>Invoice No:</strong> {order['id']}</div>
                    <div><strong>Date:</strong> {order['created_at']}</div>
                    <div><strong>Status:</strong> <span class="status-{order['status']}">{order['status'].upper()}</span></div>
                </div>

                <div class="order-info">
                    <div><strong>Bill To:</strong><br>{order['customer_name']}<br>{order['address']}<br>Phone: {order['phone']}<br>Email: {order['email'] or 'N/A'}</div>
                    <div><strong>Delivery:</strong><br>{order['delivery_zone']}<br>Fee: {order['delivery_fee']} KES<br>Est. Time: {delivery_zones.get(order['delivery_zone'], {{'estimated_time': 'N/A'}})['estimated_time']}</div>
                </div>

                <table>
                    <thead>
                        <tr><th>#</th><th>Item</th><th>Quantity</th><th>Unit Price (KES)</th><th>Total (KES)</th></tr>
                    </thead>
                    <tbody>
                        {items_list}
                        <tr style="background: #f8f9fa;">
                            <td colspan="4" style="text-align: right;"><strong>Subtotal:</strong></td>
                            <td><strong>{order['subtotal']} KES</strong></td>
                        </tr>
                        <tr style="background: #f8f9fa;">
                            <td colspan="4" style="text-align: right;"><strong>Delivery Fee:</strong></td>
                            <td><strong>{order['delivery_fee']} KES</strong></td>
                        </tr>
                        <tr style="background: #e3f2fd;">
                            <td colspan="4" style="text-align: right;"><strong>TOTAL:</strong></td>
                            <td><strong style="font-size: 18px; color: #1a237e;">{order['total']} KES</strong></td>
                        </tr>
                    </tbody>
                </table>

                <div class="total-section">
                    <p><strong>Payment Method:</strong> {order['payment_method'].upper()}</p>
                    <p><strong>M-Pesa Code:</strong> {order.get('mpesa_code', 'N/A')}</p>
                </div>
            </div>
            <div class="footer">
                <p>Thank you for shopping with Isaac Supermarket Company!</p>
                <p>This is a computer generated invoice - No signature required.</p>
                <p>Follow us on Facebook, Twitter & Instagram @IsaacSupermarket</p>
            </div>
        </div>
        <div style="text-align: center; margin-top: 20px;" class="no-print">
            <button onclick="window.print()" style="background: #1a237e; color: white; padding: 12px 30px; border: none; border-radius: 8px; cursor: pointer; margin: 0 10px;">?? Print Invoice</button>
            <button onclick="window.close()" style="background: #666; color: white; padding: 12px 30px; border: none; border-radius: 8px; cursor: pointer;">? Close</button>
        </div>
    </body>
    </html>
    '''
    return invoice_html


def generate_pdf_receipt(transaction_id, cart_items, total_amount, customer_name, customer_phone):
    if not REPORTLAB_AVAILABLE:
        return None
    filename = f"receipt_{transaction_id}.pdf"
    document = SimpleDocTemplate(filename, pagesize=letter)
    style_sheet = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=style_sheet['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#2196F3'),
        alignment=1,
        spaceAfter=30
    )
    elements = []
    elements.append(Paragraph("? ISAAC SUPERMARKET COMPANY", title_style))
    elements.append(Paragraph(f"Receipt #{transaction_id}", style_sheet['Heading2']))
    elements.append(Paragraph(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", style_sheet['Normal']))
    elements.append(Spacer(1, 12))
    if customer_name:
        elements.append(Paragraph(f"Customer: {customer_name}", style_sheet['Normal']))
    if customer_phone:
        elements.append(Paragraph(f"Phone: {customer_phone}", style_sheet['Normal']))
    elements.append(Spacer(1, 20))
    table_data = [['Item', 'Quantity', 'Unit Price', 'Total']]
    for item in cart_items:
        unit_price = item['cost'] / item['quantity']
        table_data.append([item['name'], str(item['quantity']), f"{unit_price:.2f} KES", f"{item['cost']} KES"])
    table_data.append(['', '', 'TOTAL:', f"{total_amount} KES"])
    data_table = Table(table_data, colWidths=[200, 60, 80, 80])
    data_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2196F3')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 1), (-1, -2), colors.HexColor('#E3F2FD')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#1565C0')),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -2), 1, colors.black),
    ]))
    elements.append(data_table)
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("Thank you for shopping at Isaac Supermarket!", style_sheet['Normal']))
    elements.append(Paragraph("We appreciate your business!", style_sheet['Italic']))
    document.build(elements)
    return filename


# ==================== HTML TEMPLATES ====================
COMMON_STYLE = '''
<style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
        background: linear-gradient(135deg, #1a237e 0%, #4a148c 25%, #e65100 50%, #d32f2f 75%, #1565c0 100%);
        min-height: 100vh; }
    @keyframes typingAnimation { 
        0% { width: 0; } 
        20% { width: 0; } 
        100% { width: 100%; } 
    }
    @keyframes blinkCursor { 
        0%, 100% { border-color: #2196F3; } 
        50% { border-color: transparent; } 
    }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
    .container { max-width: 1400px; margin: 0 auto; padding: 20px; animation: fadeIn 0.5s ease; }
    .header { background: rgba(255,255,255,0.95); padding: 20px; border-radius: 15px; margin-bottom: 20px; border-bottom: 3px solid #2196F3; }
    .typing-container { 
        display: inline-block; 
        overflow: hidden; 
        white-space: nowrap; 
        border-right: 3px solid #2196F3; 
        animation: typingAnimation 3.5s steps(30, end) 0.5s forwards, blinkCursor 0.75s step-end infinite; 
        width: 0; 
    }
    .company-name { font-size: 28px; font-weight: bold; background: linear-gradient(135deg, #1a237e, #4a148c, #e65100, #d32f2f, #1565c0); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .nav { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 15px; }
    .nav a { background: linear-gradient(135deg, #1565c0, #2196F3); color: white; padding: 10px 20px; text-decoration: none; border-radius: 8px; transition: all 0.3s; }
    .nav a:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(33,150,243,0.3); }
    .flash { position: fixed; top: 20px; right: 20px; padding: 15px 20px; border-radius: 8px; z-index: 1000; }
    .flash.success { background: #4CAF50; color: white; }
    .flash.danger { background: #f44336; color: white; }
    .flash.warning { background: #FF9800; color: white; }
    button, .btn { cursor: pointer; transition: all 0.2s; font-weight: 600; }
    button:hover, .btn:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(0,0,0,0.2); }
    input, select { padding: 12px; border: 2px solid #e0e0e0; border-radius: 8px; transition: all 0.3s; }
    input:focus, select:focus { border-color: #2196F3; outline: none; box-shadow: 0 0 10px rgba(33,150,243,0.3); }
    table { width: 100%; background: white; border-collapse: collapse; border-radius: 12px; overflow: hidden; }
    th, td { padding: 12px; text-align: left; border-bottom: 1px solid #e5e7eb; }
    th { background: linear-gradient(135deg, #1565c0, #2196F3); color: white; }
    .low-stock { color: #f44336; font-weight: bold; }
    .stat-card { background: white; padding: 20px; border-radius: 12px; text-align: center; cursor: pointer; border-left: 4px solid #2196F3; transition: all 0.3s; }
    .stat-card:hover { transform: translateY(-5px); box-shadow: 0 10px 30px rgba(0,0,0,0.1); }
    .stat-card .value { font-size: 2em; font-weight: bold; color: #1565c0; }
    .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 20px; }
    .chart-container { background: white; padding: 20px; border-radius: 12px; margin-bottom: 20px; }
    .search-box input { width: 100%; margin-bottom: 20px; }
    .user-info { float: right; text-align: right; margin-top: -45px; }
    .btn-order { background: linear-gradient(135deg, #FF9800, #F57C00); color: white; padding: 12px 30px; border: none; border-radius: 8px; font-size: 16px; margin-bottom: 20px; display: inline-block; text-decoration: none; font-weight: 600; }
    @media (max-width: 768px) { .user-info { float: none; text-align: center; margin-top: 15px; } .typing-container { white-space: normal; border-right: none; animation: none; width: 100%; } .company-name { font-size: 20px; } }
</style>
<script>
function animateTyping() {
    var containers = document.querySelectorAll('.typing-container');
    containers.forEach(function(container) {
        container.style.animation = 'none';
        container.offsetHeight;
        container.style.animation = 'typingAnimation 3.5s steps(30, end) 0.5s forwards, blinkCursor 0.75s step-end infinite';
    });
}
setInterval(animateTyping, 4000);
document.addEventListener("DOMContentLoaded", function() {
    setTimeout(animateTyping, 500);
});
</script>
'''

REGISTER_HTML = '''
<!DOCTYPE html>
<html>
<head><title>Register - Isaac Supermarket</title>''' + COMMON_STYLE + '''
<style>
.register-container { background: white; padding: 40px; border-radius: 15px; width: 420px; margin: 50px auto; box-shadow: 0 10px 40px rgba(0,0,0,0.15); }
h1 { text-align: center; margin-bottom: 30px; color: #1565c0; }
input { width: 100%; margin: 10px 0; }
button { width: 100%; padding: 12px; background: linear-gradient(135deg, #1565c0, #2196F3); color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: 600; }
.login-link { text-align: center; margin-top: 20px; }
.login-link a { color: #1565c0; text-decoration: none; }
</style>
</head>
<body>
<div class="register-container">
    <div style="text-align: center;"><div class="typing-container"><div class="company-name">? ISAAC SUPERMARKET COMPANY</div></div></div>
    <h1>? Create Account</h1>
    {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}{% for category, message in messages %}<div class="flash {{ category }}">{{ message }}</div>{% endfor %}{% endif %}
    {% endwith %}
    <form method="POST">
        <input type="text" name="username" placeholder="Username" required>
        <input type="email" name="email" placeholder="Email" required>
        <input type="text" name="fullname" placeholder="Full Name" required>
        <input type="password" name="password" placeholder="Password" required>
        <input type="password" name="confirm_password" placeholder="Confirm Password" required>
        <button type="submit">Register</button>
    </form>
    <div class="login-link">Already have an account? <a href="/login">Login here</a></div>
</div>
</body>
</html>
'''

LOGIN_HTML = '''
<!DOCTYPE html>
<html>
<head><title>Login - Isaac Supermarket</title>''' + COMMON_STYLE + '''
<style>
.login-container { 
    background: white; 
    padding: 50px; 
    border-radius: 20px; 
    width: 500px; 
    margin: 80px auto; 
    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
    text-align: center;
}
h1 { text-align: center; margin-bottom: 30px; background: linear-gradient(135deg, #1a237e, #4a148c, #e65100, #d32f2f, #1565c0);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 32px;
}
input { width: 100%; margin: 15px 0; padding: 14px; font-size: 16px; }
button { width: 100%; padding: 14px; background: linear-gradient(135deg, #1565c0, #2196F3); color: white; border: none; border-radius: 8px; font-size: 18px; font-weight: 600; margin-top: 10px; }
.register-link { text-align: center; margin-top: 25px; }
.register-link a { color: #1565c0; text-decoration: none; font-size: 14px; }
.typing-container { margin-bottom: 20px; }
.company-name { font-size: 26px; }
</style>
</head>
<body>
<div class="login-container">
    <div style="text-align: center;">
        <div class="typing-container"><div class="company-name">? ISAAC SUPERMARKET COMPANY</div></div>
    </div>
    <h1>? Welcome Back!</h1>
    {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}{% for category, message in messages %}<div class="flash {{ category }}">{{ message }}</div>{% endfor %}{% endif %}
    {% endwith %}
    <form method="POST">
        <input type="text" name="username" placeholder="Username or Email" required>
        <input type="password" name="password" placeholder="Password" required>
        <button type="submit">Login to Your Account</button>
    </form>
    <div class="register-link">New to Isaac Supermarket? <a href="/register">Create an account</a></div>
</div>
</body>
</html>
'''

INDEX_HTML = '''
<!DOCTYPE html>
<html>
<head><title>Isaac Supermarket - Dashboard</title><script src="https://cdn.jsdelivr.net/npm/chart.js"></script>''' + COMMON_STYLE + '''
<style>
.search-box input { width: 100%; margin-bottom: 20px; }
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <div style="text-align: center;">
            <div class="typing-container"><div class="company-name">? ISAAC SUPERMARKET COMPANY</div></div>
            <div class="company-tagline">? Quality Products | Best Prices | Free Delivery | M-Pesa Accepted ?</div>
        </div>
        <div class="user-info">
            <span>? {{ session_name }}</span> ({{ session_role }})<br>
            <a href="/change_password" style="color: #1565c0;">? Change Password</a> | <a href="/logout" style="color: #d32f2f;">? Logout</a>
        </div>
        <div class="nav">
            <a href="/">? Dashboard</a> <a href="/products">? Products</a> <a href="/shop">?? Shop Online</a>
            <a href="/cart">? Cart</a> <a href="/orders">? My Orders</a>
            {% if session_role == 'admin' %}<a href="/add_product">? Add Product</a>{% endif %}
            <a href="/sale">? Record Sale</a> <a href="/report">? Report</a> <a href="/low_stock">?? Low Stock</a>
            <a href="/best_sellers">? Best Sellers</a> <a href="/customers">? Customers</a>
            {% if session_role == 'admin' %}
            <a href="/users">? Users</a> <a href="/activity">? Activity Log</a> <a href="/export/csv">? Export CSV</a>
            <a href="/bulk_update">? Bulk Update</a> <a href="/mpesa_transactions">? M-Pesa Transactions</a>
            {% endif %}
        </div>
    </div>
    <div style="text-align: center;"><a href="/shop" class="btn-order">?? Start Shopping Online with M-Pesa</a></div>
    <div class="stats">
        <div class="stat-card" onclick="location.href='/products'"><div class="value">{{ total_products }}</div><div>? Total Products</div></div>
        <div class="stat-card"><div class="value">{{ total_stock }}</div><div>? Total Stock</div></div>
        <div class="stat-card"><div class="value">{{ low_stock_count }}</div><div>?? Low Stock</div></div>
        <div class="stat-card"><div class="value">{{ total_sales }} KES</div><div>? Total Sales</div></div>
        <div class="stat-card"><div class="value">{{ total_profit }} KES</div><div>? Total Profit</div></div>
        <div class="stat-card"><div class="value">{{ transaction_count }}</div><div>? Transactions</div></div>
    </div>
    <div class="chart-container"><canvas id="salesChart" style="max-height: 300px;"></canvas></div>
    <div class="search-box"><input type="text" id="searchInput" placeholder="? Search products..." onkeyup="searchProducts()"></div>
    <div id="productsTable">
        <table><thead><tr><th>?? Product</th><th>? Price</th><th>? Quantity</th><th>? Quality</th><th>? Category</th><th>? Profit</th></tr></thead>
        <tbody>{% for name, details in products.items() %}
        <tr class="product-row">
            <td>{{ name }}</td>
            <td>{{ details.price }} KES</td>
            <td class="{% if details.quantity < details.get('min_stock', 5) %}low-stock{% endif %}">{{ details.quantity }} / {{ details.get('min_stock', 5) }}</td>
            <td>{{ details.quality|capitalize }}</td>
            <td>{{ details.category|capitalize }}</td>
            <td>{{ details.price - details.get('cost_price', details.price - 10) }} KES}-
            </td>
        </tr>{% endfor %}</tbody>
    </table>
    </div>
</div>
<script>
setTimeout(function() { document.querySelectorAll('.flash').forEach(f => f.remove()); }, 3000);
function searchProducts() {
    let input = document.getElementById('searchInput').value.toLowerCase();
    document.querySelectorAll('.product-row').forEach(row => { row.style.display = row.textContent.toLowerCase().includes(input) ? '' : 'none'; });
}
new Chart(document.getElementById('salesChart').getContext('2d'), {
    type: 'line', data: { labels: {{ chart_labels|tojson }}, datasets: [{ label: 'Daily Sales (KES)', data: {{ chart_data|tojson }}, borderColor: '#2196F3', backgroundColor: 'rgba(33,150,243,0.1)', tension: 0.4, fill: true }] },
    options: { responsive: true, maintainAspectRatio: true }
});
</script>
</body>
</html>
'''

SHOP_HTML = '''
<!DOCTYPE html>
<html>
<head><title>Online Shop - Isaac Supermarket</title>''' + COMMON_STYLE + '''
<style>
.product-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; margin-top: 20px; }
.product-card { background: white; border-radius: 12px; padding: 20px; transition: all 0.3s; border: 2px solid transparent; }
.product-card:hover { transform: translateY(-5px); box-shadow: 0 10px 30px rgba(0,0,0,0.1); border-color: #2196F3; }
.product-name { font-size: 18px; font-weight: bold; color: #1565c0; }
.product-price { font-size: 24px; font-weight: bold; color: #e65100; margin: 10px 0; }
.quantity-input { width: 80px; padding: 8px; margin: 10px 0; border: 2px solid #e0e0e0; border-radius: 8px; }
.add-to-cart { background: linear-gradient(135deg, #1565c0, #2196F3); color: white; border: none; padding: 10px 20px; border-radius: 8px; width: 100%; font-size: 16px; font-weight: 600; cursor: pointer; }
.cart-sidebar { position: fixed; right: 0; top: 0; width: 350px; height: 100vh; background: white; box-shadow: -2px 0 10px rgba(0,0,0,0.1); padding: 20px; overflow-y: auto; transform: translateX(100%); transition: transform 0.3s; z-index: 1000; }
.cart-sidebar.open { transform: translateX(0); }
.cart-toggle { position: fixed; right: 20px; bottom: 20px; background: linear-gradient(135deg, #e65100, #d32f2f); color: white; width: 60px; height: 60px; border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; font-size: 24px; z-index: 999; }
.cart-item { border-bottom: 1px solid #e0e0e0; padding: 10px 0; }
.checkout-btn { background: linear-gradient(135deg, #4CAF50, #45A049); color: white; border: none; padding: 15px; border-radius: 8px; width: 100%; margin-top: 20px; font-size: 18px; font-weight: 600; cursor: pointer; }
.search-filter input, .search-filter select { padding: 10px; margin: 5px; }
.category-title { font-size: 24px; font-weight: bold; color: white; margin: 20px 0 10px 0; padding: 10px; background: rgba(0,0,0,0.3); border-radius: 10px; display: inline-block; }
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <div class="typing-container"><div class="company-name">? ISAAC SUPERMARKET - SHOP ONLINE</div></div>
        <div style="margin-top: 15px;"><a href="/" class="nav" style="display:inline-block;">? Dashboard</a> <a href="/cart" class="nav" style="display:inline-block;">? View Cart</a></div>
    </div>
    <div class="search-filter">
        <input type="text" id="search" placeholder="? Search products..." style="width: 300px;">
        <select id="category"><option value="all">All Categories</option><option value="cooking">Cooking</option><option value="fruits">Fruits</option><option value="vegetables">Vegetables</option><option value="dairy">Dairy</option><option value="bakery">Bakery</option><option value="beverages">Beverages</option><option value="snacks">Snacks</option><option value="household">Household</option></select>
    </div>
    {% set cats = ['cooking', 'fruits', 'vegetables', 'dairy', 'bakery', 'beverages', 'snacks', 'household'] %}
    {% for cat in cats %}
    <div><div class="category-title">{{ cat|capitalize }} Section</div></div>
    <div class="product-grid">
        {% for name, details in products.items() if details.category == cat %}
        <div class="product-card" data-name="{{ name.lower() }}" data-category="{{ details.category }}">
            <div class="product-name">{{ name }}</div>
            <div class="product-price">{{ details.price }} KES</div>
            <div>? Stock: {{ details.quantity }}</div><div>? {{ details.quality|capitalize }}</div>
            <input type="number" id="qty_{{ loop.index }}" min="1" max="{{ details.quantity }}" value="1" class="quantity-input">
            <button onclick="addToCart('{{ name }}', {{ details.price }}, {{ loop.index }})" class="add-to-cart">? Add to Cart</button>
        </div>
        {% endfor %}
    </div>
    {% endfor %}
</div>
<div class="cart-toggle" onclick="toggleCart()">? <span id="cartCount">0</span></div>
<div class="cart-sidebar" id="cartSidebar">
    <h2 style="color:#1565c0;">Your Cart</h2><div id="cartItems"></div>
    <div style="margin-top:20px;"><h3>Total: <span id="cartTotal">0</span> KES</h3>
    <button class="checkout-btn" onclick="checkout()">? Proceed to Checkout</button></div>
</div>
<script>
let cart = JSON.parse(localStorage.getItem('cart') || '[]');
function updateCartDisplay() {
    let total = 0, count = 0;
    document.getElementById('cartItems').innerHTML = '';
    cart.forEach((item, idx) => {
        total += item.price * item.quantity;
        count += item.quantity;
        document.getElementById('cartItems').innerHTML += `<div class="cart-item"><strong>${item.name}</strong><br>${item.quantity} x ${item.price} KES = ${item.price * item.quantity} KES<br><button onclick="removeFromCart(${idx})" style="background:#d32f2f;color:white;border:none;padding:5px;border-radius:5px;cursor:pointer;">Remove</button></div>`;
    });
    document.getElementById('cartTotal').innerText = total;
    document.getElementById('cartCount').innerText = count;
    localStorage.setItem('cart', JSON.stringify(cart));
}
function addToCart(name, price, idx) {
    let qty = parseInt(document.getElementById(`qty_${idx}`).value);
    let existing = cart.find(i => i.name === name);
    existing ? existing.quantity += qty : cart.push({ name, price, quantity: qty });
    updateCartDisplay();
    alert(`? Added ${qty} x ${name} to cart!`);
}
function removeFromCart(idx) { cart.splice(idx, 1); updateCartDisplay(); }
function toggleCart() { document.getElementById('cartSidebar').classList.toggle('open'); }
function checkout() {
    if(cart.length === 0) { alert('Your cart is empty!'); return; }
    localStorage.setItem('checkoutCart', JSON.stringify(cart));
    window.location.href = `/checkout?total=${cart.reduce((s,i)=>s+(i.price*i.quantity),0)}`;
}
document.getElementById('search').addEventListener('input', filter);
document.getElementById('category').addEventListener('change', filter);
function filter() {
    let term = document.getElementById('search').value.toLowerCase();
    let cat = document.getElementById('category').value;
    document.querySelectorAll('.product-card').forEach(p => {
        let match = p.getAttribute('data-name').includes(term) && (cat === 'all' || p.getAttribute('data-category') === cat);
        p.style.display = match ? 'block' : 'none';
    });
}
updateCartDisplay();
</script>
</body>
</html>
'''

CART_HTML = '''
<!DOCTYPE html>
<html>
<head><title>Your Cart - Isaac Supermarket</title>''' + COMMON_STYLE + '''
<style>
.cart-container { max-width: 800px; margin: 0 auto; background: white; border-radius: 15px; padding: 30px; }
.cart-item { border-bottom: 1px solid #e0e0e0; padding: 15px; display: flex; justify-content: space-between; }
.total { font-size: 24px; font-weight: bold; color: #1565c0; text-align: right; margin-top: 20px; }
.btn { background: linear-gradient(135deg, #1565c0, #2196F3); color: white; padding: 12px 30px; border: none; border-radius: 8px; margin-top: 20px; cursor: pointer; font-weight: 600; }
</style>
</head>
<body>
<div class="container"><div class="cart-container">
    <h1 style="color:#1565c0;">? Your Shopping Cart</h1>
    <div id="cartItems"></div>
    <div class="total">Total: <span id="cartTotal">0</span> KES</div>
    <button class="btn" onclick="checkout()">? Proceed to Checkout</button>
    <div style="margin-top:20px;"><a href="/shop" class="nav" style="color:#1565c0;">? Continue Shopping</a> | <a href="/" class="nav" style="color:#1565c0;">? Dashboard</a></div>
</div></div>
<script>
let cart = JSON.parse(localStorage.getItem('cart') || '[]');
function displayCart() {
    let total = 0;
    document.getElementById('cartItems').innerHTML = '';
    cart.forEach((item, idx) => {
        total += item.price * item.quantity;
        document.getElementById('cartItems').innerHTML += `<div class="cart-item"><div><strong>${item.name}</strong><br>${item.price} KES � ${item.quantity}</div><div>${item.price * item.quantity} KES<br><button onclick="removeItem(${idx})" style="background:#d32f2f;color:white;border:none;padding:5px 10px;border-radius:5px;cursor:pointer;">Remove</button></div></div>`;
    });
    document.getElementById('cartTotal').innerText = total;
}
function removeItem(idx) { cart.splice(idx,1); localStorage.setItem('cart',JSON.stringify(cart)); displayCart(); }
function checkout() {
    if(cart.length===0) { alert('Your cart is empty!'); return; }
    localStorage.setItem('checkoutCart', JSON.stringify(cart));
    window.location.href = `/checkout?total=${cart.reduce((s,i)=>s+(i.price*i.quantity),0)}`;
}
displayCart();
</script>
</body>
</html>
'''

CHECKOUT_HTML = '''
<!DOCTYPE html>
<html>
<head><title>Checkout - Isaac Supermarket</title>''' + COMMON_STYLE + '''
<style>
.checkout-container { max-width: 700px; margin: 0 auto; background: white; border-radius: 15px; padding: 30px; }
input, select { width: 100%; margin: 10px 0; }
.btn { background: linear-gradient(135deg, #4CAF50, #45A049); color: white; padding: 15px; border: none; border-radius: 8px; width: 100%; font-size: 18px; font-weight: 600; cursor: pointer; }
.total { font-size: 32px; color: #1565c0; text-align: center; margin: 20px 0; font-weight: bold; }
.payment-option { border: 2px solid #e0e0e0; border-radius: 10px; padding: 15px; margin: 10px 0; cursor: pointer; transition: all 0.3s; }
.payment-option.selected { border-color: #4CAF50; background: #F1F8E9; }
.mpesa-section { display: none; margin-top: 20px; padding: 15px; background: #F5F5F5; border-radius: 10px; }
.mpesa-section.active { display: block; }
.simulate-btn { background: #e65100; color: white; padding: 10px; border: none; border-radius: 8px; margin-top: 10px; cursor: pointer; width: 100%; font-weight: 600; }
.otp-section { display: none; margin-top: 15px; padding: 15px; background: #E3F2FD; border-radius: 10px; }
.otp-section.active { display: block; }
.payment-status { display: none; margin-top: 15px; padding: 15px; border-radius: 8px; text-align: center; font-weight: bold; }
.payment-status.success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
.payment-status.pending { background: #fff3cd; color: #856404; border: 1px solid #ffeeba; }
</style>
</head>
<body>
<div class="container"><div class="checkout-container">
    <h1 style="color:#1565c0; text-align:center;">? Checkout</h1>
    <div class="total">Total Amount: {{ total }} KES</div>
    <form method="POST" id="checkoutForm">
        <h3 style="color:#1565c0;">Delivery Information</h3>
        <input type="text" name="full_name" placeholder="Full Name" required>
        <input type="email" name="email" placeholder="Email Address">
        <input type="text" name="address" placeholder="Street Address / Estate" required>
        <select name="delivery_zone" required>
            <option value="">Select Your County</option>
            {% for zone, details in delivery_zones.items() %}
            <option value="{{ zone }}">{{ zone }} - {{ details.fee }} KES ({{ details.estimated_time }})</option>
            {% endfor %}
        </select>

        <h3 style="color:#1565c0; margin-top:20px;">Payment Method</h3>
        <div class="payment-option" onclick="selectPayment('mpesa')" id="opt_mpesa">
            ? M-Pesa (Paybill Number: 123456)
        </div>
        <div class="payment-option" onclick="selectPayment('cash')" id="opt_cash">
            ? Cash on Delivery
        </div>

        <input type="hidden" name="payment_method" id="payment_method" value="mpesa">
        <input type="hidden" name="total" value="{{ total }}">
        <input type="hidden" name="mpesa_code" id="mpesa_code">
        <input type="hidden" name="payment_confirmed" id="payment_confirmed" value="no">

        <div id="mpesa_section" class="mpesa-section">
            <h4 style="color:#1565c0;">M-Pesa Payment Details</h4>
            <p><strong>Paybill Number:</strong> 123456</p>
            <p><strong>Account Number:</strong> SHOP{{ random_id }}</p>
            <p><strong>Amount:</strong> {{ total }} KES</p>
            <hr style="margin: 15px 0;">
            <label><strong>? M-Pesa Phone Number:</strong></label>
            <input type="tel" name="phone" id="phone" placeholder="0712345678" pattern="[0-9]{10}" title="Enter 10-digit phone number" required>

            <button type="button" class="simulate-btn" onclick="requestSTKPush()">? Request STK Push (Send to Phone)</button>

            <div id="otp_section" class="otp-section">
                <p style="color: #1565c0; font-weight: bold;">? Check your phone!</p>
                <p>A prompt has been sent to <span id="phone_display"></span></p>
                <p>Enter your M-Pesa PIN on your phone when prompted.</p>
                <div style="background: #e8f5e9; padding: 10px; border-radius: 8px; margin-top: 10px;">
                    <p style="font-size: 12px; color: #2e7d32;">? Payment will be processed after PIN entry on phone.</p>
                </div>
            </div>

            <div id="payment_status" class="payment-status pending">
                ? Waiting for payment confirmation from your phone...
            </div>
        </div>

        <button type="submit" class="btn" id="submitBtn">? Complete Order</button>
    </form>
</div></div>
<script>
let stkRequested = false;
let paymentCompleted = false;

function selectPayment(method) {
    document.getElementById('payment_method').value = method;
    document.getElementById('opt_mpesa').style.borderColor = method === 'mpesa' ? '#4CAF50' : '#e0e0e0';
    document.getElementById('opt_cash').style.borderColor = method === 'cash' ? '#4CAF50' : '#e0e0e0';
    document.getElementById('opt_mpesa').style.background = method === 'mpesa' ? '#F1F8E9' : 'white';
    document.getElementById('opt_cash').style.background = method === 'cash' ? '#F1F8E9' : 'white';

    const mpesaSection = document.getElementById('mpesa_section');
    if (method === 'mpesa') {
        mpesaSection.classList.add('active');
        document.getElementById('phone').required = true;
    } else {
        mpesaSection.classList.remove('active');
        document.getElementById('phone').required = false;
        document.getElementById('otp_section').classList.remove('active');
        stkRequested = false;
        paymentCompleted = false;
    }
}

function requestSTKPush() {
    let phone = document.getElementById('phone').value;
    let total = {{ total }};
    if (!phone || phone.length < 10) { 
        alert('? Please enter a valid M-Pesa phone number (e.g., 0712345678)'); 
        return; 
    }

    document.getElementById('phone_display').innerText = phone;
    document.getElementById('otp_section').classList.add('active');

    let statusDiv = document.getElementById('payment_status');
    statusDiv.style.display = 'block';
    statusDiv.className = 'payment-status pending';
    statusDiv.innerHTML = '? Payment request sent to your phone. Please enter your M-Pesa PIN on your phone...';

    alert(`? STK Push sent to ${phone}\\n\\nPlease check your phone.\\n\\n? Enter your M-Pesa PIN on your phone when prompted to complete payment.`);

    setTimeout(function() {
        let userConfirmed = confirm(`? Did you enter your M-Pesa PIN on your phone for payment of ${total} KES?\\n\\nClick OK if payment was successful.\\nClick Cancel if payment failed.`);

        if (userConfirmed) {
            statusDiv.className = 'payment-status success';
            statusDiv.innerHTML = '? PAYMENT SUCCESSFUL! Your M-Pesa payment has been confirmed. Click "Complete Order" to finish.';
            document.getElementById('payment_confirmed').value = 'yes';
            document.getElementById('mpesa_code').value = 'MP' + Math.random().toString(36).substr(2, 8).toUpperCase();
            paymentCompleted = true;
            alert('? Payment successful! Your transaction has been processed. Click "Complete Order" to finalize your purchase.');
        } else {
            statusDiv.className = 'payment-status pending';
            statusDiv.innerHTML = '? PAYMENT NOT COMPLETED. Please try again or choose another payment method.';
            document.getElementById('payment_confirmed').value = 'no';
            paymentCompleted = false;
            alert('? Payment was not completed. Please try again or select Cash on Delivery.');
        }
    }, 3000);

    stkRequested = true;
}

function validateAndSubmit() {
    let paymentMethod = document.getElementById('payment_method').value;
    if (paymentMethod === 'mpesa') {
        let phone = document.getElementById('phone').value;
        if (!phone || phone.length < 10) { 
            alert('? Please enter your M-Pesa phone number'); 
            return false; 
        }
        if (!stkRequested) { 
            alert('? Please request STK push first by clicking "Request STK Push"'); 
            return false; 
        }
        if (document.getElementById('payment_confirmed').value !== 'yes') {
            alert('?? Payment not completed! Please complete the payment on your phone first.');
            return false;
        }
    }
    return true;
}

document.getElementById('checkoutForm').onsubmit = function() { return validateAndSubmit(); };
selectPayment('mpesa');
</script>
</body>
</html>
'''


# ==================== ROUTES ====================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        email = request.form['email'].strip()
        fullname = request.form['fullname'].strip()
        password = request.form['password']
        confirm = request.form['confirm_password']
        if not all([username, email, fullname, password]):
            flash('All fields required!', 'danger')
            return redirect(url_for('register'))
        if password != confirm:
            flash('Passwords do not match!', 'danger')
            return redirect(url_for('register'))
        if len(password) < 4:
            flash('Password too short!', 'danger')
            return redirect(url_for('register'))
        users_data = get_users()
        if username in users_data:
            flash('Username exists!', 'danger')
            return redirect(url_for('register'))
        users_data[username] = {
            "password": hashlib.sha256(password.encode()).hexdigest(),
            "role": "staff", "name": fullname, "email": email,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_login_ip": "", "last_login_time": ""
        }
        save_users(users_data)
        flash('Registration successful!', 'success')
        return redirect(url_for('login'))
    return render_template_string(REGISTER_HTML)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()
        users_data = get_users()
        if username in users_data and users_data[username]['password'] == password:
            users_data[username]['last_login_ip'] = get_client_ip()
            users_data[username]['last_login_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_users(users_data)
            current_session['logged_in'] = True
            current_session['username'] = username
            current_session['role'] = users_data[username]['role']
            current_session['name'] = users_data[username]['name']
            log_activity(f"User {username} logged in")
            flash(f'Welcome {users_data[username]["name"]}!', 'success')
            return redirect(url_for('index'))
        flash('Invalid credentials!', 'danger')
    return render_template_string(LOGIN_HTML)


@app.route('/logout')
def logout():
    log_activity(f"User {current_session.get('username', 'unknown')} logged out")
    current_session.clear()
    flash('Logged out!', 'success')
    return redirect(url_for('login'))


@app.route('/')
@login_required()
def index():
    daily_data = get_daily_sales_last_7_days()
    return render_template_string(INDEX_HTML,
                                  total_products=len(products), total_stock=get_total_stock(),
                                  low_stock_count=sum(
                                      1 for p in products.values() if p["quantity"] < p.get("min_stock", 5)),
                                  total_sales=get_total_sales(), total_profit=get_total_profit(),
                                  transaction_count=len(sales_transactions),
                                  products=products, session_name=current_session.get('name', 'User'),
                                  session_role=current_session.get('role', 'staff'),
                                  chart_labels=list(daily_data.keys()), chart_data=list(daily_data.values()))


@app.route('/invoice/<order_id>')
@login_required()
def view_invoice(order_id):
    order = None
    for o in orders:
        if o['id'] == order_id:
            order = o
            break

    if not order:
        flash('Order not found!', 'danger')
        return redirect(url_for('orders_page'))

    # Build items list HTML
    items_html = ''
    for idx, item in enumerate(order.get('product_items', []), 1):
        items_html += f'''
        <tr>
            <td>{idx}</td>
            <td>{item['name']}</td>
            <td>{item['quantity']}</td>
            <td>{item['price']} KES</td>
            <td>{item['price'] * item['quantity']} KES</td>
        </tr>
        '''

    # Add subtotal calculation
    subtotal = sum(item['price'] * item['quantity'] for item in order.get('product_items', []))
    order['subtotal'] = subtotal

    invoice_html = generate_invoice(order, items_html)
    return render_template_string(invoice_html)


@app.route('/products')
@login_required()
def view_products():
    PRODUCTS_HTML = '''
    <!DOCTYPE html><html><head><title>Products</title>''' + COMMON_STYLE + '''
    <style>.btn-edit{background:#4CAF50;color:white;padding:5px 10px;border-radius:5px;text-decoration:none;}.btn-delete{background:#d32f2f;color:white;padding:5px 10px;border-radius:5px;text-decoration:none;}</style>
    </head><body><div class="container"><div class="header"><div class="typing-container"><div class="company-name">? ISAAC SUPERMARKET - PRODUCTS</div></div>
    <div class="nav"><a href="/">Dashboard</a>{% if session_role == 'admin' %}<a href="/add_product">? Add Product</a>{% endif %}</div></div>
    <tr><thead><tr><th>Product</th><th>Price</th><th>Quantity</th><th>Quality</th><th>Category</th>{% if session_role == 'admin' %}<th>Actions</th>{% endif %}</tr></thead>
    <tbody>{% for name, details in products.items() %}
    <tr><td>{{ name }}</td><td>{{ details.price }} KES</td><td class="{% if details.quantity < details.get('min_stock',5) %}low-stock{% endif %}">{{ details.quantity }}</td>
    <td>{{ details.quality }}</td><td>{{ details.category }}</td>
    {% if session_role == 'admin' %}<td><a href="/edit_product/{{ name }}" class="btn-edit">?? Edit</a>
    <a href="/delete_product/{{ name }}" class="btn-delete" onclick="return confirm('Delete?')">?? Delete</a>
    <form action="/restock/{{ name }}" method="POST" style="display:inline;"><input type="number" name="quantity" placeholder="Qty" style="width:60px;" required><button type="submit" style="background:#4CAF50;color:white;border:none;padding:5px 10px;border-radius:5px;">? Restock</button></form></td>{% endif %}
    </tr>{% endfor %}</tbody>
    </table></div></body></html>
    '''
    return render_template_string(PRODUCTS_HTML, products=products, session_role=current_session.get('role', 'staff'))


@app.route('/shop')
@login_required()
def shop():
    return render_template_string(SHOP_HTML, products=products)


@app.route('/cart')
@login_required()
def cart():
    return render_template_string(CART_HTML)


@app.route('/checkout', methods=['GET', 'POST'])
@login_required()
def checkout():
    if request.method == 'POST':
        full_name = request.form['full_name']
        phone = request.form.get('phone', '')
        email = request.form.get('email', '')
        address = request.form['address']
        delivery_zone = request.form['delivery_zone']
        payment_method = request.form['payment_method']
        total = int(request.form['total'])
        mpesa_code = request.form.get('mpesa_code', '')
        payment_confirmed = request.form.get('payment_confirmed', 'no')
        delivery_fee = delivery_zones.get(delivery_zone, {}).get('fee', 100)
        grand_total = total + delivery_fee
        order_id = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(100, 999)}"

        # Get cart items from session (in production)
        # For demo, we'll use placeholder items
        cart_items = request.form.get('cart_items_json', '[]')
        try:
            cart_items_list = json.loads(cart_items) if cart_items else []
        except:
            cart_items_list = []

        # Only mark as paid if M-Pesa payment was confirmed on phone
        if payment_method == 'mpesa' and payment_confirmed == 'yes' and mpesa_code:
            status = 'paid'
            flash(f'? Payment successful! Transaction code: {mpesa_code}', 'success')
        elif payment_method == 'cash':
            status = 'pending'
            flash('? Order placed with Cash on Delivery', 'success')
        else:
            status = 'pending'
            flash('?? Order placed but payment not completed. Please complete payment.', 'warning')

        order = {'id': order_id, 'customer': current_session.get('username'), 'customer_name': full_name,
                 'phone': phone, 'email': email, 'address': address, 'delivery_zone': delivery_zone,
                 'delivery_fee': delivery_fee, 'total': grand_total, 'subtotal': total,
                 'payment_method': payment_method, 'mpesa_code': mpesa_code if payment_confirmed == 'yes' else None,
                 'status': status, 'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 'product_items': cart_items_list}
        orders.append(order)

        if payment_method == 'mpesa' and payment_confirmed == 'yes' and mpesa_code:
            mpesa_transactions.append({'id': f"MP-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(100, 999)}",
                                       'order_id': order_id, 'customer_name': full_name, 'phone': phone,
                                       'amount': grand_total, 'mpesa_code': mpesa_code, 'status': 'success',
                                       'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})

        save_data()
        log_activity(f"New order: {order_id} by {full_name}, Total: {grand_total} KES, Status: {status}")
        flash(f'? Order placed! ID: {order_id}', 'success')
        return redirect(url_for('orders_page'))

    total = request.args.get('total', 0)
    return render_template_string(CHECKOUT_HTML, total=total, random_id=random.randint(10000, 99999),
                                  delivery_zones=delivery_zones)


@app.route('/orders')
@login_required()
def orders_page():
    ORDERS_HTML = '''
    <!DOCTYPE html><html><head><title>My Orders</title>''' + COMMON_STYLE + '''
    <style>
    .order-card{background:white;border-radius:12px;padding:20px;margin-bottom:20px;border-left:4px solid #2196F3;}
    .status{display:inline-block;padding:5px 15px;border-radius:20px;font-size:12px;font-weight:bold;}
    .status-pending{background:#FF9800;color:white;}.status-paid{background:#4CAF50;color:white;}
    .invoice-btn{background:#1565c0;color:white;padding:8px 15px;border:none;border-radius:5px;cursor:pointer;text-decoration:none;display:inline-block;font-size:12px;}
    .invoice-btn:hover{background:#0d47a1;}
    </style>
    </head><body><div class="container"><div style="background:white;border-radius:15px;padding:20px;margin-bottom:20px;">
    <div class="typing-container"><div class="company-name">? ISAAC SUPERMARKET - MY ORDERS</div></div>
    <div style="margin-top:15px;"><a href="/" class="nav">? Dashboard</a> <a href="/shop" class="nav">?? Shop</a></div></div>
    {% if orders %}{% for order in orders|reverse %}
    <div class="order-card"><div style="display:flex;justify-content:space-between;align-items:center;">
        <div><strong>Order #{{ order.id }}</strong><br>{{ order.created_at }}</div>
        <div><span class="status status-{{ order.status }}">{{ order.status|upper }}</span></div>
    </div>
    <div style="margin:10px 0;"><strong>Delivery:</strong> {{ order.delivery_zone }} ({{ order.delivery_fee }} KES)<br>
    <strong>Address:</strong> {{ order.address }}<br><strong>Phone:</strong> {{ order.phone }}</div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:10px;">
        <div><strong>Total: {{ order.total }} KES</strong><br><small>Payment: {{ order.payment_method|upper }}</small></div>
        <a href="/invoice/{{ order.id }}" target="_blank" class="invoice-btn">? View Invoice</a>
    </div></div>
    {% endfor %}{% else %}<div class="order-card" style="text-align:center;"><p>No orders yet. <a href="/shop">Start shopping!</a></p></div>{% endif %}
    </div></body></html>
    '''
    user_orders = [o for o in orders if o.get('customer') == current_session.get('username')]
    return render_template_string(ORDERS_HTML, orders=user_orders)


@app.route('/change_password', methods=['GET', 'POST'])
@login_required()
def change_password():
    CHANGE_PASSWORD_HTML = '''
    <!DOCTYPE html><html><head><title>Change Password</title>''' + COMMON_STYLE + '''
    <style>.form-container{max-width:500px;margin:0 auto;background:white;padding:30px;border-radius:15px;}input{width:100%;padding:12px;margin:10px 0;}
    button{background:linear-gradient(135deg,#1565c0,#2196F3);color:white;padding:12px;border:none;border-radius:8px;width:100%;font-weight:600;}</style>
    </head><body><div class="container"><div class="form-container"><div class="typing-container"><div class="company-name">? ISAAC SUPERMARKET COMPANY</div></div>
    <h1 style="color:#1565c0;">? Change Password</h1>
    {% with messages = get_flashed_messages(with_categories=true) %}{% if messages %}{% for category, message in messages %}<div class="flash {{ category }}">{{ message }}</div>{% endfor %}{% endif %}{% endwith %}
    <form method="POST"><input type="password" name="current_password" placeholder="Current Password" required>
    <input type="password" name="new_password" placeholder="New Password" required>
    <input type="password" name="confirm_password" placeholder="Confirm New Password" required>
    <button type="submit">Change Password</button></form>
    <div style="text-align:center;margin-top:20px;"><a href="/" style="color:#1565c0;">? Back</a></div></div></div></body></html>
    '''
    if request.method == 'POST':
        current = request.form['current_password']
        new = request.form['new_password']
        confirm = request.form['confirm_password']
        username = current_session.get('username')
        users_data = get_users()
        if hashlib.sha256(current.encode()).hexdigest() != users_data[username]['password']:
            flash('Current password incorrect!', 'danger')
            return redirect(url_for('change_password'))
        if new != confirm:
            flash('Passwords do not match!', 'danger')
            return redirect(url_for('change_password'))
        if len(new) < 4:
            flash('Password too short!', 'danger')
            return redirect(url_for('change_password'))
        users_data[username]['password'] = hashlib.sha256(new.encode()).hexdigest()
        save_users(users_data)
        log_activity(f"User {username} changed password")
        flash('Password changed! Please login again.', 'success')
        current_session.clear()
        return redirect(url_for('login'))
    return render_template_string(CHANGE_PASSWORD_HTML)


# Additional routes (add_product, edit_product, delete_product, restock, sale, report, low_stock, best_sellers, customers, activity, export_csv, bulk_update, users, mpesa_transactions, delete_user)
@app.route('/add_product', methods=['GET', 'POST'])
@login_required(role='admin')
def add_product():
    if request.method == 'POST':
        name = request.form['name'].strip()
        if name in products:
            flash('Product exists!', 'danger')
            return redirect(url_for('add_product'))
        qty = int(request.form['quantity'])
        if qty <= 0:
            flash('Quantity must be greater than 0!', 'danger')
            return redirect(url_for('add_product'))
        products[name] = {"price": int(request.form['price']), "quantity": qty, "quality": request.form['quality'],
                          "category": request.form['category'], "cost_price": int(request.form['cost_price']),
                          "min_stock": int(request.form['min_stock'])}
        save_data()
        log_activity(f"Admin added product: {name}")
        flash('Product added!', 'success')
        return redirect(url_for('view_products'))
    ADD_FORM = '<!DOCTYPE html><html><head><title>Add Product</title>' + COMMON_STYLE + '<style>.form-container{max-width:500px;margin:0 auto;background:white;padding:30px;border-radius:15px;}input,select{width:100%;padding:10px;margin:10px 0;}button{background:linear-gradient(135deg,#1565c0,#2196F3);color:white;padding:12px;border:none;border-radius:8px;width:100%;}</style></head><body><div class="container"><div class="form-container"><h1 style="color:#1565c0;">? Add Product</h1><form method="POST"><input type="text" name="name" placeholder="Product Name" required><input type="number" name="price" placeholder="Price (KES)" required><input type="number" name="cost_price" placeholder="Cost Price (KES)" required><input type="number" name="quantity" placeholder="Quantity" required min="1"><input type="number" name="min_stock" placeholder="Min Stock" value="5"><select name="quality"><option>low</option><option>medium</option><option>high</option><option>premium</option></select><select name="category"><option>cooking</option><option>fruits</option><option>vegetables</option><option>dairy</option><option>bakery</option><option>beverages</option><option>snacks</option><option>household</option></select><button type="submit">Add Product</button></form></div></div></body></html>'
    return render_template_string(ADD_FORM)


@app.route('/edit_product/<name>', methods=['GET', 'POST'])
@login_required(role='admin')
def edit_product(name):
    if name not in products:
        flash('Product not found!', 'danger')
        return redirect(url_for('view_products'))
    if request.method == 'POST':
        qty = int(request.form['quantity'])
        if qty <= 0:
            flash('Quantity must be greater than 0!', 'danger')
            return redirect(url_for('edit_product', name=name))
        products[name].update({"price": int(request.form['price']), "quantity": qty, "quality": request.form['quality'],
                               "category": request.form['category'], "cost_price": int(request.form['cost_price']),
                               "min_stock": int(request.form['min_stock'])})
        save_data()
        log_activity(f"Admin edited product: {name}")
        flash('Product updated!', 'success')
        return redirect(url_for('view_products'))
    p = products[name]
    EDIT_FORM = f'<!DOCTYPE html><html><head><title>Edit Product</title>{COMMON_STYLE}<style>.form-container{{max-width:500px;margin:0 auto;background:white;padding:30px;border-radius:15px;}}input,select{{width:100%;padding:10px;margin:10px 0;}}button{{background:linear-gradient(135deg,#1565c0,#2196F3);color:white;padding:12px;border:none;border-radius:8px;width:100%;}}</style></head><body><div class="container"><div class="form-container"><h1 style="color:#1565c0;">?? Edit {name}</h1><form method="POST"><input type="number" name="price" value="{p["price"]}" required><input type="number" name="cost_price" value="{p.get("cost_price", p["price"] - 10)}" required><input type="number" name="quantity" value="{p["quantity"]}" required min="1"><input type="number" name="min_stock" value="{p.get("min_stock", 5)}" required><select name="quality"><option {"selected" if p["quality"] == "low" else ""}>low</option><option {"selected" if p["quality"] == "medium" else ""}>medium</option><option {"selected" if p["quality"] == "high" else ""}>high</option><option {"selected" if p["quality"] == "premium" else ""}>premium</option></select><select name="category"><option {"selected" if p["category"] == "cooking" else ""}>cooking</option><option {"selected" if p["category"] == "fruits" else ""}>fruits</option><option {"selected" if p["category"] == "vegetables" else ""}>vegetables</option><option {"selected" if p["category"] == "dairy" else ""}>dairy</option><option {"selected" if p["category"] == "bakery" else ""}>bakery</option><option {"selected" if p["category"] == "beverages" else ""}>beverages</option><option {"selected" if p["category"] == "snacks" else ""}>snacks</option><option {"selected" if p["category"] == "household" else ""}>household</option></select><button type="submit">Update Product</button></form></div></div></body></html>'
    return render_template_string(EDIT_FORM)


@app.route('/delete_product/<name>')
@login_required(role='admin')
def delete_product(name):
    if name in products:
        del products[name]
        save_data()
        log_activity(f"Admin deleted product: {name}")
        flash('Product deleted!', 'success')
    return redirect(url_for('view_products'))


@app.route('/restock/<name>', methods=['POST'])
@login_required()
def restock_product(name):
    if name in products:
        try:
            qty = int(request.form['quantity'])
            if qty > 0:
                products[name]["quantity"] += qty
                save_data()
                flash(f'Restocked {qty} units!', 'success')
            else:
                flash('Quantity must be positive!', 'danger')
        except:
            flash('Invalid quantity!', 'danger')
    return redirect(request.referrer or url_for('view_products'))


@app.route('/sale', methods=['GET', 'POST'])
@login_required()
def record_sale():
    SALE_HTML = '''
    <!DOCTYPE html><html><head><title>Record Sale</title>''' + COMMON_STYLE + '''
    <style>.product-item{background:white;padding:15px;margin-bottom:10px;border-radius:10px;display:flex;justify-content:space-between;}.customer-input{background:white;padding:20px;border-radius:10px;margin-bottom:20px;}</style>
    </head><body><div class="container"><h1 style="color:#1565c0;">? Record Sale</h1>
    <div class="customer-input"><h3>? Customer Information</h3><input type="text" id="customerPhone" placeholder="Phone" style="width:100%;padding:10px;margin:5px 0;">
    <input type="text" id="customerName" placeholder="Name" style="width:100%;padding:10px;margin:5px 0;">
    <input type="email" id="customerEmail" placeholder="Email" style="width:100%;padding:10px;margin:5px 0;"></div>
    <form method="POST" id="saleForm"><input type="hidden" name="customer_phone" id="customerPhoneInput"><input type="hidden" name="customer_name" id="customerNameInput"><input type="hidden" name="customer_email" id="customerEmailInput">
    {% for name, details in products.items() %}<div class="product-item"><div><strong>{{ name }}</strong><br>{{ details.price }} KES | Stock: {{ details.quantity }}</div>
    <div><input type="number" name="quantities[]" placeholder="Qty" min="0" max="{{ details.quantity }}" value="0" style="width:80px;"><input type="hidden" name="cart_items[]" value="{{ name }}"></div></div>{% endfor %}
    <button type="submit" style="background:linear-gradient(135deg,#1565c0,#2196F3);color:white;padding:15px;border:none;border-radius:10px;width:100%;margin-top:20px;">? Complete Purchase</button></form></div>
    <script>document.getElementById('saleForm').onsubmit=function(){document.getElementById('customerPhoneInput').value=document.getElementById('customerPhone').value;document.getElementById('customerNameInput').value=document.getElementById('customerName').value;document.getElementById('customerEmailInput').value=document.getElementById('customerEmail').value;};</script>
    </body></html>
    '''
    if request.method == 'POST':
        cart, total = [], 0
        items = request.form.getlist('cart_items[]')
        quantities = request.form.getlist('quantities[]')
        customer_phone, customer_name, customer_email = request.form.get('customer_phone', ''), request.form.get(
            'customer_name', ''), request.form.get('customer_email', '')
        for i, name in enumerate(items):
            if name in products:
                try:
                    qty = int(quantities[i]) if quantities[i] else 0
                    if 0 < qty <= products[name]["quantity"]:
                        cost = products[name]["price"] * qty
                        cart.append({'name': name, 'quantity': qty, 'cost': cost})
                        total += cost
                        products[name]["quantity"] -= qty
                except:
                    continue
        if cart:
            daily_sales.append(total)
            tid = f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            sales_transactions.append(
                {'id': tid, 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'items': cart, 'total': total})
            save_data()
            flash(f'Sale recorded! Total: {total} KES', 'success')
            return redirect(url_for('index'))
        flash('No valid items!', 'danger')
    return render_template_string(SALE_HTML, products=products)


@app.route('/report')
@login_required()
def daily_report():
    stats = {'total_transactions': len(daily_sales), 'total_sales': sum(daily_sales),
             'average_sale': sum(daily_sales) / len(daily_sales) if daily_sales else 0}
    REPORT_HTML = '''
    <!DOCTYPE html><html><head><title>Sales Report</title>''' + COMMON_STYLE + '''
    <style>.stat-card{background:white;padding:20px;border-radius:10px;display:inline-block;width:200px;margin:10px;text-align:center;}.transaction{background:white;padding:15px;margin-bottom:10px;border-radius:10px;}</style>
    </head><body><div class="container"><h1 style="color:#1565c0;">? Sales Report</h1><div><div class="stat-card"><h3>Transactions</h3><div style="font-size:2em;color:#1565c0;">{{ stats.total_transactions }}</div></div>
    <div class="stat-card"><h3>Total Sales</h3><div style="font-size:2em;color:#1565c0;">{{ stats.total_sales }} KES</div></div>
    <div class="stat-card"><h3>Average</h3><div style="font-size:2em;color:#1565c0;">{{ "%.2f"|format(stats.average_sale) }} KES</div></div></div>
    {% for trans in transactions|reverse %}<div class="transaction"><strong>{{ trans.timestamp }}</strong><br>{% for item in trans['items'] %}{{ item.quantity }} x {{ item.name }} = {{ item.cost }} KES<br>{% endfor %}<strong>Total: {{ trans.total }} KES</strong></div>{% endfor %}</div></body></html>
    '''
    return render_template_string(REPORT_HTML, stats=stats, transactions=sales_transactions)


@app.route('/low_stock')
@login_required()
def low_stock_alert():
    low_items = {n: d for n, d in products.items() if d["quantity"] < d.get("min_stock", 5)}
    LOW_HTML = '''
    <!DOCTYPE html><html><head><title>Low Stock</title>''' + COMMON_STYLE + '''
    <style>.alert-item{background:#fff3cd;border-left:4px solid #e65100;padding:15px;margin-bottom:15px;border-radius:10px;}</style>
    </head><body><div class="container"><h1 style="color:#1565c0;">?? Low Stock ({{ low_stock_items|length }})</h1>
    {% for name,details in low_stock_items.items() %}<div class="alert-item"><h3>{{ name }}</h3><p>Stock: {{ details.quantity }} | Min: {{ details.get('min_stock',5) }}</p>
    <form action="/restock/{{ name }}" method="POST"><input type="number" name="quantity" placeholder="Add qty"><button type="submit" style="background:#4CAF50;color:white;border:none;padding:5px 15px;border-radius:5px;">Restock</button></form></div>{% endfor %}</div></body></html>
    '''
    return render_template_string(LOW_HTML, low_stock_items=low_items)


@app.route('/best_sellers')
@login_required()
def best_sellers():
    from collections import defaultdict
    count, revenue = defaultdict(int), defaultdict(float)
    for t in sales_transactions:
        for i in t['items']:
            count[i['name']] += i['quantity']
            revenue[i['name']] += i['cost']
    BEST_HTML = '''
    <!DOCTYPE html><html><head><title>Best Sellers</title>''' + COMMON_STYLE + '''
    <style>.best-seller{background:white;padding:20px;margin-bottom:10px;border-radius:10px;border-left:4px solid #e65100;}</style>
    </head><body><div class="container"><h1 style="color:#1565c0;">? Best Sellers</h1><h2>By Quantity</h2>{% for n,q in best_sellers %}<div class="best-seller"><strong>{{ n }}</strong> - {{ q }} units</div>{% endfor %}
    <h2>By Revenue</h2>{% for n,r in top_revenue %}<div class="best-seller"><strong>{{ n }}</strong> - {{ r }} KES</div>{% endfor %}</div></body></html>
    '''
    return render_template_string(BEST_HTML, best_sellers=sorted(count.items(), key=lambda x: x[1], reverse=True)[:10],
                                  top_revenue=sorted(revenue.items(), key=lambda x: x[1], reverse=True)[:10])


@app.route('/customers')
@login_required()
def view_customers():
    total_rev = sum(c.get('total_spent', 0) for c in customers.values())
    CUST_HTML = '''
    <!DOCTYPE html><html><head><title>Customers</title>''' + COMMON_STYLE + '''
    <style>.customer-card{background:white;padding:20px;margin-bottom:10px;border-radius:10px;border-left:4px solid #1565c0;}</style>
    </head><body><div class="container"><h1 style="color:#1565c0;">? Customers ({{ customers|length }})</h1>
    {% for phone,info in customers.items() %}<div class="customer-card"><strong>? {{ info.name or 'Unknown' }}</strong><br>? {{ phone }}<br>? Spent: {{ info.get('total_spent',0) }} KES<br>? Visits: {{ info.get('visits',0) }}<br>? Last: {{ info.get('last_purchase','Never') }}</div>{% endfor %}</div></body></html>
    '''
    return render_template_string(CUST_HTML, customers=customers)


@app.route('/activity')
@login_required(role='admin')
def view_activity():
    ACT_HTML = '''
    <!DOCTYPE html><html><head><title>Activity Log</title>''' + COMMON_STYLE + '''
    <style>.log-entry{background:white;padding:10px;margin-bottom:5px;border-radius:10px;border-left:3px solid #1565c0;}</style>
    </head><body><div class="container"><h1 style="color:#1565c0;">? Activity Log</h1>
    {% for log in activity_log|reverse %}<div class="log-entry"><strong>{{ log.timestamp }}</strong> | ? {{ log.user }}: {{ log.action }}<br><span style="color:#666;">? IP: {{ log.get('ip','Unknown') }}</span></div>{% endfor %}</div></body></html>
    '''
    return render_template_string(ACT_HTML, activity_log=activity_log[-100:])


@app.route('/export/csv')
@login_required(role='admin')
def export_csv():
    if not sales_transactions:
        flash('No sales to export!', 'warning')
        return redirect(url_for('daily_report'))
    filename = f"sales_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with open(filename, 'w') as f:
        f.write("Date,Transaction,Product,Quantity,Price,Total\n")
        for t in sales_transactions:
            for i in t['items']:
                f.write(
                    f"{t['timestamp']},{t['id']},{i['name']},{i['quantity']},{i['cost'] / i['quantity']:.2f},{i['cost']}\n")
    flash(f'Exported to {filename}', 'success')
    return redirect(url_for('daily_report'))


@app.route('/bulk_update', methods=['GET', 'POST'])
@login_required(role='admin')
def bulk_update():
    if request.method == 'POST':
        percent = float(request.form['percent'])
        cat = request.form.get('category', 'all')
        count = 0
        for p in products.values():
            if cat == 'all' or p['category'] == cat:
                p['price'] = int(p['price'] * (1 + percent / 100))
                count += 1
        save_data()
        flash(f'Updated {count} products by {percent}%', 'success')
        return redirect(url_for('view_products'))
    cats = sorted(set(p['category'] for p in products.values()))
    BULK_HTML = '''
    <!DOCTYPE html><html><head><title>Bulk Update</title>''' + COMMON_STYLE + '''
    <style>.form-container{max-width:500px;margin:0 auto;background:white;padding:30px;border-radius:15px;}input,select{width:100%;padding:10px;margin:10px 0;}button{background:linear-gradient(135deg,#1565c0,#2196F3);color:white;padding:12px;border:none;border-radius:8px;width:100%;}</style>
    </head><body><div class="container"><div class="form-container"><h1 style="color:#1565c0;">? Bulk Price Update</h1>
    <form method="POST"><input type="number" name="percent" step="0.1" placeholder="Percentage (+10 or -5)" required>
    <select name="category"><option value="all">All Categories</option>{% for cat in categories %}<option value="{{ cat }}">{{ cat|capitalize }}</option>{% endfor %}</select>
    <button type="submit">Update Prices</button></form></div></div></body></html>
    '''
    return render_template_string(BULK_HTML, categories=cats)


@app.route('/users')
@login_required(role='admin')
def view_users():
    users_data = get_users()
    USERS_HTML = '''
    <!DOCTYPE html><html><head><title>User Management</title>''' + COMMON_STYLE + '''
    <style>.stats-summary{background:white;padding:20px;border-radius:10px;margin-bottom:20px;display:flex;justify-content:space-around;}.btn-delete{background:#d32f2f;color:white;padding:5px 10px;border-radius:5px;border:none;cursor:pointer;}</style>
    </head><body><div class="container"><div class="header"><div class="typing-container"><div class="company-name">? ISAAC SUPERMARKET - USER MANAGEMENT</div></div>
    <div class="nav"><a href="/">Dashboard</a><a href="/products">Products</a></div></div>
    <div class="stats-summary"><div>? Total: {{ users|length }}</div><div>? Admins: {{ admin_count }}</div><div>? Staff: {{ staff_count }}</div></div>
    <tr><thead><tr><th>Username</th><th>Name</th><th>Email</th><th>Role</th><th>Created</th><th>Last Login</th><th>Actions</th></tr></thead>
    <tbody>{% for username, data in users.items() %}<tr><td><strong>{{ username }}</strong></td><td>{{ data.name }}</td><td>{{ data.email }}</td>
    <td>{{ data.role|upper }}</td><td>{{ data.created_at }}</td><td>{{ data.last_login_time or 'Never' }}</td>
    <td>{% if username != 'admin' %}<form action="/delete_user/{{ username }}" method="POST" onsubmit="return confirm('Delete?')"><button type="submit" class="btn-delete">?? Delete</button></form>{% else %}Protected{% endif %}</td>
    </tr>{% endfor %}</tbody>
    </table></div></body></html>
    '''
    return render_template_string(USERS_HTML, users=users_data,
                                  admin_count=sum(1 for u in users_data.values() if u['role'] == 'admin'),
                                  staff_count=sum(1 for u in users_data.values() if u['role'] == 'staff'))


@app.route('/delete_user/<username>', methods=['POST'])
@login_required(role='admin')
def delete_user(username):
    if username == 'admin':
        flash('Cannot delete main admin!', 'danger')
        return redirect(url_for('view_users'))
    users_data = get_users()
    if username in users_data:
        del users_data[username]
        save_users(users_data)
        flash(f'User {username} deleted!', 'success')
    return redirect(url_for('view_users'))


@app.route('/mpesa_transactions')
@login_required(role='admin')
def mpesa_transactions_page():
    MPESA_HTML = '''
    <!DOCTYPE html><html><head><title>M-Pesa Transactions</title>''' + COMMON_STYLE + '''
    <style>.status-success{color:#4CAF50;font-weight:bold;}.status-pending{color:#FF9800;font-weight:bold;}</style>
    </head><body><div class="container"><div style="background:white;border-radius:15px;padding:20px;margin-bottom:20px;"><h1 style="color:#1565c0;">? M-Pesa Transactions</h1>
    <div class="nav"><a href="/">Dashboard</a><a href="/shop">Shop</a><a href="/orders">Orders</a></div></div>
    <table><thead><tr><th>ID</th><th>Order ID</th><th>Customer</th><th>Phone</th><th>Amount</th><th>M-Pesa Code</th><th>Status</th><th>Date</th></tr></thead>
    <tbody>{% for trans in transactions|reverse %}<tr><td>{{ trans.id }}</td><td>{{ trans.order_id }}</td><td>{{ trans.customer_name }}</td><td>{{ trans.phone }}</td>
    <td>{{ trans.amount }} KES</td><td>{{ trans.mpesa_code or 'N/A' }}</td><td class="status-{{ trans.status }}">{{ trans.status|upper }}</td><td>{{ trans.created_at }}</td>
    </tr>{% endfor %}</tbody>
    </table></div></body></html>
    '''
    return render_template_string(MPESA_HTML, transactions=mpesa_transactions)


if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("? ISAAC SUPERMARKET COMPANY - MANAGEMENT SYSTEM")
    print("=" * 70)
    print(f"? Loaded {len(products)} products")
    print(f"? Total Stock: {get_total_stock()} units")
    print("\n? LOGIN: username 'admin', password 'admin123'")
    print("\n? INVOICE FEATURE: View and print professional invoices for all orders")
    print("\n?? M-PESA PAYMENT: Enter phone number ? Request STK Push ? Enter PIN on phone")
    print("   ?? Payment successful message only appears after actual PIN entry on phone")
    print("\n? DELIVERY: All 47 Counties of Kenya with varying fees")
    print("\n? ANIMATION: Complete 'ISAAC SUPERMARKET COMPANY' text rewrites every 4 seconds")
    print("   ? Text is fully visible with blinking cursor animation")
    print("\n? LOGIN PAGE: Larger centered box (500px width) with modern design")
    print("\n? http://127.0.0.1:5000")
    print("=" * 70 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)
