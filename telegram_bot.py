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
from news_manager import NewsManager
from mood_manager import MoodManager
from tts_client import TTSClient
from logger_config import setup_logging, get_logger
from config_reloader import ConfigReloader

# Logger específico para Telegram (se inicializará después de cargar config)
logger = None


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

        # Configurar sistema de logging
        global logger
        loggers = setup_logging(self.config)
        logger = loggers.get('telegram')
        if not logger:
            # Fallback si no se configuró el logger de telegram
            logger = get_logger('telegram')

        logger.info("="*60)
        logger.info("Inicializando CompanionBot")
        logger.info("="*60)

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

        # Inicializar gestor de noticias si está configurado
        rss_feeds = self.config.get("news", {}).get("rss_feeds", [])
        if rss_feeds:
            storage_file = self.config.get("news", {}).get("cache_file", "./news_cache.json")
            self.news_manager = NewsManager(rss_feeds, storage_file)
            logger.info(f"Gestor de noticias inicializado con {len(rss_feeds)} feeds RSS")
        else:
            self.news_manager = None
            logger.info("Gestor de noticias no configurado")

        # Inicializar gestor de estado de ánimo
        mood_config = self.config.get("mood", {})
        weather_api_key = mood_config.get("weather_api_key")
        location = mood_config.get("location", "Madrid,ES")
        self.mood_manager = MoodManager(weather_api_key, location)
        logger.info(f"Gestor de estado de ánimo inicializado (ubicación: {location})")

        # Inicializar cliente TTS si está habilitado
        tts_config = self.config.get("tts", {})
        if tts_config.get("enabled", False):
            self.tts_client = TTSClient(
                api_key=self.config["llm"]["api_key"],
                model=tts_config.get("model", self.config["llm"]["model"]),
                speaker=tts_config.get("speaker", "Puck"),
                preamble=tts_config.get("preamble", ""),
                audio_dir=tts_config.get("audio_dir", "./audio_outputs")
            )
            self.tts_frequency = tts_config.get("frequency_percent", 30)
            logger.info(f"Cliente TTS inicializado (speaker: {tts_config.get('speaker', 'Puck')}, frecuencia: {self.tts_frequency}%, audio_dir: {tts_config.get('audio_dir', './audio_outputs')})")
        else:
            self.tts_client = None
            self.tts_frequency = 0
            logger.info("Cliente TTS deshabilitado")

        # Crear aplicación de Telegram
        self.app = Application.builder().token(
            self.config["telegram"]["bot_token"]
        ).build()

        # Diccionario para rastrear la última actividad de cada usuario
        self.user_last_activity = {}

        # Inicializar reloader de configuración
        self.config_reloader = ConfigReloader(config_file)
        logger.info("Sistema de recarga de configuración inicializado")

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
        logger.info(f"Comando /start recibido de usuario {user.id} ({user.username}, {user.first_name})")

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

        logger.info(f"Mensaje de bienvenida enviado a usuario {user.id}")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja el comando /help."""
        user = update.effective_user
        logger.info(f"Comando /help recibido de usuario {user.id}")

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
        logger.info(f"Comando /reset recibido de usuario {user_id}")

        self.conversation_manager.clear_user_history(user_id)

        reset_message = (
            "✨ He borrado nuestro historial de conversación.\n\n"
            "Podemos empezar de nuevo. ¿De qué te gustaría hablar?"
        )

        await update.message.reply_text(reset_message)
        logger.info(f"Historial de conversación borrado para usuario {user_id}")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja los mensajes de texto del usuario."""
        user = update.effective_user
        user_message = update.message.text

        logger.info(f"Mensaje recibido de usuario {user.id} ({user.username}): '{user_message[:100]}...'")

        # Actualizar última actividad
        self.user_last_activity[user.id] = datetime.now()
        logger.debug(f"Última actividad actualizada para usuario {user.id}")

        # Guardar mensaje del usuario
        self.conversation_manager.add_message(
            user_id=user.id,
            role="user",
            content=user_message,
            username=user.username or "",
            first_name=user.first_name or ""
        )
        logger.debug(f"Mensaje de usuario guardado en conversación {user.id}")

        # Obtener contexto de la conversación
        context_messages = self.conversation_manager.get_context(user.id)
        logger.debug(f"Contexto obtenido: {len(context_messages)} mensajes")

        # Obtener mood actual
        current_mood = self.mood_manager.get_current_mood()
        mood_prompt = self.mood_manager.get_mood_prompt()
        logger.debug(f"Mood actual: {current_mood.get('base_mood', 'N/A')}")

        # Obtener respuesta del LLM con el mood actual
        logger.debug(f"Solicitando respuesta al LLM para usuario {user.id}")
        assistant_response = self.llm_client.get_response(context_messages, mood_prompt)

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

        # Guardar respuesta del asistente con información de mood
        self.conversation_manager.add_message(
            user_id=user.id,
            role="assistant",
            content=assistant_response,
            mood_info=current_mood
        )

        # Decidir si enviar con voz según la frecuencia configurada
        send_audio = False
        if self.tts_client and self.tts_frequency > 0:
            # Generar número aleatorio entre 0 y 100
            random_value = random.randint(0, 100)
            send_audio = random_value < self.tts_frequency
            logger.debug(f"Decisión de audio: {random_value} < {self.tts_frequency} = {send_audio}")

        # Enviar respuesta al usuario (con o sin audio)
        if send_audio:
            logger.info(f"Generando audio de voz para usuario {user.id}")
            pcm_data = self.tts_client.generate_audio(assistant_response)

            if pcm_data:
                # Convertir PCM a WAV con headers correctos
                wav_data = self.tts_client.pcm_to_wav(pcm_data)

                # Enviar audio
                await update.message.reply_voice(voice=wav_data)
                logger.info(f"Audio WAV enviado a usuario {user.id} (tamaño PCM: {len(pcm_data)} bytes, WAV: {len(wav_data)} bytes)")
            else:
                # Si falla la generación de audio, enviar texto
                logger.warning(f"Error al generar audio para usuario {user.id}, enviando texto")
                await update.message.reply_text(assistant_response)
        else:
            # Enviar solo texto
            await update.message.reply_text(assistant_response)

        logger.info(f"Respuesta enviada a usuario {user.id} (longitud: {len(assistant_response)} caracteres, audio: {send_audio})")

    async def send_proactive_message(self, context: ContextTypes.DEFAULT_TYPE):
        """
        Envía mensajes proactivos a usuarios que llevan tiempo sin escribir.
        """
        logger.debug("Verificando usuarios para mensajes proactivos")

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
                logger.info(f"Usuario {user_id} inactivo por {time_inactive:.1f} minutos. Enviando mensaje proactivo...")
                try:
                    # Obtener contexto de la conversación
                    context_messages = self.conversation_manager.get_context(user_id)

                    # Decidir si usar una noticia (50% de probabilidad si hay noticias disponibles)
                    use_news = False
                    news_context = ""

                    if self.news_manager and random.random() < 0.5:
                        news_item = self.news_manager.get_random_news()
                        if news_item:
                            use_news = True
                            logger.debug(f"Usando noticia en mensaje proactivo: {news_item['title'][:50]}...")
                            news_context = f"\n\nNOTICIA RECIENTE:\nTítulo: {news_item['title']}\n"
                            if news_item.get('description'):
                                news_context += f"Resumen: {news_item['description']}\n"
                            if news_item.get('source'):
                                news_context += f"Fuente: {news_item['source']}\n"

                    # Crear un prompt especial para mensaje proactivo
                    if use_news:
                        proactive_content = (
                            "El usuario lleva un rato sin escribir. Inicia una conversación comentando "
                            "la siguiente noticia de forma natural y amigable. Menciona lo que te parece "
                            "interesante o pregunta su opinión al respecto. No copies el texto literal, "
                            "sino comenta sobre ella de manera conversacional." + news_context
                        )
                    else:
                        proactive_content = (
                            "El usuario lleva un rato sin escribir. Inicia una conversación de forma "
                            "natural y amigable. Puedes preguntar cómo está, proponer un tema interesante "
                            "para conversar, compartir algo curioso, o simplemente saludar de manera cálida. "
                            "Sé creativa y espontánea."
                        )

                    proactive_prompt = {
                        "role": "user",
                        "content": proactive_content
                    }

                    # Obtener mood actual
                    current_mood = self.mood_manager.get_current_mood()
                    mood_prompt = self.mood_manager.get_mood_prompt()

                    # Generar mensaje proactivo con mood
                    proactive_messages = context_messages + [proactive_prompt]
                    assistant_response = self.llm_client.get_response(proactive_messages, mood_prompt)

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

                    # Guardar mensaje del asistente con información de mood
                    self.conversation_manager.add_message(
                        user_id=user_id,
                        role="assistant",
                        content=assistant_response,
                        mood_info=current_mood
                    )

                    # Decidir si enviar con voz según la frecuencia configurada
                    send_audio = False
                    if self.tts_client and self.tts_frequency > 0:
                        random_value = random.randint(0, 100)
                        send_audio = random_value < self.tts_frequency
                        logger.debug(f"Decisión de audio (proactivo): {random_value} < {self.tts_frequency} = {send_audio}")

                    # Enviar mensaje proactivo al usuario (con o sin audio)
                    if send_audio:
                        logger.info(f"Generando audio de voz para mensaje proactivo a usuario {user_id}")
                        pcm_data = self.tts_client.generate_audio(assistant_response)

                        if pcm_data:
                            # Convertir PCM a WAV con headers correctos
                            wav_data = self.tts_client.pcm_to_wav(pcm_data)

                            await context.bot.send_voice(chat_id=user_id, voice=wav_data)
                            logger.info(f"Audio WAV proactivo enviado a usuario {user_id} (tamaño PCM: {len(pcm_data)} bytes, WAV: {len(wav_data)} bytes)")
                        else:
                            logger.warning(f"Error al generar audio proactivo para usuario {user_id}, enviando texto")
                            await context.bot.send_message(chat_id=user_id, text=assistant_response)
                    else:
                        await context.bot.send_message(chat_id=user_id, text=assistant_response)

                    # Actualizar última actividad (para no enviar otro mensaje inmediatamente)
                    self.user_last_activity[user_id] = datetime.now()

                    logger.info(f"Mensaje proactivo enviado exitosamente a usuario {user_id} (audio: {send_audio})")

                except Exception as e:
                    logger.error(f"Error al enviar mensaje proactivo a usuario {user_id}: {e}", exc_info=True)

    async def update_news_cache(self, context: ContextTypes.DEFAULT_TYPE):
        """
        Actualiza el caché de noticias RSS.
        Se ejecuta diariamente.
        """
        if self.news_manager:
            logger.info("Iniciando actualización de noticias RSS...")
            success = self.news_manager.update_news()
            if success:
                logger.info(f"Noticias actualizadas: {self.news_manager.get_news_count()} noticias en caché")
            else:
                logger.warning("No se pudieron actualizar las noticias")

    async def check_config_reload(self, context: ContextTypes.DEFAULT_TYPE):
        """
        Verifica si hay señal de recarga de configuración y la aplica.
        Se ejecuta periódicamente.
        """
        if self.config_reloader.check_reload_signal():
            logger.info("Señal de recarga detectada, recargando configuración...")
            self.config_reloader.reload_config(self)
            logger.info("Recarga de configuración completada")

    def run(self):
        """Inicia el bot."""
        logger.info("="*60)
        logger.info("Iniciando bot de Telegram...")
        logger.info("="*60)
        logger.info(f"Modelo LLM: {self.config['llm']['model']}")
        logger.info(f"Directorio de conversaciones: {self.config['storage']['conversations_dir']}")

        job_queue = self.app.job_queue

        # Configurar job para mensajes proactivos
        proactive_enabled = self.config.get("proactive", {}).get("enabled", True)
        check_interval = self.config.get("proactive", {}).get("check_interval_minutes", 15)

        if proactive_enabled:
            job_queue.run_repeating(
                self.send_proactive_message,
                interval=check_interval * 60,  # Convertir a segundos
                first=60  # Primer chequeo después de 1 minuto
            )
            logger.info(f"Mensajes proactivos habilitados (cada {check_interval} minutos)")
        else:
            logger.info("Mensajes proactivos deshabilitados")

        # Configurar job para actualizar noticias diariamente
        if self.news_manager:
            job_queue.run_repeating(
                self.update_news_cache,
                interval=24 * 60 * 60,  # Una vez al día (en segundos)
                first=10  # Primera actualización a los 10 segundos de iniciar
            )
            logger.info("Actualización diaria de noticias habilitada")
        else:
            logger.info("Gestor de noticias no disponible")

        # Configurar job para verificar recarga de configuración
        job_queue.run_repeating(
            self.check_config_reload,
            interval=30,  # Cada 30 segundos
            first=5  # Primera verificación a los 5 segundos de iniciar
        )
        logger.info("Verificación de recarga de configuración habilitada (cada 30 segundos)")

        logger.info("Bot iniciado. Esperando mensajes...")
        logger.info("="*60)
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
