from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
import os

app = Flask(__name__, template_folder='.')
CORS(app)

API_KEY = os.environ.get('API_KEY')
LIGA_MUNDIAL_ID = "1"
TEMPORADA = "2026"

def obtener_conexion():
    DATABASE_URL = os.environ.get('DATABASE_URL')
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def inicializar_bd():
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS partidos (
                id INTEGER PRIMARY KEY,
                equipo_local TEXT,
                equipo_visitante TEXT,
                fecha_inicio TEXT,
                estado TEXT,
                goles_local INTEGER,
                goles_visitante INTEGER
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quinielas (
                id SERIAL PRIMARY KEY,
                partido_id INTEGER,
                nombre TEXT,
                marcador_local INTEGER,
                marcador_visitante INTEGER
            )
        ''')
        conexion.commit()
        conexion.close()
    except Exception as e:
        print(f"Error al inicializar la BD: {e}")

# ¡LA SOLUCIÓN! Ejecutamos la creación de tablas aquí afuera para que Render lo lea siempre
inicializar_bd()

@app.route('/')
def inicio():
    return render_template('index.html')

@app.route('/api/sincronizar', methods=['POST'])
def sincronizar_api():
    url = f"https://v3.football.api-sports.io/fixtures?league={LIGA_MUNDIAL_ID}&season={TEMPORADA}"
    headers = {'x-apisports-key': API_KEY}
    
    try:
        respuesta = requests.get(url, headers=headers)
        datos = respuesta.json()
        
        # Verificamos si la API nos rechazó la llave
       if 'errors' in datos and datos['errors']:
    error_real = str(datos['errors'])
    return jsonify({'error': f'La API de Fútbol dice: {error_real}'}), 400

        partidos_descargados = datos.get('response', [])
        if len(partidos_descargados) == 0:
            return jsonify({'mensaje': 'Conexión exitosa, pero la API devolvió 0 partidos para esta liga/temporada.'}), 200

        conexion = obtener_conexion()
        cursor = conexion.cursor()
        
        for partido in partidos_descargados:
            p_id = partido['fixture']['id']
            fecha = partido['fixture']['date']
            estado = partido['fixture']['status']['short']
            eq_local = partido['teams']['home']['name']
            eq_visita = partido['teams']['away']['name']
            goles_local = partido['goals']['home']
            goles_visita = partido['goals']['away']

            cursor.execute('''
                INSERT INTO partidos (id, equipo_local, equipo_visitante, fecha_inicio, estado, goles_local, goles_visitante)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(id) DO UPDATE SET
                estado=excluded.estado,
                goles_local=excluded.goles_local,
                goles_visitante=excluded.goles_visitante
            ''', (p_id, eq_local, eq_visita, fecha, estado, goles_local, goles_visita))
            
        conexion.commit()
        conexion.close()
        return jsonify({'mensaje': f'¡BD actualizada con {len(partidos_descargados)} partidos!'}), 200
        
    except Exception as e:
        return jsonify({'error': f"Hubo un problema: {str(e)}"}), 500

@app.route('/api/partidos', methods=['GET'])
def obtener_partidos():
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute('SELECT * FROM partidos ORDER BY fecha_inicio ASC')
        partidos_bd = cursor.fetchall()
        conexion.close()
        return jsonify(partidos_bd), 200
    except Exception as e:
        # Si falla, ahora enviamos un error claro en formato JSON
        return jsonify({'error': f"Error al leer BD: {str(e)}"}), 500

@app.route('/api/guardar', methods=['POST'])
def guardar_quiniela():
    datos = request.json
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute('''
            INSERT INTO quinielas (partido_id, nombre, marcador_local, marcador_visitante)
            VALUES (%s, %s, %s, %s)
        ''', (datos['partidoId'], datos['nombre'], datos['local'], datos['visitante']))
        conexion.commit()
        conexion.close()
        return jsonify({'mensaje': '¡Marcador guardado con éxito!'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    app.run(host='0.0.0.0', port=port)
