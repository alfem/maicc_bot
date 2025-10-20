"""
Sistema de recarga de configuración mediante archivo de señales.
Permite recargar la configuración del bot sin reiniciar el proceso.
"""
import json
import os
from datetime import datetime
from logger_config import get_logger

logger = get_logger('telegram')

RELOAD_SIGNAL_FILE = '.reload_signal'


class ConfigReloader:
    """Gestiona la recarga de configuración del bot."""

    def __init__(self, config_file: str = "config.json"):
        """
        Inicializa el reloader de configuración.

        Args:
            config_file: Ruta al archivo de configuración
        """
        self.config_file = config_file
        self.last_reload = datetime.now()

    def check_reload_signal(self) -> bool:
        """
        Verifica si existe una señal de recarga.

        Returns:
            True si hay señal de recarga, False en caso contrario
        """
        if os.path.exists(RELOAD_SIGNAL_FILE):
            logger.info("Señal de recarga detectada")
            try:
                # Leer el archivo de señal para obtener información
                with open(RELOAD_SIGNAL_FILE, 'r') as f:
                    signal_data = json.load(f)
                    logger.info(f"Recarga solicitada: {signal_data.get('reason', 'Sin razón especificada')}")
                    logger.info(f"Solicitada por: {signal_data.get('source', 'Desconocido')}")
            except Exception as e:
                logger.warning(f"No se pudo leer información del archivo de señal: {e}")

            # Eliminar el archivo de señal
            try:
                os.remove(RELOAD_SIGNAL_FILE)
                logger.debug("Archivo de señal eliminado")
            except Exception as e:
                logger.error(f"Error al eliminar archivo de señal: {e}")

            return True
        return False

    def reload_config(self, bot_instance):
        """
        Recarga la configuración del bot.

        Args:
            bot_instance: Instancia de CompanionBot
        """
        try:
            logger.info("="*60)
            logger.info("Iniciando recarga de configuración...")
            logger.info("="*60)

            # Cargar nueva configuración
            with open(self.config_file, 'r', encoding='utf-8') as f:
                new_config = json.load(f)

            logger.info("Nueva configuración cargada desde archivo")

            # Actualizar configuración en la instancia del bot
            old_config = bot_instance.config
            bot_instance.config = new_config

            # Reconstruir el cliente LLM con nueva configuración
            from llm_client import LLMClient
            bot_instance.llm_client = LLMClient(
                api_key=new_config["llm"]["api_key"],
                model=new_config["llm"]["model"],
                max_tokens=new_config["llm"]["max_tokens"],
                temperature=new_config["llm"]["temperature"],
                system_prompt=new_config["llm"]["system_prompt"],
                api_url=new_config["llm"]["api_url"]
            )
            logger.info("Cliente LLM reconstruido con nueva configuración")

            # Actualizar gestor de noticias si cambió
            rss_feeds = new_config.get("news", {}).get("rss_feeds", [])
            if rss_feeds != old_config.get("news", {}).get("rss_feeds", []):
                if rss_feeds:
                    from news_manager import NewsManager
                    storage_file = new_config.get("news", {}).get("cache_file", "./news_cache.json")
                    bot_instance.news_manager = NewsManager(rss_feeds, storage_file)
                    logger.info(f"Gestor de noticias actualizado con {len(rss_feeds)} feeds")
                else:
                    bot_instance.news_manager = None
                    logger.info("Gestor de noticias deshabilitado")

            # Actualizar gestor de mood si cambió
            mood_config = new_config.get("mood", {})
            old_mood_config = old_config.get("mood", {})
            if (mood_config.get("weather_api_key") != old_mood_config.get("weather_api_key") or
                mood_config.get("location") != old_mood_config.get("location")):
                from mood_manager import MoodManager
                weather_api_key = mood_config.get("weather_api_key")
                location = mood_config.get("location", "Madrid,ES")
                bot_instance.mood_manager = MoodManager(weather_api_key, location)
                logger.info(f"Gestor de mood actualizado (ubicación: {location})")

            # Actualizar cliente TTS si cambió o se habilitó/deshabilitó
            tts_config = new_config.get("tts", {})
            old_tts_config = old_config.get("tts", {})

            # Verificar si cambió algún parámetro de TTS
            tts_changed = (
                tts_config.get("enabled") != old_tts_config.get("enabled") or
                tts_config.get("model") != old_tts_config.get("model") or
                tts_config.get("speaker") != old_tts_config.get("speaker") or
                tts_config.get("preamble") != old_tts_config.get("preamble") or
                tts_config.get("temperature") != old_tts_config.get("temperature") or
                tts_config.get("frequency_percent") != old_tts_config.get("frequency_percent")
            )

            if tts_changed:
                logger.info("Detectados cambios en configuración de TTS")
                if tts_config.get("enabled", False):
                    from tts_client import TTSClient
                    bot_instance.tts_client = TTSClient(
                        api_key=new_config["llm"]["api_key"],
                        model=tts_config.get("model", new_config["llm"]["model"]),
                        speaker=tts_config.get("speaker", "Leda"),
                        preamble=tts_config.get("preamble", ""),
                        temperature=tts_config.get("temperature", 0.5),
                        audio_dir=tts_config.get("audio_dir", "./audio_outputs")
                    )
                    bot_instance.tts_frequency = tts_config.get("frequency_percent", 30)
                    logger.info(f"Cliente TTS reconstruido (speaker: {tts_config.get('speaker', 'Leda')}, temperature: {tts_config.get('temperature', 0.5)}, frecuencia: {bot_instance.tts_frequency}%)")
                else:
                    bot_instance.tts_client = None
                    bot_instance.tts_frequency = 0
                    logger.info("Cliente TTS deshabilitado")

            self.last_reload = datetime.now()

            logger.info("="*60)
            logger.info("✅ Configuración recargada exitosamente")
            logger.info("="*60)

            # Log de cambios importantes
            self._log_config_changes(old_config, new_config)

        except Exception as e:
            logger.error(f"❌ Error al recargar configuración: {e}", exc_info=True)

    def _log_config_changes(self, old_config, new_config):
        """
        Registra los cambios importantes en la configuración.

        Args:
            old_config: Configuración anterior
            new_config: Nueva configuración
        """
        changes = []

        # Cambios en LLM
        if old_config["llm"]["temperature"] != new_config["llm"]["temperature"]:
            changes.append(f"  - Temperatura: {old_config['llm']['temperature']} → {new_config['llm']['temperature']}")

        if old_config["llm"]["max_tokens"] != new_config["llm"]["max_tokens"]:
            changes.append(f"  - Max tokens: {old_config['llm']['max_tokens']} → {new_config['llm']['max_tokens']}")

        if old_config["llm"]["system_prompt"] != new_config["llm"]["system_prompt"]:
            changes.append(f"  - System prompt modificado (longitud: {len(old_config['llm']['system_prompt'])} → {len(new_config['llm']['system_prompt'])} caracteres)")

        # Cambios en proactive
        if old_config["proactive"]["inactivity_minutes"] != new_config["proactive"]["inactivity_minutes"]:
            changes.append(f"  - Minutos de inactividad: {old_config['proactive']['inactivity_minutes']} → {new_config['proactive']['inactivity_minutes']}")

        # Cambios en quiet hours
        old_quiet = old_config.get("proactive", {}).get("quiet_hours", {})
        new_quiet = new_config.get("proactive", {}).get("quiet_hours", {})
        if old_quiet != new_quiet:
            changes.append(f"  - Horario de silencio modificado")

        # Cambios en RSS feeds
        old_rss = old_config.get("news", {}).get("rss_feeds", [])
        new_rss = new_config.get("news", {}).get("rss_feeds", [])
        if old_rss != new_rss:
            changes.append(f"  - Feeds RSS: {len(old_rss)} → {len(new_rss)}")

        # Cambios en TTS
        old_tts = old_config.get("tts", {})
        new_tts = new_config.get("tts", {})

        if old_tts.get("enabled") != new_tts.get("enabled"):
            changes.append(f"  - TTS habilitado: {old_tts.get('enabled', False)} → {new_tts.get('enabled', False)}")

        if new_tts.get("enabled", False):
            if old_tts.get("model") != new_tts.get("model"):
                changes.append(f"  - TTS Modelo: {old_tts.get('model', 'N/A')} → {new_tts.get('model', 'N/A')}")

            if old_tts.get("speaker") != new_tts.get("speaker"):
                changes.append(f"  - TTS Speaker: {old_tts.get('speaker', 'N/A')} → {new_tts.get('speaker', 'N/A')}")

            if old_tts.get("preamble") != new_tts.get("preamble"):
                old_preamble = old_tts.get("preamble", "")
                new_preamble = new_tts.get("preamble", "")
                changes.append(f"  - TTS Preámbulo: '{old_preamble[:30]}...' → '{new_preamble[:30]}...'")

            if old_tts.get("temperature") != new_tts.get("temperature"):
                changes.append(f"  - TTS Temperatura: {old_tts.get('temperature', 'N/A')} → {new_tts.get('temperature', 'N/A')}")

            if old_tts.get("frequency_percent") != new_tts.get("frequency_percent"):
                changes.append(f"  - TTS Frecuencia: {old_tts.get('frequency_percent', 'N/A')}% → {new_tts.get('frequency_percent', 'N/A')}%")

        if changes:
            logger.info("Cambios detectados:")
            for change in changes:
                logger.info(change)
        else:
            logger.info("No se detectaron cambios significativos")


def create_reload_signal(reason: str = "Configuración actualizada", source: str = "web_interface"):
    """
    Crea un archivo de señal para solicitar recarga de configuración.

    Args:
        reason: Razón de la recarga
        source: Origen de la solicitud
    """
    signal_data = {
        "timestamp": datetime.now().isoformat(),
        "reason": reason,
        "source": source
    }

    try:
        with open(RELOAD_SIGNAL_FILE, 'w') as f:
            json.dump(signal_data, f, indent=2)
        logger.info(f"Señal de recarga creada: {reason}")
        return True
    except Exception as e:
        logger.error(f"Error al crear señal de recarga: {e}")
        return False
