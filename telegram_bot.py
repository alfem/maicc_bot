"""
Bot de Telegram que actúa como compañero conversacional.
"""
import json
import logging
import random
import asyncio
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

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
        self.app = Application.builder().token(
            self.config["telegram"]["bot_token"]
        ).build()

        # Diccionario para rastrear la última actividad de cada usuario
        self.user_last_activity = {}

        # Registrar manejadores
        self._register_handlers()

    def _calculate_typing_delay(self, text: str) -> float:
        """
        Calcula un retraso aleatorio basado en la longitud del texto.
        Simula el tiempo que tomaría escribir el mensaje.

        Args:
            text: Texto de la respuesta

        Returns:
            Tiempo de retraso en segundos
        """
        # Palabras por minuto promedio (ajustable)
        wpm = random.uniform(40, 60)  # Velocidad de escritura aleatoria entre 40-60 palabras/min

        # Contar palabras en el texto
        word_count = len(text.split())

        # Calcular tiempo base (en segundos)
        base_delay = (word_count / wpm) * 60

        # Agregar un pequeño retraso aleatorio adicional (0.5-2 segundos)
        random_delay = random.uniform(0.5, 2.0)

        # Retraso mínimo de 1 segundo, máximo de 20 segundos
        total_delay = min(max(base_delay + random_delay, 1.0), 20.0)

        return total_delay

    def _register_handlers(self):
        """Registra los manejadores de comandos y mensajes."""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("reset", self.reset_command))
        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.handle_message
        ))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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

        await update.message.reply_text(welcome_message)

        # Actualizar última actividad
        self.user_last_activity[user.id] = datetime.now()

        logger.info(f"Usuario {user.id} ({user.username}) inició el bot")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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

        await update.message.reply_text(help_message, parse_mode='Markdown')

    async def reset_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja el comando /reset para borrar el historial."""
        user_id = update.effective_user.id

        self.conversation_manager.clear_user_history(user_id)

        reset_message = (
            "✨ He borrado nuestro historial de conversación.\n\n"
            "Podemos empezar de nuevo. ¿De qué te gustaría hablar?"
        )

        await update.message.reply_text(reset_message)
        logger.info(f"Usuario {user_id} reinició su conversación")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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

        # Obtener respuesta del LLM
        assistant_response = self.llm_client.get_response(context_messages)

        # Calcular retraso basado en la longitud de la respuesta
        typing_delay = self._calculate_typing_delay(assistant_response)
        logger.info(f"Esperando {typing_delay:.2f} segundos antes de responder a {user.id}")

        # Mostrar indicador de "escribiendo..." durante el retraso
        # El indicador dura 5 segundos, así que lo renovamos si es necesario
        start_time = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start_time) < typing_delay:
            await update.message.chat.send_action(action="typing")
            # Esperar 4 segundos o el tiempo restante, lo que sea menor
            remaining_time = typing_delay - (asyncio.get_event_loop().time() - start_time)
            await asyncio.sleep(min(4, remaining_time))

        # Guardar respuesta del asistente
        self.conversation_manager.add_message(
            user_id=user.id,
            role="assistant",
            content=assistant_response
        )

        # Enviar respuesta al usuario
        await update.message.reply_text(assistant_response)

        logger.info(f"Respuesta enviada a {user.id}")

    async def send_proactive_message(self, context: ContextTypes.DEFAULT_TYPE):
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

                    # Generar mensaje proactivo
                    proactive_messages = context_messages + [proactive_prompt]
                    assistant_response = self.llm_client.get_response(proactive_messages)

                    # Calcular retraso basado en la longitud de la respuesta
                    typing_delay = self._calculate_typing_delay(assistant_response)
                    logger.info(f"Esperando {typing_delay:.2f} segundos antes de enviar mensaje proactivo a {user_id}")

                    # Mostrar indicador de "escribiendo..." durante el retraso
                    start_time = asyncio.get_event_loop().time()
                    while (asyncio.get_event_loop().time() - start_time) < typing_delay:
                        await context.bot.send_chat_action(chat_id=user_id, action="typing")
                        # Esperar 4 segundos o el tiempo restante, lo que sea menor
                        remaining_time = typing_delay - (asyncio.get_event_loop().time() - start_time)
                        await asyncio.sleep(min(4, remaining_time))

                    # Guardar mensaje del asistente
                    self.conversation_manager.add_message(
                        user_id=user_id,
                        role="assistant",
                        content=assistant_response
                    )

                    # Enviar mensaje al usuario
                    await context.bot.send_message(chat_id=user_id, text=assistant_response)

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
            job_queue = self.app.job_queue
            job_queue.run_repeating(
                self.send_proactive_message,
                interval=check_interval * 60,  # Convertir a segundos
                first=60  # Primer chequeo después de 1 minuto
            )
            logger.info(f"Mensajes proactivos habilitados (cada {check_interval} minutos)")

        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


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
