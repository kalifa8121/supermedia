import os
import random
import datetime
import psycopg
from psycopg.rows import dict_row
from flask import (
    Flask, request, redirect, url_for, session, 
    render_template_string, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super_app_secret_key_2026")

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Neon Database Connection Helper (Psycopg 3)
def get_db():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL variable-ni Neon DB hin saagamtine!")
    return psycopg.connect(db_url, row_factory=dict_row)

# Database Initialization
def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            # Users Table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    full_name VARCHAR(100),
                    bio TEXT DEFAULT '',
                    profile_pic TEXT DEFAULT 'https://via.placeholder.com/150',
                    is_admin BOOLEAN DEFAULT FALSE,
                    is_vip BOOLEAN DEFAULT FALSE,
                    is_online BOOLEAN DEFAULT FALSE,
                    status VARCHAR(20) DEFAULT 'ACTIVE',
                    ban_until TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Posts Table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id SERIAL PRIMARY KEY,
                    user_id INT REFERENCES users(id) ON DELETE CASCADE,
                    media_type VARCHAR(20),
                    media_url TEXT,
                    caption TEXT,
                    status VARCHAR(20) DEFAULT 'PENDING',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Default Admin Account
            cur.execute("SELECT * FROM users WHERE username = 'admin'")
            if not cur.fetchone():
                admin_pass = generate_password_hash("admin123")
                cur.execute("""
                    INSERT INTO users (username, password, full_name, is_admin, is_vip)
                    VALUES ('admin', %s, 'Super Admin', TRUE, TRUE)
                """, (admin_pass,))

            conn.commit()

try:
    init_db()
except Exception as e:
    print(f"⚠️ DB Init Warning: {e}")

# HTML Main Layout
BASE_HTML = """
<!DOCTYPE html>
<html lang="om">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SuperApp - Facebook, Telegram & TikTok</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
</head>
<body class="bg-slate-100 text-slate-800">

    <nav class="bg-blue-600 text-white p-3 sticky top-0 z-50 flex justify-between items-center shadow-md">
        <a href="/" class="font-black text-xl tracking-wider">SuperApp</a>
        <div class="flex items-center gap-3">
            {% if session.get('user_id') %}
                <a href="/" class="text-xs font-bold">Feed</a>
                <a href="/users" class="text-xs font-bold">Chat/Calls</a>
                <a href="/profile" class="text-xs font-bold">Profile</a>
                {% if session.get('is_admin') %}
                    <a href="/admin" class="bg-amber-400 text-slate-900 px-2 py-0.5 rounded text-xs font-bold">Admin Panel</a>
                {% endif %}
                <a href="/logout" class="bg-rose-500 text-white px-2 py-0.5 rounded text-xs font-bold">Logout</a>
            {% else %}
                <a href="/login" class="text-xs font-bold">Login</a>
                <a href="/register" class="bg-white text-blue-600 px-2 py-0.5 rounded text-xs font-bold">Register</a>
            {% endif %}
        </div>
    </nav>

    <div class="bg-gradient-to-r from-amber-400 to-amber-500 text-slate-900 text-xs font-bold p-2 text-center">
        🌟 VIP Membership Bitachuuf Admin Contact: 📞 <b>0920689815</b> | Telegram: 💬 <b>@kalifaakka</b>
    </div>

    <div class="max-w-2xl mx-auto p-4">
        {% block content %}{% endblock %}
    </div>

    <div id="callPopup" class="fixed bottom-5 right-5 bg-slate-900 text-white p-4 rounded-2xl shadow-2xl hidden z-50 border border-slate-700">
        <h4 id="callerTitle" class="font-bold text-sm">📞 Video Call...</h4>
        <p class="text-xs text-slate-400 mb-3">Bilbilli isin qaqqabeera.</p>
        <div class="flex gap-2">
            <button onclick="acceptCall()" class="bg-emerald-600 px-3 py-1 rounded text-xs font-bold">Accept</button>
            <button onclick="declineCall()" class="bg-rose-600 px-3 py-1 rounded text-xs font-bold">Decline</button>
        </div>
    </div>

    <script>
        const socket = io();
        const currentUserId = "{{ session.get('user_id', '') }}";

        if (currentUserId) {
            socket.emit('user_online', { user_id: currentUserId });
            socket.on('incoming_call', (data) => {
                if (data.receiver_id == currentUserId) {
                    document.getElementById('callerTitle').innerText = "📞 " + data.caller_name + " is calling...";
                    document.getElementById('callPopup').classList.remove('hidden');
                }
            });
        }

        function acceptCall() { alert("Video Stream Connected!"); document.getElementById('callPopup').classList.add('hidden'); }
        function declineCall() { document.getElementById('callPopup').classList.add('hidden'); }
    </script>
</body>
</html>
"""

# ================= ROUTES =================

@app.route('/')
def feed():
    if 'user_id' not in session:
        return redirect('/login')

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT p.*, u.username, u.full_name, u.profile_pic, u.is_vip 
                FROM posts p JOIN users u ON p.user_id = u.id 
                WHERE p.status = 'APPROVED' 
                ORDER BY p.created_at DESC
            """)
            posts = cur.fetchall()

    content = """
    <div class="bg-white p-4 rounded-2xl shadow-sm border mb-4">
        <h3 class="font-bold text-sm text-slate-700 mb-2">Postii Haaraa Maxxansi</h3>
        <form action="/create_post" method="POST" class="space-y-2">
            <textarea name="caption" placeholder="Maal yaadaa jirta? Video, sagalee, fi barreeffama qoodadhu..." class="w-full p-2 border rounded-xl text-sm outline-none" required></textarea>
            <div class="flex gap-2">
                <select name="media_type" class="border p-2 rounded-xl text-xs">
                    <option value="text">Text Qofa</option>
                    <option value="video">TikTok Video</option>
                    <option value="audio">Voice Note / Audio</option>
                </select>
                <input type="text" name="media_url" placeholder="Media Link (URL)" class="flex-1 p-2 border rounded-xl text-xs">
            </div>
            <button type="submit" class="w-full bg-blue-600 text-white font-bold py-2 rounded-xl text-sm">Maxxansi (Post)</button>
        </form>
    </div>

    <div class="space-y-4">
        {% for p in posts %}
            <div class="bg-white p-4 rounded-2xl shadow-sm border">
                <div class="flex items-center gap-2 mb-2">
                    <img src="{{ p.profile_pic }}" class="w-8 h-8 rounded-full object-cover">
                    <div>
                        <h4 class="font-bold text-xs">{{ p.full_name }} {% if p.is_vip %}<span class="text-amber-500">⭐ VIP</span>{% endif %}</h4>
                        <span class="text-[10px] text-slate-400">@{{ p.username }}</span>
                    </div>
                </div>
                <p class="text-sm mb-2">{{ p.caption }}</p>
                {% if p.media_type == 'video' and p.media_url %}
                    <video src="{{ p.media_url }}" controls class="w-full rounded-xl max-h-80 object-cover"></video>
                    <a href="{{ p.media_url }}" download class="block text-right text-xs font-bold text-emerald-600 mt-1">📥 Video Download</a>
                {% endif %}
            </div>
        {% endfor %}
    </div>
    """
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', content), posts=posts)

@app.route('/create_post', methods=['POST'])
def create_post():
    if 'user_id' not in session: return redirect('/login')

    caption = request.form.get('caption')
    media_type = request.form.get('media_type')
    media_url = request.form.get('media_url')

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO posts (user_id, media_type, media_url, caption, status)
                VALUES (%s, %s, %s, %s, 'PENDING')
            """, (session['user_id'], media_type, media_url, caption))
            conn.commit()

    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', """
        <div class="bg-white p-6 rounded-2xl shadow text-center my-10">
            <h2 class="text-emerald-600 font-bold text-lg mb-2">✅ Postiin keessan ergameera!</h2>
            <p class="text-xs text-slate-500 mb-4">Postiin keessan sa'aatii gabaabaa keessatti uummataaf (public) kan dhihaatu ta'a.</p>
            <a href="/" class="bg-blue-600 text-white font-bold px-4 py-2 rounded-xl text-xs">Gara Feed</a>
        </div>
    """))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password').strip()
        full_name = request.form.get('full_name').strip()

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users WHERE username = %s", (username,))
                if cur.fetchone(): return "Usernamiin kun qabatameera!"
                
                hashed_p = generate_password_hash(password)
                cur.execute("INSERT INTO users (username, password, full_name) VALUES (%s, %s, %s)", (username, hashed_p, full_name))
                conn.commit()

        return redirect('/login')

    content = """
    <div class="bg-white p-6 rounded-2xl shadow-sm border max-w-sm mx-auto my-10">
        <h2 class="font-bold text-lg mb-4">Galmee Maammilaa</h2>
        <form method="POST" class="space-y-3">
            <input type="text" name="full_name" placeholder="Maqaa Guutuu" class="w-full p-2 border rounded-xl text-sm" required>
            <input type="text" name="username" placeholder="Username" class="w-full p-2 border rounded-xl text-sm" required>
            <input type="password" name="password" placeholder="Password" class="w-full p-2 border rounded-xl text-sm" required>
            <button type="submit" class="w-full bg-blue-600 text-white font-bold py-2 rounded-xl text-sm">Galmaa'i</button>
        </form>
    </div>
    """
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', content))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password').strip()

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE username = %s", (username,))
                user = cur.fetchone()

        if user and check_password_hash(user['password'], password):
            if user['status'] == 'BANNED': return "🚫 Akkaawunttiin keessan UGGURAMEERA!"
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']
            return redirect('/')
        return "Username ykn Password dogoggoraa!"

    content = """
    <div class="bg-white p-6 rounded-2xl shadow-sm border max-w-sm mx-auto my-10">
        <h2 class="font-bold text-lg mb-4">Seensa Maammilaa (Login)</h2>
        <form method="POST" class="space-y-3">
            <input type="text" name="username" placeholder="Username" class="w-full p-2 border rounded-xl text-sm" required>
            <input type="password" name="password" placeholder="Password" class="w-full p-2 border rounded-xl text-sm" required>
            <button type="submit" class="w-full bg-blue-600 text-white font-bold py-2 rounded-xl text-sm">Seeni</button>
        </form>
    </div>
    """
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', content))

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/admin')
def admin_panel():
    if not session.get('is_admin'): return "🚫 Hayyama Admin qofa!", 403

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT p.*, u.username FROM posts p 
                JOIN users u ON p.user_id = u.id 
                WHERE p.status = 'PENDING'
            """)
            pending_posts = cur.fetchall()

            cur.execute("SELECT * FROM users WHERE is_admin = FALSE")
            users = cur.fetchall()

    content = """
    <div class="bg-white p-4 rounded-2xl shadow-sm border mb-4">
        <h2 class="font-bold text-amber-600 mb-2">🛡️ Admin Control Panel</h2>
        <h4 class="font-bold text-xs text-slate-700 mb-2">Postii Mirkaneessa Eegaan</h4>
        {% for p in pending_posts %}
            <div class="bg-slate-50 p-2.5 rounded-xl border mb-2 flex justify-between items-center text-xs">
                <div><b>@{{ p.username }}:</b> {{ p.caption }}</div>
                <div class="flex gap-1">
                    <a href="/admin/approve_post/{{ p.id }}" class="bg-emerald-600 text-white px-2 py-1 rounded font-bold">Approve</a>
                    <a href="/admin/reject_post/{{ p.id }}" class="bg-rose-600 text-white px-2 py-1 rounded font-bold">Reject</a>
                </div>
            </div>
        {% endfor %}
    </div>

    <div class="bg-white p-4 rounded-2xl shadow-sm border">
        <h4 class="font-bold text-xs text-slate-700 mb-2">Users Control</h4>
        {% for u in users %}
            <div class="py-2 border-b flex justify-between items-center text-xs">
                <div><b>{{ u.full_name }}</b> (@{{ u.username }})</div>
                <a href="/admin/ban_user/{{ u.id }}" class="bg-rose-600 text-white px-2 py-1 rounded font-bold">Ban User</a>
            </div>
        {% endfor %}
    </div>
    """
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', content), pending_posts=pending_posts, users=users)

@app.route('/admin/approve_post/<int:post_id>')
def approve_post(post_id):
    if not session.get('is_admin'): return "Unauthorized", 403
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE posts SET status = 'APPROVED' WHERE id = %s", (post_id,))
            conn.commit()
    return redirect('/admin')

@app.route('/admin/reject_post/<int:post_id>')
def reject_post(post_id):
    if not session.get('is_admin'): return "Unauthorized", 403
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM posts WHERE id = %s", (post_id,))
            conn.commit()
    return redirect('/admin')

@app.route('/admin/ban_user/<int:user_id>')
def ban_user(user_id):
    if not session.get('is_admin'): return "Unauthorized", 403
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET status = 'BANNED' WHERE id = %s", (user_id,))
            conn.commit()
    return redirect('/admin')

@socketio.on('user_online')
def handle_online(data):
    user_id = data.get('user_id')
    if user_id:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET is_online = TRUE WHERE id = %s", (user_id,))
                conn.commit()

@socketio.on('start_call')
def handle_call(data):
    emit('incoming_call', data, broadcast=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=True)
