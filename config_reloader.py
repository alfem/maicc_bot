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
