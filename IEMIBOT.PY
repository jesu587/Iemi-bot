import os
import re
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import mysql.connector
from mysql.connector import pooling, Error
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)

# Configuración del pool de conexiones a la base de datos
db_pool = pooling.MySQLConnectionPool(
    pool_name="mypool",
    pool_size=5,
    host=os.getenv("DB_HOST"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME")
)

# Diccionario para almacenar el estado de los usuarios
usuarios = {}

def obtener_conexion():
    """Obtiene una conexión del pool de MySQL"""
    try:
        return db_pool.get_connection()
    except Error as e:
        print(f"❌ Error en la conexión con MySQL: {e}")
        return None

def cita_disponible(fecha, hora):
    """Verifica si ya existe una cita en la misma fecha y hora"""
    conexion = obtener_conexion()
    if not conexion:
        return False

    try:
        cursor = conexion.cursor()
        cursor.execute("SELECT COUNT(*) FROM citas WHERE fecha = %s AND hora = %s", (fecha, hora))
        resultado = cursor.fetchone()
        return resultado[0] == 0  # Devuelve True si no hay citas en esa fecha y hora
    except Error as e:
        print(f"❌ Error al verificar disponibilidad: {e}")
        return False
    finally:
        cursor.close()
        conexion.close()

def guardar_cita(nombre, telefono, fecha, hora):
    """Guarda la cita en la base de datos"""
    conexion = obtener_conexion()
    if not conexion:
        return False

    try:
        cursor = conexion.cursor()
        sql = "INSERT INTO citas (nombre, telefono, fecha, hora) VALUES (%s, %s, %s, %s)"
        valores = (nombre, telefono, fecha, hora)
        cursor.execute(sql, valores)
        conexion.commit()
        return True
    except Error as e:
        print(f"❌ Error al guardar la cita: {e}")
        return False
    finally:
        cursor.close()
        conexion.close()

@app.route("/bot", methods=["POST"])
def bot():
    numero = request.form.get("From")
    mensaje = request.form.get("Body").strip().lower()
    respuesta = MessagingResponse()
    mensaje_respuesta = respuesta.message()

    # Verifica si es un usuario nuevo
    if numero not in usuarios:
        usuarios[numero] = {"estado": "inicio"}

    estado = usuarios[numero]["estado"]

    # Diccionario de estados
    estados = {
        "inicio": preguntar_nombre,
        "preguntar_nombre": preguntar_telefono,
        "preguntar_telefono": preguntar_fecha,
        "preguntar_fecha": preguntar_hora,
        "preguntar_hora": confirmar_cita
    }

    # Ejecuta la función correspondiente al estado
    if estado in estados:
        return estados[estado](numero, mensaje, mensaje_respuesta)

    return str(respuesta)

def preguntar_nombre(numero, mensaje, mensaje_respuesta):
    """Solicita el nombre del usuario"""
    usuarios[numero]["nombre"] = mensaje
    mensaje_respuesta.body(f"Gracias, {mensaje}. ¿Cuál es tu número de teléfono?")
    usuarios[numero]["estado"] = "preguntar_telefono"
    return str(mensaje_respuesta)

def preguntar_telefono(numero, mensaje, mensaje_respuesta):
    """Solicita el número de teléfono"""
    if re.match(r"^\+?[0-9]{10,15}$", mensaje):
        usuarios[numero]["telefono"] = mensaje
        mensaje_respuesta.body("📅 ¿Para qué fecha deseas la matrícula? (Formato: YYYY-MM-DD)")
        usuarios[numero]["estado"] = "preguntar_fecha"
    else:
        mensaje_respuesta.body("❌ Formato de teléfono inválido. Intenta nuevamente.")
    return str(mensaje_respuesta)

def preguntar_fecha(numero, mensaje, mensaje_respuesta):
    """Solicita la fecha de la cita"""
    if re.match(r"^\d{4}-\d{2}-\d{2}$", mensaje):
        usuarios[numero]["fecha"] = mensaje
        mensaje_respuesta.body("⏰ ¿A qué hora? (Formato: HH:MM en formato 24 horas)")
        usuarios[numero]["estado"] = "preguntar_hora"
    else:
        mensaje_respuesta.body("❌ Formato de fecha inválido. Usa YYYY-MM-DD.")
    return str(mensaje_respuesta)

def preguntar_hora(numero, mensaje, mensaje_respuesta):
    """Solicita la hora de la cita"""
    if re.match(r"^\d{2}:\d{2}$", mensaje):
        usuarios[numero]["hora"] = mensaje

        # Verificar si la cita está disponible
        if cita_disponible(usuarios[numero]["fecha"], usuarios[numero]["hora"]):
            mensaje_respuesta.body(f"📅 Confirmando tu cita para el {usuarios[numero]['fecha']} a las {usuarios[numero]['hora']}. ¿Es correcto? (Sí/No)")
            usuarios[numero]["estado"] = "confirmar_cita"
        else:
            mensaje_respuesta.body("❌ Lo sentimos, ya hay una cita agendada en esa fecha y hora. Elige otra.")
            usuarios[numero]["estado"] = "preguntar_fecha"
    else:
        mensaje_respuesta.body("❌ Formato de hora inválido. Usa HH:MM en formato 24h.")
    return str(mensaje_respuesta)

def confirmar_cita(numero, mensaje, mensaje_respuesta):
    """Confirma y guarda la cita"""
    if mensaje in ["sí", "si"]:
        if guardar_cita(usuarios[numero]["nombre"], usuarios[numero]["telefono"], usuarios[numero]["fecha"], usuarios[numero]["hora"]):
            mensaje_respuesta.body(f"✅ Cita agendada para {usuarios[numero]['fecha']} a las {usuarios[numero]['hora']}. ¡Te esperamos!")
        else:
            mensaje_respuesta.body("❌ Ocurrió un error al guardar la cita. Intenta de nuevo.")
    else:
        mensaje_respuesta.body("❌ Cita cancelada. Empecemos de nuevo. ¿Cuál es tu nombre?")
        usuarios[numero]["estado"] = "preguntar_nombre"
    
    del usuarios[numero]  # Reiniciar conversación
    return str(mensaje_respuesta)

if __name__ == "__main__":
    app.run(port=5000, debug=True)


