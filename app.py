from flask import Flask, render_template, request, redirect, url_for, session, flash
from pymongo import MongoClient
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash
import os
from bson.objectid import ObjectId
from dotenv import load_dotenv
from datetime import datetime
from authlib.integrations.flask_client import OAuth

# ================================
# 🔧 CONFIGURACIÓN BÁSICA
# ================================
load_dotenv()

app = Flask(__name__)

# 🔐 CLAVE SEGURA
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24).hex())

# Configuración de sesión básica pero segura
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # 30 min

# ================================
# 🗄️ MONGODB
# ================================
MONGO_URI = os.getenv('MONGODB_URI')
if not MONGO_URI:
    raise ValueError("❌ Configura MONGODB_URI en .env")

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
client.admin.command('ismaster')  # probar conexión

db = client['URLS']
yapo_collection = db['Yapo']
users_collection = db['users']

# ================================
# 🔑 OAUTH GOOGLE
# ================================
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    access_token_url='https://oauth2.googleapis.com/token',
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    client_kwargs={'scope': 'openid email profile'}
)

# ================================
# 🛡️ DECORADORES
# ================================
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session and 'email' not in session:
            flash('Inicia sesión para continuar.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ================================
# 🖼️ FUNCIONES AUXILIARES
# ================================
def load_logos():
    try:
        logos_dir = os.path.join(app.static_folder, 'logos')
        if os.path.exists(logos_dir):
            images = ['logos/' + f for f in os.listdir(logos_dir) 
                     if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))]
            return sorted(images) if images else ['logo.png']
    except:
        pass
    return ['logo.png']

def load_property_images():
    try:
        dir_path = os.path.join(app.static_folder, 'propiedades')
        if os.path.exists(dir_path):
            images = ['propiedades/' + f for f in os.listdir(dir_path)
                     if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))]
            return sorted(images) if images else ['propiedades/default.jpg']
    except:
        pass
    return ['propiedades/default.jpg']

def validate_input(text, max_len=50, allowed_chars=None):
    if not text or len(text) > max_len:
        return False
    if allowed_chars and any(c not in allowed_chars + 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in text.lower()):
        return False
    return True

# ================================
# 📍 RUTAS PRINCIPALES
# ================================
@app.route('/')
def index():
    return redirect(url_for('login'))

# ================================
# 🔐 LOGIN TRADICIONAL
# ================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session or 'email' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not validate_input(username, 50) or not password:
            flash('Datos inválidos.', 'error')
            return render_template('login.html', images=load_property_images())
        
        user = users_collection.find_one({'username': username})
        if user and check_password_hash(user['password'], password):
            session['username'] = username
            session['last_activity'] = datetime.now().timestamp()
            flash('¡Bienvenido!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Usuario o contraseña incorrectos.', 'error')
    
    return render_template('login.html', images=load_property_images())

# ================================
# 🔑 LOGIN CON GOOGLE
# ================================
@app.route('/login/google')
def login_google():
    return google.authorize_redirect(url_for('authorize', _external=True))

@app.route('/authorize')
def authorize():
    token = google.authorize_access_token()
    user_info = google.parse_id_token(token)
    email = user_info.get('email')

    # Verificar si el correo está en Mongo
    user = users_collection.find_one({'email': email})
    if not user:
        flash('Tu correo no está autorizado. Contacta al administrador.', 'error')
        return redirect(url_for('login'))
    
    session['email'] = email
    session['last_activity'] = datetime.now().timestamp()
    flash(f'Bienvenido {email}!', 'success')
    return redirect(url_for('dashboard'))

# ================================
# 🚪 LOGOUT
# ================================
@app.route('/logout')
def logout():
    session.clear()
    flash('Sesión cerrada.', 'info')
    return redirect(url_for('login'))

