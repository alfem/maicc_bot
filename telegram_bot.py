"""
Bot de Telegram que actúa como compañero conversacional.
"""
import json
import logging
import random
import asyncio
import os
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from conversation_manager import ConversationManager
from llm_client import create_llm_client
from news_manager import NewsManager
from mood_manager import MoodManager
from tts_client import create_tts_client
from memory_manager import MemoryManager
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

        # Configurar variables de entorno para mem0
        # mem0 necesita estas variables según el proveedor usado
        if 'GOOGLE_API_KEY' not in os.environ:
            gemini_api_key = self.config["llm"].get("gemini", {}).get("api_key", "")
            if gemini_api_key:
                os.environ['GOOGLE_API_KEY'] = gemini_api_key
                logger.info("GOOGLE_API_KEY configurada desde config.json")

        # Configurar API key de OpenAI para LLM principal si se usa
        llm_provider = self.config["llm"].get("provider", "gemini")
        if llm_provider == "openai":
            openai_api_key = self.config["llm"].get("openai", {}).get("api_key", "")
            if openai_api_key and 'OPENAI_API_KEY' not in os.environ:
                os.environ['OPENAI_API_KEY'] = openai_api_key
                logger.info("OPENAI_API_KEY configurada desde config.json")

        # Inicializar gestor de memorias mem0 si está habilitado
        mem0_config = self.config.get("mem0", {})
        mem0_enabled = mem0_config.get("enabled", False)

        # Configurar API key de OpenAI si mem0 usa OpenAI como proveedor LLM
        if mem0_enabled:
            mem0_llm_provider = mem0_config.get("llm", {}).get("provider", "gemini")
            if mem0_llm_provider == "openai":
                openai_api_key = mem0_config.get("llm", {}).get("openai", {}).get("api_key", "")
                if openai_api_key and 'OPENAI_API_KEY' not in os.environ:
                    os.environ['OPENAI_API_KEY'] = openai_api_key
                    logger.info("OPENAI_API_KEY configurada para mem0 desde config.json")

        if mem0_enabled:
            self.memory_manager = MemoryManager(
                config={
                    "history_db_path": mem0_config.get("history_db_path", "/tmp/mem0_history.db"),
                    "vector_store": mem0_config.get("vector_store", {}),
                    "llm": mem0_config.get("llm", {}),
                    "embedder": mem0_config.get("embedder", {})
                },
                enabled=True
            )
            logger.info("Gestor de memorias mem0 inicializado")
        else:
            self.memory_manager = None
            logger.info("Gestor de memorias mem0 deshabilitado")

        # Inicializar componentes
        self.conversation_manager = ConversationManager(
            conversations_dir=self.config["storage"]["conversations_dir"],
            max_context_messages=self.config["storage"]["max_context_messages"],
            memory_manager=self.memory_manager
        )

        # Inicializar cliente LLM según el proveedor configurado
        llm_provider = self.config["llm"].get("provider", "gemini")
        logger.info(f"Inicializando LLM con proveedor: {llm_provider}")
        self.llm_client = create_llm_client(llm_provider, self.config["llm"])

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
            provider = tts_config.get("provider", "gemini")
            provider_config = tts_config.get(provider, {})

            # Añadir audio_dir a la configuración del proveedor
            provider_config["audio_dir"] = tts_config.get("audio_dir", "./audio_outputs")

            try:
                self.tts_client = create_tts_client(provider, provider_config)
                self.tts_frequency = tts_config.get("frequency_percent", 30)
                logger.info(f"Cliente TTS inicializado (proveedor: {provider}, frecuencia: {self.tts_frequency}%, audio_dir: {provider_config['audio_dir']})")
            except ValueError as e:
                logger.error(f"Error al inicializar TTS: {e}")
                self.tts_client = None
                self.tts_frequency = 0
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

        # Diccionario para rastrear temporizadores de agrupación de mensajes
        self.pending_timers = {}

        # Inicializar reloader de configuración
        self.config_reloader = ConfigReloader(config_file)
        logger.info("Sistema de recarga de configuración inicializado")

        # Registrar manejadores
        self._register_handlers()

    def _calculate_thinking_delay(self) -> float:
        """
        Calcula un retraso de "pensamiento" antes de empezar a escribir.
        Simula el tiempo que una persona tomaría en pensar qué responder.

        Returns:
            Tiempo de retraso en segundos (entre 2 y 5 segundos)
        """
        return random.uniform(2.0, 5.0)

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

        # Borrar historial de conversación en JSON
        self.conversation_manager.clear_user_history(user_id)

        # Borrar memorias de mem0 si está habilitado
        if self.memory_manager and self.memory_manager.enabled:
            success = self.memory_manager.delete_all_memories(user_id)
            if success:
                logger.info(f"Memorias de mem0 borradas para usuario {user_id}")
            else:
                logger.warning(f"No se pudieron borrar memorias de mem0 para usuario {user_id}")

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

        # Cancelar temporizador existente si hay uno (el usuario está escribiendo más mensajes)
        if user.id in self.pending_timers:
            self.pending_timers[user.id].cancel()
            logger.debug(f"Temporizador de respuesta cancelado para usuario {user.id} (nuevo mensaje recibido)")

        # Configurar delay de agrupación de mensajes
        grouping_delay = self.config.get("telegram", {}).get("message_grouping_delay", 5.0)
        logger.info(f"Esperando {grouping_delay:.1f} segundos para agrupar mensajes de usuario {user.id}")

        # Crear nuevo temporizador para procesar la respuesta después del delay
        self.pending_timers[user.id] = asyncio.create_task(
            self._process_response(user, update)
        )

    async def _process_response(self, user, update: Update):
        """
        Procesa y envía la respuesta al usuario después del delay de agrupación.

        Args:
            user: Objeto de usuario de Telegram
            update: Update object de Telegram
        """
        # Obtener delay de agrupación
        grouping_delay = self.config.get("telegram", {}).get("message_grouping_delay", 5.0)

        try:
            # Esperar el delay de agrupación (permite que el usuario envíe más mensajes)
            await asyncio.sleep(grouping_delay)
        except asyncio.CancelledError:
            # El temporizador fue cancelado (usuario envió otro mensaje)
            logger.debug(f"Procesamiento de respuesta cancelado para usuario {user.id}")
            return

        # Limpiar temporizador del diccionario
        if user.id in self.pending_timers:
            del self.pending_timers[user.id]

        logger.info(f"Procesando respuesta para usuario {user.id} tras {grouping_delay:.1f}s de espera")

        # Pausa de "pensamiento" antes de procesar (simula humano pensando qué responder)
        thinking_delay = self._calculate_thinking_delay()
        logger.info(f"Pausa de pensamiento: {thinking_delay:.2f} segundos (sin mostrar 'typing')")
        await asyncio.sleep(thinking_delay)

        # Obtener contexto de la conversación
        context_messages = self.conversation_manager.get_context(user.id)
        logger.debug(f"Contexto obtenido: {len(context_messages)} mensajes")

        # Obtener el último mensaje del usuario para búsqueda de memorias
        last_user_message = ""
        for msg in reversed(context_messages):
            if msg.get("role") == "user":
                last_user_message = msg.get("content", "")
                break

        # Recuperar memorias relevantes de mem0 si está habilitado
        memories_context = ""
        if self.memory_manager and self.memory_manager.enabled and last_user_message:
            logger.debug(f"Recuperando memorias relevantes de mem0 para usuario {user.id}")
            memories = self.memory_manager.get_relevant_memories(
                user_id=user.id,
                query=last_user_message,
                limit=5
            )
            if memories:
                memories_context = self.memory_manager.format_memories_for_context(memories)
                logger.info(f"Memorias recuperadas de mem0: {len(memories)} memorias relevantes")
            else:
                logger.debug("No se encontraron memorias relevantes en mem0")

        # Obtener mood actual
        current_mood = self.mood_manager.get_current_mood()
        mood_prompt = self.mood_manager.get_mood_prompt()
        logger.debug(f"Mood actual: {current_mood.get('base_mood', 'N/A')}")

        # Combinar mood y memorias en el contexto adicional
        additional_context = mood_prompt
        if memories_context:
            additional_context = memories_context + "\n\n" + mood_prompt

        # Obtener respuesta del LLM con el contexto, memorias y mood actual
        logger.debug(f"Solicitando respuesta al LLM para usuario {user.id}")
        assistant_response = self.llm_client.get_response(context_messages, additional_context)

        # Calcular retraso de escritura basado en la longitud de la respuesta
        typing_delay = self._calculate_typing_delay(assistant_response)
        logger.info(f"Pausa de escritura: {typing_delay:.2f} segundos (mostrando 'typing...') para {user.id}")

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
            audio_data = self.tts_client.generate_audio(assistant_response)

            if audio_data:
                # Si el cliente es de Google Gemini, convertir PCM a WAV
                # Si es Eleven Labs, el audio ya viene en formato MP3 listo para usar
                if hasattr(self.tts_client, 'pcm_to_wav'):
                    # Es cliente de Gemini, necesita conversión
                    audio_data = self.tts_client.pcm_to_wav(audio_data)
                    logger.info(f"Audio convertido a WAV para usuario {user.id} (tamaño: {len(audio_data)} bytes)")
                else:
                    # Es cliente de Eleven Labs, audio ya está en formato final
                    logger.info(f"Audio MP3 listo para usuario {user.id} (tamaño: {len(audio_data)} bytes)")

                # Enviar audio
                await update.message.reply_voice(voice=audio_data)
                logger.info(f"Audio enviado a usuario {user.id}")
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

                    # Pausa de "pensamiento" antes de procesar (simula humano pensando qué responder)
                    thinking_delay = self._calculate_thinking_delay()
                    logger.info(f"Pausa de pensamiento proactiva: {thinking_delay:.2f} segundos (sin mostrar 'typing')")
                    await asyncio.sleep(thinking_delay)

                    # Generar mensaje proactivo con mood
                    proactive_messages = context_messages + [proactive_prompt]
                    assistant_response = self.llm_client.get_response(proactive_messages, mood_prompt)

                    # Calcular retraso de escritura basado en la longitud de la respuesta
                    typing_delay = self._calculate_typing_delay(assistant_response)
                    logger.info(f"Pausa de escritura proactiva: {typing_delay:.2f} segundos (mostrando 'typing...') para {user_id}")

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
                        audio_data = self.tts_client.generate_audio(assistant_response)

                        if audio_data:
                            # Si el cliente es de Google Gemini, convertir PCM a WAV
                            # Si es Eleven Labs, el audio ya viene en formato MP3 listo para usar
                            if hasattr(self.tts_client, 'pcm_to_wav'):
                                # Es cliente de Gemini, necesita conversión
                                audio_data = self.tts_client.pcm_to_wav(audio_data)
                                logger.info(f"Audio proactivo convertido a WAV para usuario {user_id} (tamaño: {len(audio_data)} bytes)")
                            else:
                                # Es cliente de Eleven Labs, audio ya está en formato final
                                logger.info(f"Audio proactivo MP3 listo para usuario {user_id} (tamaño: {len(audio_data)} bytes)")

                            await context.bot.send_voice(chat_id=user_id, voice=audio_data)
                            logger.info(f"Audio proactivo enviado a usuario {user_id}")
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
