# register_user.py
from pymongo import MongoClient
from werkzeug.security import generate_password_hash

# Configuración de MongoDB
MONGO_URI = "mongodb+srv://pgalleguil:vLr5MTTZ7kcNzjSZ@cluster0.mzve39k.mongodb.net/?retryWrites=true&w=majority"
DB_NAME = "URLS"

# Conexión a MongoDB
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
users_collection = db['users']

def register_user():
    username = input("Ingrese el nombre de usuario: ")
    password = input("Ingrese la contraseña: ")  # Usamos input para mostrar la contraseña

    # Verificar si el usuario ya existe
    if users_collection.find_one({'username': username}):
        print("Error: El usuario ya existe.")
        return

    # Generar hash de la contraseña
    hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

    # Guardar el usuario en la base de datos
    user = {
        'username': username,
        'password': hashed_password
    }
    users_collection.insert_one(user)
    print(f"Usuario {username} registrado exitosamente.")

if __name__ == "__main__":
    try:
        register_user()
    except Exception as e:
        print(f"Error al registrar el usuario: {e}")
    finally:
        client.close()