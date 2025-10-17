"""
Interfaz web para consultar los diálogos del bot.
"""
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from functools import wraps

from conversation_manager import ConversationManager
from logger_config import setup_logging, get_logger
from config_reloader import create_reload_signal


# Cargar configuración
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

# Configurar sistema de logging
loggers = setup_logging(config)
logger = loggers.get('web')
if not logger:
    logger = get_logger('web')

logger.info("="*60)
logger.info("Inicializando interfaz web")
logger.info("="*60)

app = Flask(__name__)
app.secret_key = config['web'].get('admin_password', 'change_this_secret_key_123')

# Desactivar logging de Flask por defecto para usar nuestro logger
import logging as flask_logging
flask_log = flask_logging.getLogger('werkzeug')
flask_log.setLevel(flask_logging.ERROR)  # Solo errores críticos de Flask

conversation_manager = ConversationManager(
    conversations_dir=config["storage"]["conversations_dir"],
    max_context_messages=config["storage"]["max_context_messages"]
)

logger.info(f"Directorio de conversaciones: {config['storage']['conversations_dir']}")


def login_required(f):
    """Decorador para requerir autenticación."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Página de login."""
    client_ip = request.remote_addr

    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == config['web']['admin_password']:
            session['logged_in'] = True
            logger.info(f"Inicio de sesión exitoso desde {client_ip}")
            return redirect(url_for('index'))
        else:
            logger.warning(f"Intento de inicio de sesión fallido desde {client_ip}")
            return render_template('login.html', error='Contraseña incorrecta')

    logger.debug(f"Acceso a página de login desde {client_ip}")
    return render_template('login.html')


@app.route('/logout')
def logout():
    """Cerrar sesión."""
    client_ip = request.remote_addr
    session.pop('logged_in', None)
    logger.info(f"Cierre de sesión desde {client_ip}")
    return redirect(url_for('login'))


@app.route('/')
@login_required
def index():
    """Página principal con lista de usuarios."""
    client_ip = request.remote_addr
    logger.debug(f"Acceso a página principal desde {client_ip}")
    users = conversation_manager.get_all_users()
    logger.debug(f"Mostrando {len(users)} usuarios")
    return render_template('index.html', users=users)


@app.route('/user/<int:user_id>')
@login_required
def user_conversation(user_id):
    """Ver la conversación completa de un usuario."""
    client_ip = request.remote_addr
    logger.info(f"Acceso a conversación del usuario {user_id} desde {client_ip}")

    user_data = conversation_manager.get_full_history(user_id)

    # Obtener parámetros de fecha
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')

    # Si no se especifican fechas, usar por defecto el día anterior y hoy
    if not start_date and not end_date:
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        start_date = yesterday.strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
        logger.debug(f"Usando filtro por defecto: {start_date} a {end_date}")

    # Filtrar por fecha
    messages = user_data.get('messages', [])
    if start_date and end_date:
        logger.debug(f"Filtrando mensajes por fecha: {start_date} a {end_date}")
        messages = conversation_manager.get_messages_by_date(user_id, start_date, end_date)

    logger.debug(f"Mostrando {len(messages)} mensajes del usuario {user_id}")

    return render_template(
        'conversation.html',
        user_data=user_data,
        messages=messages,
        start_date=start_date,
        end_date=end_date
    )


@app.route('/api/users')
@login_required
def api_users():
    """API para obtener lista de usuarios."""
    client_ip = request.remote_addr
    logger.debug(f"API /api/users llamada desde {client_ip}")
    users = conversation_manager.get_all_users()
    return jsonify(users)


