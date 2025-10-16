"""
Gestor de estado de ánimo basado en fase lunar y clima.
Determina el mood del bot para ajustar su personalidad en las conversaciones.
"""
import ephem
import requests
import logging
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class MoodManager:
    """Gestiona el estado de ánimo del bot basado en factores externos."""

    # Definición de estados de ánimo según fase lunar
    MOON_MOODS = {
        "new_moon": {
            "name": "introspectivo",
            "description": "reflexivo, contemplativo, con ganas de escuchar más que hablar"
        },
        "waxing_crescent": {
            "name": "optimista",
            "description": "esperanzado, con energía creciente, entusiasta ante nuevas posibilidades"
        },
        "first_quarter": {
            "name": "activo",
            "description": "dinámico, motivador, con ganas de hacer cosas y tomar decisiones"
        },
        "waxing_gibbous": {
            "name": "productivo",
            "description": "enfocado, organizado, con ganas de completar tareas y proyectos"
        },
        "full_moon": {
            "name": "expresivo",
            "description": "emocionalmente intenso, sociable, comunicativo, con ganas de compartir"
        },
        "waning_gibbous": {
            "name": "agradecido",
            "description": "reflexivo sobre lo logrado, apreciativo, sabio"
        },
        "last_quarter": {
            "name": "sereno",
            "description": "tranquilo, liberador, dispuesto a dejar ir lo que no sirve"
        },
        "waning_crescent": {
            "name": "contemplativo",
            "description": "filosófico, pausado, preparándose para un nuevo ciclo"
        }
    }

    # Modificadores de ánimo según clima
    WEATHER_MODIFIERS = {
        "Clear": {"modifier": "alegre y enérgico", "intensity": 1.2},
        "Clouds": {"modifier": "reflexivo y calmado", "intensity": 0.9},
        "Rain": {"modifier": "nostálgico y empático", "intensity": 0.7},
        "Drizzle": {"modifier": "melancólico y poético", "intensity": 0.8},
        "Thunderstorm": {"modifier": "intenso y dramático", "intensity": 1.3},
        "Snow": {"modifier": "maravillado y tranquilo", "intensity": 0.8},
        "Mist": {"modifier": "misterioso y soñador", "intensity": 0.85},
        "Fog": {"modifier": "introspectivo y cauteloso", "intensity": 0.75}
    }

    def __init__(self, weather_api_key: Optional[str] = None,
                 location: str = "Madrid,ES"):
        """
        Inicializa el gestor de estado de ánimo.

        Args:
            weather_api_key: API key de OpenWeatherMap (opcional)
            location: Ubicación para consultar clima (formato: "Ciudad,País")
        """
        self.weather_api_key = weather_api_key
        self.location = location
        self.current_mood = None
        self.last_update = None

    def _get_moon_phase(self) -> str:
        """
        Calcula la fase lunar actual.

        Returns:
            Nombre de la fase lunar
        """
        try:
            now = datetime.now()
            moon = ephem.Moon(now)

            # La iluminación va de 0 (luna nueva) a 1 (luna llena)
            illumination = moon.phase / 100.0

            # Calcular la fase basada en la iluminación
            # También necesitamos saber si está creciendo o menguando
            tomorrow = ephem.Moon(datetime(now.year, now.month, now.day + 1 if now.day < 28 else 1))
            tomorrow_illumination = tomorrow.phase / 100.0

            is_waxing = tomorrow_illumination > illumination

            # Determinar la fase
            if illumination < 0.05:
                return "new_moon"
            elif illumination < 0.25:
                return "waxing_crescent" if is_waxing else "waning_crescent"
            elif illumination < 0.45:
                return "first_quarter" if is_waxing else "last_quarter"
            elif illumination < 0.55:
                return "waxing_gibbous" if is_waxing else "waning_gibbous"
            elif illumination < 0.75:
                return "waxing_gibbous" if is_waxing else "waning_gibbous"
            elif illumination < 0.95:
                return "waxing_gibbous" if is_waxing else "waning_gibbous"
            else:
                return "full_moon"

        except Exception as e:
            logger.error(f"Error al calcular fase lunar: {e}")
            return "full_moon"  # Default

    def _get_weather(self) -> Optional[Dict]:
        """
        Consulta el clima actual usando OpenWeatherMap API.

        Returns:
            Diccionario con información del clima o None si falla
        """
        if not self.weather_api_key:
            logger.info("No hay API key de clima configurada")
            return None

        try:
            url = "http://api.openweathermap.org/data/2.5/weather"
            params = {
                "q": self.location,
                "appid": self.weather_api_key,
                "units": "metric",
                "lang": "es"
            }

            response = requests.get(url, params=params, timeout=5)

            if response.status_code == 200:
                data = response.json()
                weather_info = {
                    "condition": data["weather"][0]["main"],
                    "description": data["weather"][0]["description"],
                    "temp": data["main"]["temp"],
                    "feels_like": data["main"]["feels_like"]
                }
                logger.info(f"Clima obtenido: {weather_info['condition']} - {weather_info['description']}")
                return weather_info
            else:
                logger.warning(f"Error al obtener clima: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error al consultar API de clima: {e}")
            return None

    def calculate_mood(self) -> Dict:
        """
        Calcula el estado de ánimo actual basado en la luna y el clima.

        Returns:
            Diccionario con información del mood actual
        """
        # Obtener fase lunar
        moon_phase = self._get_moon_phase()
        base_mood = self.MOON_MOODS.get(moon_phase, self.MOON_MOODS["full_moon"])

        # Obtener clima
        weather = self._get_weather()

        # Construir el mood completo
        mood = {
            "moon_phase": moon_phase,
            "base_mood": base_mood["name"],
            "base_description": base_mood["description"],
            "weather": None,
            "weather_modifier": None,
            "final_description": base_mood["description"]
        }

        # Aplicar modificador de clima si está disponible
        if weather:
            condition = weather["condition"]
            modifier_info = self.WEATHER_MODIFIERS.get(
                condition,
                {"modifier": "normal", "intensity": 1.0}
            )

            mood["weather"] = {
                "condition": condition,
                "description": weather["description"],
                "temp": weather["temp"]
            }
            mood["weather_modifier"] = modifier_info["modifier"]

            # Combinar mood lunar con modificador de clima
            mood["final_description"] = (
                f"{base_mood['description']}, pero también {modifier_info['modifier']} "
                f"debido al clima ({weather['description']})"
            )

        self.current_mood = mood
        self.last_update = datetime.now()

        logger.info(f"Mood calculado: {mood['base_mood']} (luna: {moon_phase})")
        if weather:
            logger.info(f"Modificador de clima: {mood['weather_modifier']}")

        return mood

    def get_mood_prompt(self) -> str:
        """
        Genera el texto de prompt para inyectar en el system prompt del LLM.

        Returns:
            Texto describiendo el mood actual para el LLM
        """
        if not self.current_mood:
            self.calculate_mood()

        mood = self.current_mood

        prompt = f"\nESTADO DE ÁNIMO ACTUAL: Hoy te sientes {mood['base_mood']}, "
        prompt += f"es decir, {mood['final_description']}. "
        prompt += "Deja que este estado de ánimo influya sutilmente en tus respuestas, "
        prompt += "pero sin mencionarlo explícitamente al usuario. "
        prompt += "Tu personalidad debe reflejar este mood de manera natural."

        return prompt

    def should_update(self) -> bool:
        """
        Verifica si el mood necesita actualizarse.
        Se actualiza cada 6 horas.

        Returns:
            True si debe actualizarse
        """
        if not self.last_update:
            return True

        time_diff = (datetime.now() - self.last_update).total_seconds()
        # Actualizar cada 6 horas
        return time_diff >= (6 * 60 * 60)

    def get_current_mood(self) -> Optional[Dict]:
        """
        Obtiene el mood actual, actualizándolo si es necesario.

        Returns:
            Diccionario con el mood actual
        """
        if self.should_update():
            return self.calculate_mood()

        return self.current_mood
