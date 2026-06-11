from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
import os

app = Flask(__name__, template_folder='.')
# Escudo activado: Solo tu página web oficial tiene permiso de usar la API
CORS(app, resources={r"/api/*": {"origins": "https://app-quiniela.onrender.com"}})

# La llave sigue segura en Render
API_KEY = os.environ.get('API_KEY')

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

inicializar_bd()

@app.route('/')
def inicio():
    return render_template('index.html')

# --- CONEXIÓN NUEVA A FOOTBALL-DATA.ORG ---
@app.route('/api/sincronizar', methods=['POST'])
def sincronizar_api():
    # 'WC' es el código universal de esta API para la World Cup
    url = "https://api.football-data.org/v4/competitions/WC/matches"
    headers = {'X-Auth-Token': API_KEY}
    
    try:
        respuesta = requests.get(url, headers=headers)
        datos = respuesta.json()
        
        # Validamos errores de esta nueva API
        if 'errorCode' in datos or 'error' in datos:
            error_msg = datos.get('message', 'Error desconocido')
            return jsonify({'error': f"Football-Data dice: {error_msg}"}), 400

        partidos_descargados = datos.get('matches', [])
        
        if len(partidos_descargados) == 0:
            return jsonify({'mensaje': 'Conexión exitosa, pero aún no hay partidos listos.'}), 200

        conexion = obtener_conexion()
        cursor = conexion.cursor()
        
        for partido in partidos_descargados:
            p_id = partido['id']
            fecha = partido['utcDate']
            
            # Traducción de estados de partido
            estado_crudo = partido['status']
            if estado_crudo == 'FINISHED':
                estado = 'FT'
            elif estado_crudo in ['SCHEDULED', 'TIMED']:
                estado = 'NS'
            else:
                estado = estado_crudo
            
            # Nombres de equipos (si aún no se deciden, ponemos "Por Definir")
            eq_local = partido['homeTeam']['name'] if partido['homeTeam'].get('name') else 'Por Definir'
            eq_visita = partido['awayTeam']['name'] if partido['awayTeam'].get('name') else 'Por Definir'
            
            # Goles
            score_ft = partido.get('score', {}).get('fullTime', {}) or {}
            goles_local = score_ft.get('home')
            goles_visita = score_ft.get('away')

            cursor.execute('''
                INSERT INTO partidos (id, equipo_local, equipo_visitante, fecha_inicio, estado, goles_local, goles_visitante)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(id) DO UPDATE SET
                equipo_local=excluded.equipo_local,
                equipo_visitante=excluded.equipo_visitante,
                estado=excluded.estado,
                fecha_inicio=excluded.fecha_inicio,
                goles_local=excluded.goles_local,
                goles_visitante=excluded.goles_visitante
            ''', (p_id, eq_local, eq_visita, fecha, estado, goles_local, goles_visita))
            
        conexion.commit()
        conexion.close()
        return jsonify({'mensaje': f'¡BD actualizada con {len(partidos_descargados)} partidos de Football-Data!'}), 200
        
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

@app.route('/api/quinielas_todas', methods=['GET'])
def obtener_todas_quinielas():
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute('SELECT * FROM quinielas')
        todas = cursor.fetchall()
        conexion.close()
        return jsonify(todas), 200
    except Exception as e:
        return jsonify([]), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    app.run(host='0.0.0.0', port=port)
