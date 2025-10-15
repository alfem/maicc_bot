"""
Bot de Telegram que actúa como compañero conversacional.
"""
import json
import logging
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

from conversation_manager import ConversationManager
from llm_client import LLMClient


# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class CompanionBot:
    """Bot de Telegram que funciona como compañero conversacional."""

    def __init__(self, config_file: str = "config.json"):
        """
        Inicializa el bot con la configuración del archivo JSON.

        Args:
            config_file: Ruta al archivo de configuración
        """
        # Cargar configuración
        with open(config_file, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        # Inicializar componentes
        self.conversation_manager = ConversationManager(
            conversations_dir=self.config["storage"]["conversations_dir"],
            max_context_messages=self.config["storage"]["max_context_messages"]
        )

        self.llm_client = LLMClient(
            api_key=self.config["llm"]["api_key"],
            model=self.config["llm"]["model"],
            max_tokens=self.config["llm"]["max_tokens"],
            temperature=self.config["llm"]["temperature"],
            system_prompt=self.config["llm"]["system_prompt"],
            api_url=self.config["llm"]["api_url"]
        )

        # Crear aplicación de Telegram
        self.updater = Updater(
            token=self.config["telegram"]["bot_token"],
            use_context=True
        )
        self.dispatcher = self.updater.dispatcher

        # Diccionario para rastrear la última actividad de cada usuario
        self.user_last_activity = {}

        # Registrar manejadores
        self._register_handlers()

    def _register_handlers(self):
        """Registra los manejadores de comandos y mensajes."""
        self.dispatcher.add_handler(CommandHandler("start", self.start_command))
        self.dispatcher.add_handler(CommandHandler("help", self.help_command))
        self.dispatcher.add_handler(CommandHandler("reset", self.reset_command))
        self.dispatcher.add_handler(MessageHandler(
            Filters.text & ~Filters.command,
            self.handle_message
        ))

    def start_command(self, update: Update, context: CallbackContext):
        """Maneja el comando /start."""
        user = update.effective_user
        welcome_message = (
            f"¡Hola {user.first_name}! 👋\n\n"
            "Soy tu compañero de conversación. Estoy aquí para charlar contigo, "
            "escuchar tus historias y acompañarte. Puedes hablarme de lo que quieras: "
            "tus recuerdos, tu día a día, tus intereses... ¡Lo que te apetezca!\n\n"
            "Escribe cualquier mensaje para empezar a conversar.\n\n"
            "Comandos disponibles:\n"
            "/help - Mostrar esta ayuda\n"
            "/reset - Empezar una nueva conversación"
        )

        update.message.reply_text(welcome_message)

        # Actualizar última actividad
        self.user_last_activity[user.id] = datetime.now()

        logger.info(f"Usuario {user.id} ({user.username}) inició el bot")

    def help_command(self, update: Update, context: CallbackContext):
        """Maneja el comando /help."""
        help_message = (
            "🤝 *Cómo usar el bot*\n\n"
            "Simplemente escribe lo que quieras contarme y yo te responderé. "
            "Puedo recordar nuestra conversación, así que puedes hacer referencia "
            "a cosas que me hayas contado antes.\n\n"
            "*Comandos disponibles:*\n"
            "/start - Mensaje de bienvenida\n"
            "/help - Mostrar esta ayuda\n"
            "/reset - Borrar el historial y empezar de nuevo\n\n"
            "Estoy aquí para acompañarte y conversar. ¡No dudes en escribirme!"
        )

        update.message.reply_text(help_message, parse_mode='Markdown')

    def reset_command(self, update: Update, context: CallbackContext):
        """Maneja el comando /reset para borrar el historial."""
        user_id = update.effective_user.id

        self.conversation_manager.clear_user_history(user_id)

        reset_message = (
            "✨ He borrado nuestro historial de conversación.\n\n"
            "Podemos empezar de nuevo. ¿De qué te gustaría hablar?"
        )

        update.message.reply_text(reset_message)
        logger.info(f"Usuario {user_id} reinició su conversación")

    def handle_message(self, update: Update, context: CallbackContext):
        """Maneja los mensajes de texto del usuario."""
        user = update.effective_user
        user_message = update.message.text

        logger.info(f"Mensaje de {user.id} ({user.username}): {user_message}")

        # Actualizar última actividad
        self.user_last_activity[user.id] = datetime.now()

        # Guardar mensaje del usuario
        self.conversation_manager.add_message(
            user_id=user.id,
            role="user",
            content=user_message,
            username=user.username or "",
            first_name=user.first_name or ""
        )

        # Obtener contexto de la conversación
        context_messages = self.conversation_manager.get_context(user.id)

        # Enviar "escribiendo..." mientras se genera la respuesta
        context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        # Obtener respuesta del LLM
        assistant_response = self.llm_client.get_response(context_messages)

        # Guardar respuesta del asistente
        self.conversation_manager.add_message(
            user_id=user.id,
            role="assistant",
            content=assistant_response
        )

        # Enviar respuesta al usuario
        update.message.reply_text(assistant_response)

        logger.info(f"Respuesta enviada a {user.id}")

    def send_proactive_message(self, context: CallbackContext):
        """
        Envía mensajes proactivos a usuarios que llevan tiempo sin escribir.
        """
        # Verificar horario de "no molestar"
        quiet_hours = self.config.get("proactive", {}).get("quiet_hours", {})
        if quiet_hours.get("enabled", False):
            current_time = datetime.now().time()
            start_time = datetime.strptime(quiet_hours.get("start", "22:00"), "%H:%M").time()
            end_time = datetime.strptime(quiet_hours.get("end", "09:00"), "%H:%M").time()

            # Verificar si estamos en horario de no molestar
            if start_time < end_time:
                # Rango normal (ej: 22:00 a 23:59)
                in_quiet_hours = start_time <= current_time <= end_time
            else:
                # Rango que cruza medianoche (ej: 22:00 a 09:00)
                in_quiet_hours = current_time >= start_time or current_time <= end_time

            if in_quiet_hours:
                logger.info(f"Horario de no molestar activo ({quiet_hours.get('start')} - {quiet_hours.get('end')}). No se envían mensajes proactivos.")
                return

        # Configuración de tiempo de inactividad (en minutos)
        inactivity_threshold = self.config.get("proactive", {}).get("inactivity_minutes", 60)

        now = datetime.now()
        users_to_check = list(self.user_last_activity.items())

        for user_id, last_activity in users_to_check:
            # Calcular tiempo de inactividad
            time_inactive = (now - last_activity).total_seconds() / 60

            if time_inactive >= inactivity_threshold:
                try:
                    # Obtener contexto de la conversación
                    context_messages = self.conversation_manager.get_context(user_id)

                    # Crear un prompt especial para mensaje proactivo
                    proactive_prompt = {
                        "role": "user",
                        "content": "El usuario lleva un rato sin escribir. Inicia una conversación de forma natural y amigable. Puedes preguntar cómo está, proponer un tema interesante para conversar, compartir algo curioso, o simplemente saludar de manera cálida. Sé creativa y espontánea."
                    }

                    # Enviar acción de escritura
                    context.bot.send_chat_action(chat_id=user_id, action="typing")

                    # Generar mensaje proactivo
                    proactive_messages = context_messages + [proactive_prompt]
                    assistant_response = self.llm_client.get_response(proactive_messages)

                    # Guardar mensaje del asistente
                    self.conversation_manager.add_message(
                        user_id=user_id,
                        role="assistant",
                        content=assistant_response
                    )

                    # Enviar mensaje al usuario
                    context.bot.send_message(chat_id=user_id, text=assistant_response)

                    # Actualizar última actividad (para no enviar otro mensaje inmediatamente)
                    self.user_last_activity[user_id] = datetime.now()

                    logger.info(f"Mensaje proactivo enviado a {user_id}")

                except Exception as e:
                    logger.error(f"Error al enviar mensaje proactivo a {user_id}: {e}")

    def run(self):
        """Inicia el bot."""
        logger.info("Iniciando bot de Telegram...")
        logger.info(f"Modelo LLM: {self.config['llm']['model']}")
        logger.info(f"Directorio de conversaciones: {self.config['storage']['conversations_dir']}")

        # Configurar job para mensajes proactivos
        proactive_enabled = self.config.get("proactive", {}).get("enabled", True)
        check_interval = self.config.get("proactive", {}).get("check_interval_minutes", 15)

        if proactive_enabled:
            job_queue = self.updater.job_queue
            job_queue.run_repeating(
                self.send_proactive_message,
                interval=check_interval * 60,  # Convertir a segundos
                first=60  # Primer chequeo después de 1 minuto
            )
            logger.info(f"Mensajes proactivos habilitados (cada {check_interval} minutos)")

        # Iniciar el bot
        self.updater.start_polling()
        self.updater.idle()


def main():
    """Función principal para ejecutar el bot."""
    try:
        bot = CompanionBot()
        bot.run()
    except FileNotFoundError:
        logger.error("No se encontró el archivo config.json. Por favor, créalo con la configuración necesaria.")
    except KeyError as e:
        logger.error(f"Falta una clave de configuración: {e}")
    except Exception as e:
        logger.error(f"Error al iniciar el bot: {e}")


if __name__ == "__main__":
    main()
