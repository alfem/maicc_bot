"""
Cliente para generación de voz usando la API de Google Gemini.
"""
from google import genai
from google.genai import types
from typing import Optional
from logger_config import get_logger
import os
from datetime import datetime

# Logger específico para TTS
logger = get_logger('llm')  # Usamos el mismo logger que LLM


class TTSClient:
    """Cliente para generar audio de voz usando Google Gemini."""

    def __init__(self, api_key: str, model: str, speaker: str = "Puck",
                 preamble: str = "", audio_dir: str = "./audio_outputs"):
        """
        Inicializa el cliente de Text-to-Speech.

        Args:
            api_key: Clave de API de Google Gemini
            model: Nombre del modelo a usar (ej: gemini-2.5-flash-preview-tts)
            speaker: Nombre del speaker/voz a usar (Puck, Charon, Kore, Fenrir, Aoede)
            preamble: Texto para añadir antes del contenido a convertir
            audio_dir: Directorio donde guardar los audios generados
        """
        logger.info(f"Inicializando TTSClient con modelo: {model}, speaker: {speaker}")

        # Configurar cliente con API key
        self.client = genai.Client(api_key=api_key)

        self.model_name = model
        self.speaker = speaker
        self.preamble = preamble
        self.audio_dir = audio_dir

        # Crear directorio de audios si no existe
        if not os.path.exists(audio_dir):
            os.makedirs(audio_dir)
            logger.info(f"Directorio de audios creado: {audio_dir}")

        logger.info("TTSClient inicializado correctamente")

    def generate_audio(self, text: str, save_to_disk: bool = True) -> Optional[bytes]:
        """
        Genera audio de voz a partir de texto.

        Args:
            text: Texto a convertir en voz
            save_to_disk: Si es True, guarda el audio en disco para depuración

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
                logger.debug(f"Respuesta completa: {response}")
                return None

            # Obtener el audio de la respuesta
            part = response.candidates[0].content.parts[0]

            # Depuración: ver qué hay en el part
            logger.debug(f"Part type: {type(part)}")
            logger.debug(f"Part attributes: {dir(part)}")

            if hasattr(part, 'inline_data') and part.inline_data:
                audio_data = part.inline_data.data
                mime_type = part.inline_data.mime_type if hasattr(part.inline_data, 'mime_type') else 'unknown'
                logger.info(f"Audio MIME type: {mime_type}")
            else:
                logger.warning("No se encontró inline_data en el part")
                return None

            if not audio_data:
                logger.warning("No se encontró audio en la respuesta")
                return None

            logger.info(f"Audio generado exitosamente (tamaño: {len(audio_data)} bytes)")

            # Guardar audio en disco si está habilitado
            if save_to_disk:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                # Determinar extensión basada en MIME type
                extension = "wav"  # Por defecto
                if mime_type == "audio/mp3":
                    extension = "mp3"
                elif mime_type == "audio/wav":
                    extension = "wav"
                elif mime_type == "audio/ogg":
                    extension = "ogg"

                filename = f"audio_{timestamp}_{self.speaker}.{extension}"
                filepath = os.path.join(self.audio_dir, filename)

                with open(filepath, 'wb') as f:
                    f.write(audio_data)

                logger.info(f"Audio guardado en: {filepath}")

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