@app.route('/api/user/<int:user_id>/messages')
@login_required
def api_user_messages(user_id):
    """API para obtener mensajes de un usuario."""
    client_ip = request.remote_addr
    logger.debug(f"API /api/user/{user_id}/messages llamada desde {client_ip}")

    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')

    if start_date and end_date:
        messages = conversation_manager.get_messages_by_date(user_id, start_date, end_date)
    else:
        user_data = conversation_manager.get_full_history(user_id)
        messages = user_data.get('messages', [])

    return jsonify(messages)


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """Página de configuración del bot."""
    client_ip = request.remote_addr

    if request.method == 'POST':
        logger.info(f"Guardando cambios de configuración desde {client_ip}")

        try:
            # Cargar configuración actual
            with open('config.json', 'r', encoding='utf-8') as f:
                current_config = json.load(f)

            # Actualizar valores desde el formulario
            # LLM
            current_config['llm']['system_prompt'] = request.form.get('system_prompt', '').strip()
            current_config['llm']['temperature'] = float(request.form.get('temperature', 0.7))
            current_config['llm']['max_tokens'] = int(request.form.get('max_tokens', 1024))

            # Proactive messaging
            current_config['proactive']['inactivity_minutes'] = int(request.form.get('inactivity_minutes', 60))

            # Quiet hours
            quiet_hours_enabled = request.form.get('quiet_hours_enabled') == 'on'
            current_config['proactive']['quiet_hours']['enabled'] = quiet_hours_enabled
            current_config['proactive']['quiet_hours']['start'] = request.form.get('quiet_hours_start', '22:00')
            current_config['proactive']['quiet_hours']['end'] = request.form.get('quiet_hours_end', '09:00')

            # RSS Feeds (uno por línea)
            rss_feeds_text = request.form.get('rss_feeds', '').strip()
            if rss_feeds_text:
                rss_feeds = [feed.strip() for feed in rss_feeds_text.split('\n') if feed.strip()]
                current_config['news']['rss_feeds'] = rss_feeds
            else:
                current_config['news']['rss_feeds'] = []

            # Admin password
            new_password = request.form.get('admin_password', '').strip()
            if new_password:
                current_config['web']['admin_password'] = new_password
                # Actualizar secret_key de Flask también
                app.secret_key = new_password
                logger.info("Contraseña de administrador actualizada")

            # Guardar configuración
            with open('config.json', 'w', encoding='utf-8') as f:
                json.dump(current_config, f, indent=2, ensure_ascii=False)

            logger.info("Configuración guardada exitosamente")

            # Actualizar la variable global config
            global config
            config = current_config

            # Crear señal de recarga para el bot
            create_reload_signal(
                reason="Configuración actualizada desde interfaz web",
                source=f"web_interface ({client_ip})"
            )

            return render_template('settings.html', config=config, success=True, reload_pending=True)

        except Exception as e:
            logger.error(f"Error al guardar configuración: {e}", exc_info=True)
            return render_template('settings.html', config=config, error=str(e))

    # GET - mostrar formulario
    logger.debug(f"Acceso a configuración desde {client_ip}")
    return render_template('settings.html', config=config)


@app.route('/reload', methods=['POST'])
@login_required
def reload_config():
    """Solicita recarga inmediata de la configuración del bot."""
    client_ip = request.remote_addr
    logger.info(f"Recarga manual de configuración solicitada desde {client_ip}")

    try:
        success = create_reload_signal(
            reason="Recarga manual solicitada desde interfaz web",
            source=f"web_interface ({client_ip})"
        )

        if success:
            return jsonify({
                "success": True,
                "message": "Señal de recarga enviada. El bot aplicará los cambios en 30 segundos o menos."
            })
        else:
            return jsonify({
                "success": False,
                "message": "Error al crear señal de recarga"
            }), 500

    except Exception as e:
        logger.error(f"Error al solicitar recarga: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "message": f"Error: {str(e)}"
        }), 500


def main():
    """Inicia el servidor web."""
    host = config['web']['host']
    port = config['web']['port']

    logger.info("="*60)
    logger.info(f"Iniciando servidor web en http://{host}:{port}")
    logger.info(f"Usuario: admin")
    logger.info(f"Contraseña: {config['web']['admin_password']}")
    logger.info("="*60)

    try:
        app.run(host=host, port=port, debug=False)
    except Exception as e:
        logger.error(f"Error al iniciar servidor web: {e}", exc_info=True)
        raise


if __name__ == '__main__':
    main()
