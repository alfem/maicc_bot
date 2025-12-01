"""
Interfaz web para consultar los diálogos del bot.
"""
import json
import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from functools import wraps

from conversation_manager import ConversationManager
from memory_manager import MemoryManager
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

# Configurar GOOGLE_API_KEY como variable de entorno para mem0
# mem0 necesita esta variable de entorno para Gemini
if 'GOOGLE_API_KEY' not in os.environ:
    os.environ['GOOGLE_API_KEY'] = config["llm"]["api_key"]
    logger.info("GOOGLE_API_KEY configurada desde config.json")

# Inicializar gestor de memorias mem0 si está habilitado
mem0_config = config.get("mem0", {})
mem0_enabled = mem0_config.get("enabled", False)
memory_manager = None

if mem0_enabled:
    try:
        memory_manager = MemoryManager(
            config={
                "history_db_path": mem0_config.get("history_db_path", "/tmp/mem0_history.db"),
                "vector_store": mem0_config.get("vector_store", {}),
                "llm": mem0_config.get("llm", {}),
                "embedder": mem0_config.get("embedder", {})
            },
            enabled=True
        )
        logger.info("Gestor de memorias mem0 inicializado para interfaz web")
    except Exception as e:
        logger.error(f"Error al inicializar MemoryManager en web interface: {e}")
        memory_manager = None