# ================================
# 📊 DASHBOARD
# ================================
@app.route('/dashboard')
@login_required
def dashboard():
    try:
        page = max(1, min(int(request.args.get('page', 1)), 1000))
        per_page = max(1, min(int(request.args.get('per_page', 10)), 100))
        skip = (page - 1) * per_page
        
        total_items = yapo_collection.count_documents({})
        pipeline = [
            {"$sort": {"_id": -1}},
            {"$skip": skip},
            {"$limit": per_page},
            {"$project": {
                "title": {"$ifNull": ["$title", "Sin título"]},
                "category": {"$ifNull": ["$category", "General"]},
                "price": 1,
                "location": 1,
                "date": 1
            }}
        ]
        
        data = list(yapo_collection.aggregate(pipeline, maxTimeMS=10000))
        total_pages = (total_items + per_page - 1) // per_page
        
        processed_data = []
        for item in data:
            processed = dict(item)
            processed['_id_str'] = str(processed.pop('_id', ''))
            for field in ['title', 'category', 'location']:
                if field in processed and isinstance(processed[field], str):
                    processed[field] = processed[field][:100]
            if 'date' in processed:
                try:
                    if isinstance(processed['date'], str):
                        processed['date_formatted'] = datetime.fromisoformat(
                            processed['date'].replace('Z', '+00:00')
                        ).strftime('%d/%m/%Y')
                    else:
                        processed['date_formatted'] = processed['date'].strftime('%d/%m/%Y')
                except:
                    processed['date_formatted'] = 'Fecha inválida'
            processed_data.append(processed)
        
        logos = load_logos()
        return render_template(
            'dashboard.html',
            data=processed_data,
            total_items=total_items,
            current_page=page,
            page_size=per_page,
            total_pages=total_pages,
            logos=logos,
            username=session.get('username') or session.get('email')
        )
        
    except Exception as e:
        print(f"Error dashboard: {e}")
        flash('Error cargando datos.', 'error')
        return render_template(
            'dashboard.html', 
            data=[], total_items=0, current_page=1, 
            page_size=10, total_pages=1, logos=load_logos(),
            username=session.get('username') or session.get('email')
        )

# ================================
# 👁️ DETALLE
# ================================
@app.route('/detail/<id>')
@login_required
def detail(id):
    try:
        if not ObjectId.is_valid(id):
            flash('ID inválido.', 'error')
            return redirect(url_for('dashboard'))
        
        item = yapo_collection.find_one(
            {'_id': ObjectId(id)},
            {'title': 1, 'category': 1, 'price': 1, 'location': 1, 
             'description': 1, 'date': 1, 'images': 1},
            maxTimeMS=5000
        )
        
        if not item:
            flash('Elemento no encontrado.', 'error')
            return redirect(url_for('dashboard'))
        
        processed = dict(item)
        processed['_id_str'] = str(processed.pop('_id', ''))
        processed['title'] = processed.get('title', 'Sin título')[:100]
        processed['category'] = processed.get('category', 'General')
        if 'description' in processed and isinstance(processed['description'], str):
            processed['description'] = processed['description'][:500]
        if 'date' in processed:
            try:
                if isinstance(processed['date'], str):
                    processed['date_formatted'] = datetime.fromisoformat(
                        processed['date'].replace('Z', '+00:00')
                    ).strftime('%d/%m/%Y %H:%M')
                else:
                    processed['date_formatted'] = processed['date'].strftime('%d/%m/%Y %H:%M')
            except:
                processed['date_formatted'] = 'Sin fecha'
        
        logos = load_logos()
        return render_template('detail.html', item=processed, logos=logos)
        
    except Exception as e:
        print(f"Error detail: {e}")
        flash('Error cargando detalles.', 'error')
        return redirect(url_for('dashboard'))

# ================================
# ❌ ERRORES
# ================================
@app.errorhandler(404)
def not_found(e):
    return render_template('404.html', logos=load_logos()), 404

@app.errorhandler(500)
def internal_error(e):
    flash('Error del servidor.', 'error')
    return render_template('500.html', logos=load_logos()), 500

# ================================
# 🛠️ CREAR ADMIN
# ================================
def create_admin_if_needed():
    if os.getenv('FLASK_ENV') == 'development':
        if not users_collection.find_one({'username': 'admin'}):
            hashed = generate_password_hash('admin2024!')
            users_collection.insert_one({
                'username': 'admin',
                'email': 'admin@tuempresa.com',
                'password': hashed,
                'role': 'admin',
                'created_at': datetime.now()
            })
            print("👤 Admin creado: admin / admin2024!")

# ================================
# 🚀 EJECUTAR
# ================================
if __name__ == '__main__':
    print("🚀 Iniciando app...")
    create_admin_if_needed()
    port = int(os.environ.get('PORT', 5000))
    host = '0.0.0.0' if os.getenv('PORT') else '127.0.0.1'
    print(f"🌐 http://{host}:{port}")
    app.run(debug=True, host=host, port=port)
