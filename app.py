import os
import random
import datetime
import psycopg2
from psycopg2.extras import DictCursor
from flask import (
    Flask, request, redirect, url_for, session, 
    render_template_string, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super_app_secret_key_2026")

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Database Connection Helper (Neon PostgreSQL)
def get_db():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL environment variable is not set!")
    return psycopg2.connect(db_url, cursor_factory=DictCursor)

# Database Initialization
def init_db():
    conn = get_db()
    cur = conn.cursor()
    
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
            status VARCHAR(20) DEFAULT 'ACTIVE', -- ACTIVE, WARNED, BANNED
            ban_until TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Posts Table (Stealth Approval System)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id SERIAL PRIMARY KEY,
            user_id INT REFERENCES users(id) ON DELETE CASCADE,
            media_type VARCHAR(20), -- text, video, audio, live
            media_url TEXT,
            caption TEXT,
            status VARCHAR(20) DEFAULT 'PENDING', -- PENDING, APPROVED, REJECTED
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Comments Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id SERIAL PRIMARY KEY,
            post_id INT REFERENCES posts(id) ON DELETE CASCADE,
            user_id INT REFERENCES users(id) ON DELETE CASCADE,
            comment_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Friendships Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS friendships (
            id SERIAL PRIMARY KEY,
            requester_id INT REFERENCES users(id),
            addressee_id INT REFERENCES users(id),
            status VARCHAR(20) DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Call Logs & Notifications Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            user_id INT REFERENCES users(id) ON DELETE CASCADE,
            type VARCHAR(50),
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Create Default Admin User
    cur.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cur.fetchone():
        admin_pass = generate_password_hash("admin123")
        cur.execute("""
            INSERT INTO users (username, password, full_name, is_admin, is_vip)
            VALUES ('admin', %s, 'Super Admin', TRUE, TRUE)
        """, (admin_pass,))

    conn.commit()
    cur.close()
    conn.close()

try:
    init_db()
except Exception as e:
    print(f"⚠️ DB Init Warning: {e}")

# HTML Template (Facebook / Telegram / TikTok Hybrid Layout)
BASE_HTML = """
<!DOCTYPE html>
<html lang="om">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Super Social Platform</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        .vip-banner { background: linear-gradient(135deg, #fbbf24, #f59e0b); }
        .tiktok-aspect { aspect-ratio: 9/16; }
    </style>
</head>
<body class="bg-slate-100 text-slate-800">

    <!-- Top Navigation Bar -->
    <nav class="bg-blue-600 text-white p-3 sticky top-0 z-50 flex justify-between items-center shadow-md">
        <a href="/" class="font-extrabold text-xl tracking-wider">SuperApp</a>
        <div class="flex items-center gap-3">
            {% if session.get('user_id') %}
                <a href="/" class="text-sm font-semibold">Feed</a>
                <a href="/users" class="text-sm font-semibold">Chat & Users</a>
                <a href="/profile" class="text-sm font-semibold">Profile</a>
                {% if session.get('is_admin') %}
                    <a href="/admin" class="bg-amber-500 px-2 py-1 rounded text-xs font-bold text-slate-900">Admin Panel</a>
                {% endif %}
                <a href="/logout" class="bg-rose-500 px-2.5 py-1 rounded text-xs font-bold">Logout</a>
            {% else %}
                <a href="/login" class="text-sm font-bold">Login</a>
                <a href="/register" class="bg-white text-blue-600 px-3 py-1 rounded text-sm font-bold">Register</a>
            {% endif %}
        </div>
    </nav>

    <!-- VIP Promo Alert Banner -->
    <div class="vip-banner text-slate-900 text-xs font-bold p-2 text-center shadow-sm">
        🌟 VIP Membership Bitachuuf Admin Contact: 📞 <b>0920689815</b> | Telegram: 💬 <b>@kalifaakka</b>
    </div>

    <!-- Main Container -->
    <div class="max-w-3xl mx-auto p-3">
        {% block content %}{% endblock %}
    </div>

    <!-- Video Calling Dialog / Incoming Ringing Popup -->
    <div id="callPopup" class="fixed bottom-5 right-5 bg-slate-900 text-white p-4 rounded-xl shadow-2xl hidden z-50 border border-slate-700">
        <h4 id="callerTitle" class="font-bold text-sm">📞 Inbound Video Call...</h4>
        <p class="text-xs text-slate-400 mb-3">Bilbilli isaan irraa isin qaqqabeera.</p>
        <div class="flex gap-2">
            <button onclick="acceptCall()" class="bg-emerald-600 px-3 py-1.5 rounded text-xs font-bold">Accept</button>
            <button onclick="declineCall()" class="bg-rose-600 px-3 py-1.5 rounded text-xs font-bold">Decline</button>
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

        function acceptCall() {
            alert("Video Stream Connected!");
            document.getElementById('callPopup').classList.add('hidden');
        }

        function declineCall() {
            document.getElementById('callPopup').classList.add('hidden');
        }
    </script>
</body>
</html>
"""

# ================= APP ROUTES =================

@app.route('/')
def feed():
    if 'user_id' not in session:
        return redirect('/login')

    conn = get_db()
    cur = conn.cursor()
    
    # Only show approved posts to users
    cur.execute("""
        SELECT p.*, u.username, u.full_name, u.profile_pic, u.is_vip 
        FROM posts p JOIN users u ON p.user_id = u.id 
        WHERE p.status = 'APPROVED' 
        ORDER BY p.created_at DESC
    """)
    posts = cur.fetchall()
    cur.close()
    conn.close()

    content = """
    <!-- Create Post Box -->
    <div class="bg-white p-4 rounded-xl shadow-sm border border-slate-200 mb-4">
        <h3 class="font-bold text-sm text-slate-700 mb-2">Postii Haaraa Maxxansi</h3>
        <form action="/create_post" method="POST" class="space-y-2">
            <textarea name="caption" placeholder="Maal yaadaa jirta? Video, sagalee, fi barreeffama qoodadhu..." class="w-full p-2.5 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500" required></textarea>
            <div class="flex gap-2">
                <select name="media_type" class="border p-2 rounded text-xs bg-slate-50">
                    <option value="text">Text Qofa</option>
                    <option value="video">TikTok Video (Short)</option>
                    <option value="audio">Voice Note / Audio</option>
                </select>
                <input type="text" name="media_url" placeholder="Media Link (URL)" class="flex-1 p-2 border rounded text-xs">
            </div>
            <button type="submit" class="w-full bg-blue-600 text-white font-bold py-2 rounded-lg text-sm">Maxxansi (Post)</button>
        </form>
    </div>

    <!-- Approved Feed Posts -->
    <div class="space-y-4">
        {% for p in posts %}
            <div class="bg-white p-4 rounded-xl shadow-sm border border-slate-200">
                <div class="flex items-center gap-2 mb-2">
                    <img src="{{ p.profile_pic }}" class="w-9 h-9 rounded-full object-cover">
                    <div>
                        <h4 class="font-bold text-xs">{{ p.full_name }} {% if p.is_vip %}<span class="text-amber-500">⭐ VIP</span>{% endif %}</h4>
                        <span class="text-[10px] text-slate-400">@{{ p.username }}</span>
                    </div>
                </div>

                <p class="text-sm text-slate-800 mb-2">{{ p.caption }}</p>

                {% if p.media_type == 'video' and p.media_url %}
                    <div class="bg-black rounded-lg overflow-hidden my-2">
                        <video src="{{ p.media_url }}" controls class="w-full max-h-96 object-contain"></video>
                        <div class="p-2 bg-slate-900 text-right">
                            <a href="{{ p.media_url }}" download target="_blank" class="bg-emerald-600 text-white text-xs px-3 py-1 rounded font-bold">📥 Save / Download Video</a>
                        </div>
                    </div>
                {% elif p.media_type == 'audio' and p.media_url %}
                    <div class="bg-slate-50 p-3 rounded-lg border my-2">
                        <audio src="{{ p.media_url }}" controls class="w-full mb-1"></audio>
                        <a href="{{ p.media_url }}" download target="_blank" class="text-xs font-bold text-emerald-600">📥 Audio Download</a>
                    </div>
                {% endif %}
            </div>
        {% endfor %}
    </div>
    """
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', content), posts=posts)

@app.route('/create_post', methods=['POST'])
def create_post():
    if 'user_id' not in session:
        return redirect('/login')

    caption = request.form.get('caption')
    media_type = request.form.get('media_type')
    media_url = request.form.get('media_url')

    conn = get_db()
    cur = conn.cursor()
    
    # Save post with PENDING status (stealth moderation)
    cur.execute("""
        INSERT INTO posts (user_id, media_type, media_url, caption, status)
        VALUES (%s, %s, %s, %s, 'PENDING')
    """, (session['user_id'], media_type, media_url, caption))
    
    conn.commit()
    cur.close()
    conn.close()

    # Stealth User Response (User sees success message only)
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', """
        <div class="bg-white p-6 rounded-xl shadow border text-center my-10">
            <h2 class="text-emerald-600 font-bold text-lg mb-2">✅ Postiin keessan milkaa'inaan ergameera!</h2>
            <p class="text-xs text-slate-500 mb-4">Postiin keessan sa'aatii gabaabaa keessatti uummataaf (public) kan dhihaatu ta'a.</p>
            <a href="/" class="bg-blue-600 text-white font-bold px-4 py-2 rounded text-xs">Gara Feed</a>
        </div>
    """))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password').strip()
        full_name = request.form.get('full_name').strip()

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return "Usernamiin kun duraan qabatameera!"

        hashed_p = generate_password_hash(password)
        cur.execute("INSERT INTO users (username, password, full_name) VALUES (%s, %s, %s)", (username, hashed_p, full_name))
        conn.commit()
        cur.close()
        conn.close()
        return redirect('/login')

    content = """
    <div class="bg-white p-6 rounded-xl shadow-sm border max-w-md mx-auto my-10">
        <h2 class="font-bold text-lg mb-4">Galmee Maammilaa (Sign Up)</h2>
        <form method="POST" class="space-y-3">
            <input type="text" name="full_name" placeholder="Maqaa Guutuu" class="w-full p-2.5 border rounded text-sm" required>
            <input type="text" name="username" placeholder="Username" class="w-full p-2.5 border rounded text-sm" required>
            <input type="password" name="password" placeholder="Password" class="w-full p-2.5 border rounded text-sm" required>
            <button type="submit" class="w-full bg-blue-600 text-white font-bold py-2 rounded text-sm">Galmaa'i</button>
        </form>
    </div>
    """
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', content))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password').strip()

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and check_password_hash(user['password'], password):
            if user['status'] == 'BANNED':
                return "🚫 Akkaawunttiin keessan seera darbuu keessaniif UGGURAMEERA!"

            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']
            return redirect('/')
        else:
            return "Username ykn Password dogoggoraa!"

    content = """
    <div class="bg-white p-6 rounded-xl shadow-sm border max-w-md mx-auto my-10">
        <h2 class="font-bold text-lg mb-4">Seensa Maammilaa (Login)</h2>
        <form method="POST" class="space-y-3">
            <input type="text" name="username" placeholder="Username" class="w-full p-2.5 border rounded text-sm" required>
            <input type="password" name="password" placeholder="Password" class="w-full p-2.5 border rounded text-sm" required>
            <button type="submit" class="w-full bg-blue-600 text-white font-bold py-2 rounded text-sm">Seeni</button>
        </form>
    </div>
    """
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', content))

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect('/login')

    conn = get_db()
    cur = conn.cursor()

    if request.method == 'POST':
        full_name = request.form.get('full_name')
        bio = request.form.get('bio')
        profile_pic = request.form.get('profile_pic')

        cur.execute("UPDATE users SET full_name = %s, bio = %s, profile_pic = %s WHERE id = %s",
                    (full_name, bio, profile_pic, session['user_id']))
        conn.commit()

    cur.execute("SELECT * FROM users WHERE id = %s", (session['user_id'],))
    user = cur.fetchone()
    cur.close()
    conn.close()

    content = f"""
    <div class="bg-white p-6 rounded-xl shadow-sm border max-w-md mx-auto">
        <h2 class="font-bold text-lg mb-4">Profile Edit Godhi</h2>
        <form method="POST" class="space-y-3">
            <label class="text-xs font-bold text-slate-600">Maqaa Guutuu:</label>
            <input type="text" name="full_name" value="{user['full_name']}" class="w-full p-2 border rounded text-sm" required>
            
            <label class="text-xs font-bold text-slate-600">Bio / Seenaa Gabaabaa:</label>
            <input type="text" name="bio" value="{user['bio']}" class="w-full p-2 border rounded text-sm">
            
            <label class="text-xs font-bold text-slate-600">Profile Picture URL:</label>
            <input type="text" name="profile_pic" value="{user['profile_pic']}" class="w-full p-2 border rounded text-sm">
            
            <button type="submit" class="w-full bg-emerald-600 text-white font-bold py-2 rounded text-sm">Save Changes</button>
        </form>
    </div>
    """
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', content))

@app.route('/users')
def users_list():
    if 'user_id' not in session:
        return redirect('/login')

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, username, full_name, profile_pic, is_online FROM users WHERE id != %s", (session['user_id'],))
    users = cur.fetchall()
    cur.close()
    conn.close()

    content = """
    <div class="bg-white p-4 rounded-xl shadow-sm border">
        <h3 class="font-bold text-sm text-slate-700 mb-3">Maammiltoota (Online & Offline Users)</h3>
        <div class="divide-y">
            {% for u in users %}
                <div class="py-2 flex items-center justify-between">
                    <div class="flex items-center gap-2">
                        <span class="w-2.5 h-2.5 rounded-full {% if u.is_online %}bg-emerald-500{% else %}bg-slate-300{% endif %}"></span>
                        <img src="{{ u.profile_pic }}" class="w-8 h-8 rounded-full object-cover">
                        <div>
                            <h5 class="font-bold text-xs">{{ u.full_name }}</h5>
                            <span class="text-[10px] text-slate-400">@{{ u.username }}</span>
                        </div>
                    </div>
                    <button onclick="triggerCall({{ u.id }}, '{{ u.full_name }}')" class="bg-blue-600 text-white text-xs px-3 py-1 rounded font-bold">📞 Video Call</button>
                </div>
            {% endfor %}
        </div>
    </div>

    <script>
        function triggerCall(receiverId, name) {
            socket.emit('start_call', {
                caller_id: currentUserId,
                receiver_id: receiverId,
                caller_name: "{{ session.get('username') }}"
            });
            alert("Gara " + name + " tti bilbilamaa jira...");
        }
    </script>
    """
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', content), users=users)

# ================= ADMIN CONTROL ROUTE =================

@app.route('/admin')
def admin_panel():
    if 'user_id' not in session or not session.get('is_admin'):
        return "🚫 Hayyama Admin qofa!", 403

    conn = get_db()
    cur = conn.cursor()

    # Get Pending Posts for Moderation
    cur.execute("""
        SELECT p.*, u.username FROM posts p 
        JOIN users u ON p.user_id = u.id 
        WHERE p.status = 'PENDING'
    """)
    pending_posts = cur.fetchall()

    # Get Users for Ban Management
    cur.execute("SELECT * FROM users WHERE is_admin = FALSE")
    users = cur.fetchall()

    cur.close()
    conn.close()

    content = """
    <div class="bg-white p-4 rounded-xl shadow-sm border mb-4">
        <h2 class="font-bold text-base text-amber-600 mb-2">🛡️ Admin Control Panel</h2>
        <h4 class="font-bold text-xs text-slate-700 mb-2">Postii Mirkaneessa Eegaan (Stealth Moderation)</h4>
        
        {% for p in pending_posts %}
            <div class="bg-slate-50 p-3 rounded border mb-2 flex justify-between items-center">
                <div>
                    <span class="font-bold text-xs">@{{ p.username }}:</span>
                    <p class="text-xs text-slate-600">{{ p.caption }}</p>
                </div>
                <div class="flex gap-1">
                    <a href="/admin/approve_post/{{ p.id }}" class="bg-emerald-600 text-white text-xs px-2.5 py-1 rounded font-bold">Approve</a>
                    <a href="/admin/reject_post/{{ p.id }}" class="bg-rose-600 text-white text-xs px-2.5 py-1 rounded font-bold">Reject</a>
                </div>
            </div>
        {% endfor %}
    </div>

    <div class="bg-white p-4 rounded-xl shadow-sm border">
        <h4 class="font-bold text-xs text-slate-700 mb-2">Bulchiinsa Maammiltootaa (Adabbii / Ban)</h4>
        {% for u in users %}
            <div class="py-2 border-b flex justify-between items-center text-xs">
                <div><b>{{ u.full_name }}</b> (@{{ u.username }}) - Status: {{ u.status }}</div>
                <a href="/admin/ban_user/{{ u.id }}" class="bg-rose-600 text-white text-[10px] px-2 py-1 rounded font-bold">🚫 Ban User</a>
            </div>
        {% endfor %}
    </div>
    """
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', content), pending_posts=pending_posts, users=users)

@app.route('/admin/approve_post/<int:post_id>')
def approve_post(post_id):
    if not session.get('is_admin'): return "Unauthorized", 403
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE posts SET status = 'APPROVED' WHERE id = %s", (post_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect('/admin')

@app.route('/admin/reject_post/<int:post_id>')
def reject_post(post_id):
    if not session.get('is_admin'): return "Unauthorized", 403
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM posts WHERE id = %s", (post_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect('/admin')

@app.route('/admin/ban_user/<int:user_id>')
def ban_user(user_id):
    if not session.get('is_admin'): return "Unauthorized", 403
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET status = 'BANNED' WHERE id = %s", (user_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect('/admin')

# ================= SOCKET.IO EVENTS =================

@socketio.on('user_online')
def handle_online(data):
    user_id = data.get('user_id')
    if user_id:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE users SET is_online = TRUE WHERE id = %s", (user_id,))
        conn.commit()
        cur.close()
        conn.close()

@socketio.on('start_call')
def handle_call(data):
    emit('incoming_call', data, broadcast=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=True)
