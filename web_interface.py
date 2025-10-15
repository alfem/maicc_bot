"""
Interfaz web para consultar los diálogos del bot.
"""
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from functools import wraps

from conversation_manager import ConversationManager


# Cargar configuración
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

app = Flask(__name__)
app.secret_key = config['web'].get('admin_password', 'change_this_secret_key_123')

conversation_manager = ConversationManager(
    conversations_dir=config["storage"]["conversations_dir"],
    max_context_messages=config["storage"]["max_context_messages"]
)


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
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == config['web']['admin_password']:
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Contraseña incorrecta')

    return render_template('login.html')


@app.route('/logout')
def logout():
    """Cerrar sesión."""
    session.pop('logged_in', None)
    return redirect(url_for('login'))


@app.route('/')
@login_required
def index():
    """Página principal con lista de usuarios."""
    users = conversation_manager.get_all_users()
    return render_template('index.html', users=users)


@app.route('/user/<int:user_id>')
@login_required
def user_conversation(user_id):
    """Ver la conversación completa de un usuario."""
    # Obtener parámetros de fecha (opcional)
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')

    user_data = conversation_manager.get_full_history(user_id)

    # Filtrar por fecha si se especifica
    messages = user_data.get('messages', [])
    if start_date and end_date:
        messages = conversation_manager.get_messages_by_date(user_id, start_date, end_date)

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
    users = conversation_manager.get_all_users()
    return jsonify(users)


@app.route('/api/user/<int:user_id>/messages')
@login_required
def api_user_messages(user_id):
    """API para obtener mensajes de un usuario."""
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')

    if start_date and end_date:
        messages = conversation_manager.get_messages_by_date(user_id, start_date, end_date)
    else:
        user_data = conversation_manager.get_full_history(user_id)
        messages = user_data.get('messages', [])

    return jsonify(messages)


def main():
    """Inicia el servidor web."""
    host = config['web']['host']
    port = config['web']['port']

    print(f"Iniciando interfaz web en http://{host}:{port}")
    print(f"Usuario: admin")
    print(f"Contraseña: {config['web']['admin_password']}")

    app.run(host=host, port=port, debug=False)


if __name__ == '__main__':
    main()
