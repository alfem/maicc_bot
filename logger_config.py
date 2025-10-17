"""
Configuración centralizada de logging para el bot.
Crea loggers separados para Telegram y LLM con rotación diaria.
"""
import logging
import os
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
from typing import Dict, Any


def setup_logging(config: Dict[str, Any]) -> Dict[str, logging.Logger]:
    """
    Configura los loggers según la configuración proporcionada.

    Args:
        config: Diccionario de configuración completo del bot

    Returns:
        Diccionario con los loggers configurados {'telegram': logger, 'llm': logger}
    """
    log_config = config.get("logging", {})
    log_dir = log_config.get("log_dir", "./logs")
    log_level = log_config.get("level", "INFO")
    log_format = log_config.get("format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    date_format = log_config.get("date_format", "%Y-%m-%d %H:%M:%S")

    # Crear directorio de logs si no existe
    os.makedirs(log_dir, exist_ok=True)

    # Configurar formato
    formatter = logging.Formatter(log_format, datefmt=date_format)

    # Diccionario para almacenar los loggers
    loggers = {}

    # Configurar loggers individuales
    loggers_config = log_config.get("loggers", {})

    for logger_name, logger_config in loggers_config.items():
        filename_prefix = logger_config.get("filename_prefix", logger_name)
        level = logger_config.get("level", log_level)

        # Crear logger
        logger = logging.getLogger(logger_name)
        logger.setLevel(getattr(logging, level.upper()))

        # Limpiar handlers existentes
        logger.handlers.clear()

        # Crear handler con rotación diaria
        log_file = os.path.join(log_dir, f"{filename_prefix}.log")
        file_handler = TimedRotatingFileHandler(
            filename=log_file,
            when='midnight',  # Rotar a medianoche
            interval=1,  # Cada 1 día
            backupCount=30,  # Mantener 30 días de logs
            encoding='utf-8'
        )

        # Configurar nombre de archivo de respaldo con fecha
        file_handler.suffix = "%Y-%m-%d"
        file_handler.setFormatter(formatter)
        file_handler.setLevel(getattr(logging, level.upper()))

        # Agregar handler al logger
        logger.addHandler(file_handler)

        # Agregar también handler para consola
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(getattr(logging, level.upper()))
        logger.addHandler(console_handler)

        # Evitar propagación al logger raíz
        logger.propagate = False

        loggers[logger_name] = logger

        logger.info(f"Logger '{logger_name}' configurado: {log_file}")

    return loggers


def get_logger(name: str) -> logging.Logger:
    """
    Obtiene un logger por nombre.

    Args:
        name: Nombre del logger ('telegram' o 'llm')

    Returns:
        Logger configurado
    """
    logger = logging.getLogger(name)

    # Si el logger no tiene handlers, está sin configurar
    if not logger.handlers:
        # Configuración mínima por defecto
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.warning(f"Logger '{name}' no configurado, usando configuración por defecto")

    return logger