else:
    logger.info("Gestor de memorias mem0 deshabilitado")


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

    # Obtener memorias de mem0 si está habilitado
    memories = []
    memory_stats = {"total": 0, "enabled": False}
    if mem0_enabled:
        try:
            # Crear una nueva instancia de MemoryManager para forzar recarga desde disco
            # Esto asegura que leemos los datos más recientes guardados por el bot
            temp_memory_manager = MemoryManager(
                config={
                    "history_db_path": mem0_config.get("history_db_path", "/tmp/mem0_history.db"),
                    "vector_store": mem0_config.get("vector_store", {}),
                    "llm": mem0_config.get("llm", {}),
                    "embedder": mem0_config.get("embedder", {})
                },
                enabled=True
            )
            memories = temp_memory_manager.get_all_memories(user_id)
            memory_stats = {"total": len(memories), "enabled": True}
            logger.debug(f"Recuperadas {len(memories)} memorias de mem0 para usuario {user_id}")
        except Exception as e:
            logger.error(f"Error al recuperar memorias para usuario {user_id}: {e}")

    return render_template(
        'conversation.html',
        user_data=user_data,
        messages=messages,
        start_date=start_date,
        end_date=end_date,
        memories=memories,
        memory_stats=memory_stats
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


@app.route('/api/user/<int:user_id>/memories')
@login_required
def api_user_memories(user_id):
    """API para obtener memorias de mem0 de un usuario."""
    client_ip = request.remote_addr
    logger.debug(f"API /api/user/{user_id}/memories llamada desde {client_ip}")

    if not mem0_enabled:
        return jsonify({"error": "mem0 no está habilitado", "memories": [], "count": 0})

    try:
        # Crear una nueva instancia para forzar recarga desde disco
        temp_memory_manager = MemoryManager(
            config={
                "history_db_path": mem0_config.get("history_db_path", "/tmp/mem0_history.db"),
                "vector_store": mem0_config.get("vector_store", {}),
                "llm": mem0_config.get("llm", {}),
                "embedder": mem0_config.get("embedder", {})
            },
            enabled=True
        )
        memories = temp_memory_manager.get_all_memories(user_id)
        logger.debug(f"Recuperadas {len(memories)} memorias para usuario {user_id}")
        return jsonify({"memories": memories, "count": len(memories)})
    except Exception as e:
        logger.error(f"Error al obtener memorias para usuario {user_id}: {e}", exc_info=True)
        return jsonify({"error": str(e), "memories": [], "count": 0}), 500


@app.route('/api/memory/<memory_id>', methods=['DELETE'])
@login_required
def api_delete_memory(memory_id):
    """API para borrar una memoria específica."""
    client_ip = request.remote_addr
    logger.info(f"API DELETE /api/memory/{memory_id} llamada desde {client_ip}")

    if not memory_manager or not memory_manager.enabled:
        return jsonify({"success": False, "error": "mem0 no está habilitado"}), 400

    try:
        success = memory_manager.delete_memory(memory_id)
        if success:
            logger.info(f"Memoria {memory_id} borrada exitosamente desde {client_ip}")
            return jsonify({"success": True, "message": "Memoria borrada exitosamente"})
        else:
            return jsonify({"success": False, "error": "No se pudo borrar la memoria"}), 500
    except Exception as e:
        logger.error(f"Error al borrar memoria {memory_id}: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/user/<int:user_id>/memories/delete', methods=['POST'])
@login_required
def api_delete_multiple_memories(user_id):
    """API para borrar múltiples memorias."""
    client_ip = request.remote_addr
    logger.info(f"API POST /api/user/{user_id}/memories/delete llamada desde {client_ip}")

    if not memory_manager or not memory_manager.enabled:
        return jsonify({"success": False, "error": "mem0 no está habilitado"}), 400

    try:
        data = request.get_json()
        memory_ids = data.get('memory_ids', [])

        if not memory_ids:
            return jsonify({"success": False, "error": "No se proporcionaron IDs de memorias"}), 400

        deleted_count = 0
        failed_count = 0

        for memory_id in memory_ids:
            success = memory_manager.delete_memory(memory_id)
            if success:
                deleted_count += 1
            else:
                failed_count += 1

        logger.info(f"{deleted_count} memorias borradas, {failed_count} fallaron para usuario {user_id} desde {client_ip}")

        return jsonify({
            "success": True,
            "deleted": deleted_count,
            "failed": failed_count,
            "message": f"{deleted_count} memorias borradas exitosamente"
        })
    except Exception as e:
        logger.error(f"Error al borrar memorias para usuario {user_id}: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/user/<int:user_id>/messages/reprocess', methods=['POST'])
@login_required
def api_reprocess_messages(user_id):
    """API para reprocesar mensajes seleccionados en mem0."""
    client_ip = request.remote_addr
    logger.info(f"API POST /api/user/{user_id}/messages/reprocess llamada desde {client_ip}")

    if not mem0_enabled:
        return jsonify({"success": False, "error": "mem0 no está habilitado"}), 400

    try:
        data = request.get_json()
        message_indices = data.get('message_indices', [])

        if not message_indices:
            return jsonify({"success": False, "error": "No se proporcionaron índices de mensajes"}), 400

        # Obtener la conversación completa
        user_data = conversation_manager.get_full_history(user_id)
        all_messages = user_data.get('messages', [])

        # Filtrar los mensajes seleccionados
        selected_messages = []
        for idx in sorted(message_indices):
            if 0 <= idx < len(all_messages):
                msg = all_messages[idx]
                selected_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })

        if not selected_messages:
            return jsonify({"success": False, "error": "No se encontraron mensajes válidos"}), 400

        # Crear instancia temporal de MemoryManager para reprocesar
        temp_memory_manager = MemoryManager(
            config={
                "history_db_path": mem0_config.get("history_db_path", "/tmp/mem0_history.db"),
                "vector_store": mem0_config.get("vector_store", {}),
                "llm": mem0_config.get("llm", {}),
                "embedder": mem0_config.get("embedder", {})
            },
            enabled=True
        )

        # Procesar los mensajes en mem0
        success = temp_memory_manager.add_conversation(user_id, selected_messages)

        if success:
            logger.info(f"{len(selected_messages)} mensajes reprocesados exitosamente para usuario {user_id} desde {client_ip}")
            return jsonify({
                "success": True,
                "message": f"{len(selected_messages)} mensajes reprocesados exitosamente",
                "processed": len(selected_messages)
            })
        else:
            return jsonify({"success": False, "error": "Error al reprocesar mensajes"}), 500

    except Exception as e:
        logger.error(f"Error al reprocesar mensajes para usuario {user_id}: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


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
            current_config['llm']['model'] = request.form.get('model', 'gemini-2.5-flash').strip()
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

            # TTS Configuration
            if 'tts' not in current_config:
                current_config['tts'] = {}

            tts_enabled = request.form.get('tts_enabled') == 'on'
            current_config['tts']['enabled'] = tts_enabled

            # Provider selection
            tts_provider = request.form.get('tts_provider', 'gemini').strip()
            current_config['tts']['provider'] = tts_provider

            # Common settings
            current_config['tts']['frequency_percent'] = int(request.form.get('tts_frequency', 30))
            current_config['tts']['audio_dir'] = request.form.get('tts_audio_dir', './audio_outputs').strip()

            # Gemini TTS settings
            if 'gemini' not in current_config['tts']:
                current_config['tts']['gemini'] = {}

            current_config['tts']['gemini']['api_key'] = request.form.get('gemini_api_key', '').strip()
            current_config['tts']['gemini']['model'] = request.form.get('gemini_model', 'gemini-2.5-flash-preview-tts').strip()
            current_config['tts']['gemini']['speaker'] = request.form.get('gemini_speaker', 'Leda').strip()
            current_config['tts']['gemini']['preamble'] = request.form.get('gemini_preamble', '').strip()
            current_config['tts']['gemini']['temperature'] = float(request.form.get('gemini_temperature', 0.5))

            # Eleven Labs TTS settings
            if 'elevenlabs' not in current_config['tts']:
                current_config['tts']['elevenlabs'] = {}

            current_config['tts']['elevenlabs']['api_key'] = request.form.get('elevenlabs_api_key', '').strip()
            current_config['tts']['elevenlabs']['voice_id'] = request.form.get('elevenlabs_voice_id', '21m00Tcm4TlvDq8ikWAM').strip()
            current_config['tts']['elevenlabs']['model_id'] = request.form.get('elevenlabs_model_id', 'eleven_multilingual_v2').strip()
            current_config['tts']['elevenlabs']['stability'] = float(request.form.get('elevenlabs_stability', 0.5))
            current_config['tts']['elevenlabs']['similarity_boost'] = float(request.form.get('elevenlabs_similarity_boost', 0.75))
            current_config['tts']['elevenlabs']['style'] = float(request.form.get('elevenlabs_style', 0.0))
            current_config['tts']['elevenlabs']['use_speaker_boost'] = request.form.get('elevenlabs_speaker_boost') == 'on'

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

    # Asegurar que existe la configuración TTS con valores por defecto y estructura correcta
    if 'tts' not in config:
        config['tts'] = {}

    # Asegurar valores por defecto comunes
    if 'enabled' not in config['tts']:
        config['tts']['enabled'] = False
    if 'provider' not in config['tts']:
        config['tts']['provider'] = 'gemini'
    if 'frequency_percent' not in config['tts']:
        config['tts']['frequency_percent'] = 30
    if 'audio_dir' not in config['tts']:
        config['tts']['audio_dir'] = './audio_outputs'

    # Asegurar configuración de Gemini
    if 'gemini' not in config['tts']:
        config['tts']['gemini'] = {}
    gemini_defaults = {
        'api_key': config.get('llm', {}).get('api_key', ''),
        'model': 'gemini-2.5-flash-preview-tts',
        'speaker': 'Leda',
        'preamble': 'Habla de forma natural y expresiva: ',
        'temperature': 0.5
    }
    for key, default_value in gemini_defaults.items():
        if key not in config['tts']['gemini']:
            config['tts']['gemini'][key] = default_value

    # Asegurar configuración de Eleven Labs
    if 'elevenlabs' not in config['tts']:
        config['tts']['elevenlabs'] = {}
    elevenlabs_defaults = {
        'api_key': '',
        'voice_id': '21m00Tcm4TlvDq8ikWAM',
        'model_id': 'eleven_multilingual_v2',
        'stability': 0.5,
        'similarity_boost': 0.75,
        'style': 0.0,
        'use_speaker_boost': True
    }
    for key, default_value in elevenlabs_defaults.items():
        if key not in config['tts']['elevenlabs']:
            config['tts']['elevenlabs'][key] = default_value

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
