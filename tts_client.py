"""
Cliente para generación de voz usando la API de Google Gemini.
"""
from google import genai
from google.genai import types
from typing import Optional
from logger_config import get_logger

# Logger específico para TTS
logger = get_logger('llm')  # Usamos el mismo logger que LLM


class TTSClient:
    """Cliente para generar audio de voz usando Google Gemini."""

    def __init__(self, api_key: str, model: str, speaker: str = "Puck",
                 preamble: str = ""):
        """
        Inicializa el cliente de Text-to-Speech.

        Args:
            api_key: Clave de API de Google Gemini
            model: Nombre del modelo a usar (ej: gemini-2.5-flash-preview-tts)
            speaker: Nombre del speaker/voz a usar (Puck, Charon, Kore, Fenrir, Aoede)
            preamble: Texto para añadir antes del contenido a convertir
        """
        logger.info(f"Inicializando TTSClient con modelo: {model}, speaker: {speaker}")

        # Configurar cliente con API key
        self.client = genai.Client(api_key=api_key)

        self.model_name = model
        self.speaker = speaker
        self.preamble = preamble

        logger.info("TTSClient inicializado correctamente")

    def generate_audio(self, text: str) -> Optional[bytes]:
        """
        Genera audio de voz a partir de texto.

        Args:
            text: Texto a convertir en voz

        Returns:
            Bytes del archivo de audio en formato WAV, o None si hay error
        """
        try:
            logger.info(f"Generando audio de voz (longitud texto: {len(text)} caracteres)")

            # Preparar el texto con el preámbulo
            full_text = self.preamble + text if self.preamble else text
            logger.debug(f"Texto completo para TTS: '{full_text[:100]}...'")

            # Generar el contenido con speech usando la nueva API
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=self.speaker
                            )
                        )
                    )
                )
            )

            # Verificar que hay audio en la respuesta
            if not response.candidates or not response.candidates[0].content.parts:
                logger.warning("La respuesta no contiene audio")
                return None

            # Obtener el audio de la respuesta
            audio_data = response.candidates[0].content.parts[0].inline_data.data

            if not audio_data:
                logger.warning("No se encontró audio en la respuesta")
                return None

            logger.info(f"Audio generado exitosamente (tamaño: {len(audio_data)} bytes)")
            return audio_data

        except Exception as e:
            logger.error(f"Error al generar audio con la API de Gemini: {e}", exc_info=True)
            return None

    def update_speaker(self, speaker: str):
        """
        Actualiza el speaker/voz a utilizar.

        Args:
            speaker: Nombre del nuevo speaker
        """
        logger.info(f"Actualizando speaker de '{self.speaker}' a '{speaker}'")
        self.speaker = speaker

    def update_preamble(self, preamble: str):
        """
        Actualiza el preámbulo a utilizar.

        Args:
            preamble: Nuevo texto de preámbulo
        """
        logger.info(f"Actualizando preámbulo")
        self.preamble = preamble
