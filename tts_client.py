"""
Cliente para generación de voz usando la API de Google Gemini.
"""
from google import genai
from google.genai import types
from typing import Optional
from logger_config import get_logger
import os
import wave
from datetime import datetime

# Logger específico para TTS
logger = get_logger('llm')  # Usamos el mismo logger que LLM


def save_wave_file(filename: str, pcm_data: bytes, channels: int = 1,
                   rate: int = 24000, sample_width: int = 2):
    """
    Guarda datos PCM en un archivo WAV con los headers correctos.

    Args:
        filename: Ruta del archivo a guardar
        pcm_data: Datos de audio en formato PCM
        channels: Número de canales (1 para mono, 2 para estéreo)
        rate: Frecuencia de muestreo en Hz (default: 24000)
        sample_width: Ancho de muestra en bytes (default: 2 para 16-bit)
    """
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm_data)


class TTSClient:
    """Cliente para generar audio de voz usando Google Gemini."""

    def __init__(self, api_key: str, model: str, speaker: str = "Leda",
                 preamble: str = "", temperature: float = 0.5,
                 audio_dir: str = "./audio_outputs"):
        """
        Inicializa el cliente de Text-to-Speech.

        Args:
            api_key: Clave de API de Google Gemini
            model: Nombre del modelo a usar (ej: gemini-2.5-flash-preview-tts)
            speaker: Nombre del speaker/voz a usar (30 voces disponibles)
            preamble: Texto para añadir antes del contenido a convertir
            temperature: Temperatura para control de variación (0.0-1.0, default: 0.5)
            audio_dir: Directorio donde guardar los audios generados
        """
        logger.info(f"Inicializando TTSClient con modelo: {model}, speaker: {speaker}, temperature: {temperature}")

        # Configurar cliente con API key
        self.client = genai.Client(api_key=api_key)

        self.model_name = model
        self.speaker = speaker
        self.preamble = preamble
        self.temperature = temperature
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
            logger.info("="*80)
            logger.info("GENERACIÓN DE VOZ TTS - INICIO")
            logger.info("="*80)

            # Registrar todos los parámetros de generación
            logger.info(f"Parámetros de generación de voz:")
            logger.info(f"  - Modelo: {self.model_name}")
            logger.info(f"  - Speaker/Voz: {self.speaker}")
            logger.info(f"  - Temperature: {self.temperature}")
            logger.info(f"  - Preámbulo: '{self.preamble}'")
            logger.info(f"  - Longitud del texto original: {len(text)} caracteres")

            # Preparar el texto con el preámbulo
            full_text = self.preamble + text if self.preamble else text
            logger.info(f"  - Longitud del texto completo (con preámbulo): {len(full_text)} caracteres")
            logger.info(f"Texto original: '{text[:200]}{'...' if len(text) > 200 else ''}'")
            if self.preamble:
                logger.info(f"Texto completo (con preámbulo): '{full_text[:200]}{'...' if len(full_text) > 200 else ''}'")

            logger.info("Llamando a la API de Gemini para generar audio...")

            # Generar el contenido con speech usando la nueva API
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_text,
                config=types.GenerateContentConfig(
                    temperature=self.temperature,
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
                logger.info("="*80)
                return None

            logger.info(f"✅ Audio generado exitosamente")
            logger.info(f"  - Tamaño del audio: {len(audio_data)} bytes")

            # Guardar audio en disco si está habilitado
            if save_to_disk:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"audio_{timestamp}_{self.speaker}.wav"
                filepath = os.path.join(self.audio_dir, filename)

                # Guardar como WAV con headers correctos
                # Los datos vienen como PCM raw a 24kHz, mono, 16-bit
                save_wave_file(filepath, audio_data, channels=1, rate=24000, sample_width=2)

                logger.info(f"  - Audio guardado en: {filepath}")

            logger.info("="*80)
            logger.info("GENERACIÓN DE VOZ TTS - FIN EXITOSO")
            logger.info("="*80)

            return audio_data

        except Exception as e:
            logger.error("="*80)
            logger.error("GENERACIÓN DE VOZ TTS - ERROR")
            logger.error("="*80)
            logger.error(f"Error al generar audio con la API de Gemini: {e}", exc_info=True)
            logger.error("="*80)
            return None

    def update_speaker(self, speaker: str):
        """
        Actualiza el speaker/voz a utilizar.

        Args:
            speaker: Nombre del nuevo speaker
        """
        logger.info(f"🔄 Actualizando speaker de '{self.speaker}' a '{speaker}'")
        self.speaker = speaker

    def update_preamble(self, preamble: str):
        """
        Actualiza el preámbulo a utilizar.

        Args:
            preamble: Nuevo texto de preámbulo
        """
        logger.info(f"🔄 Actualizando preámbulo de '{self.preamble}' a '{preamble}'")
        self.preamble = preamble

    def update_temperature(self, temperature: float):
        """
        Actualiza la temperatura de generación.

        Args:
            temperature: Nueva temperatura (0.0-1.0)
        """
        logger.info(f"🔄 Actualizando temperatura de {self.temperature} a {temperature}")
        self.temperature = temperature

    def pcm_to_wav(self, pcm_data: bytes, channels: int = 1,
                   rate: int = 24000, sample_width: int = 2) -> bytes:
        """
        Convierte datos PCM raw a formato WAV con headers.

        Args:
            pcm_data: Datos de audio en formato PCM
            channels: Número de canales (1 para mono, 2 para estéreo)
            rate: Frecuencia de muestreo en Hz (default: 24000)
            sample_width: Ancho de muestra en bytes (default: 2 para 16-bit)

        Returns:
            Bytes del archivo WAV completo con headers
        """
        import io

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(rate)
            wf.writeframes(pcm_data)

        wav_buffer.seek(0)
        return wav_buffer.read()
