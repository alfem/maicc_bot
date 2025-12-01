"""
Cliente para generación de voz usando la API de Eleven Labs.
"""
import requests
from typing import Optional
from logger_config import get_logger
import os
from datetime import datetime

# Logger específico para TTS
logger = get_logger('llm')


class ElevenLabsTTSClient:
    """Cliente para generar audio de voz usando Eleven Labs."""

    def __init__(self, api_key: str, voice_id: str = "21m00Tcm4TlvDq8ikWAM",
                 model_id: str = "eleven_multilingual_v2",
                 stability: float = 0.5, similarity_boost: float = 0.75,
                 style: float = 0.0, use_speaker_boost: bool = True,
                 audio_dir: str = "./audio_outputs"):
        """
        Inicializa el cliente de Text-to-Speech de Eleven Labs.

        Args:
            api_key: Clave de API de Eleven Labs
            voice_id: ID de la voz a usar (default: Rachel - 21m00Tcm4TlvDq8ikWAM)
            model_id: ID del modelo a usar (default: eleven_multilingual_v2)
            stability: Estabilidad de la voz (0.0-1.0)
            similarity_boost: Boost de similitud (0.0-1.0)
            style: Estilo/expresividad (0.0-1.0, solo para v2 models)
            use_speaker_boost: Activar speaker boost para mejorar la similitud
            audio_dir: Directorio donde guardar los audios generados
        """
        logger.info(f"Inicializando ElevenLabsTTSClient con voice_id: {voice_id}, model: {model_id}")

        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id
        self.stability = stability
        self.similarity_boost = similarity_boost
        self.style = style
        self.use_speaker_boost = use_speaker_boost
        self.audio_dir = audio_dir

        # URL base de la API
        self.base_url = "https://api.elevenlabs.io/v1"

        # Crear directorio de audios si no existe
        if not os.path.exists(audio_dir):
            os.makedirs(audio_dir)
            logger.info(f"Directorio de audios creado: {audio_dir}")

        logger.info("ElevenLabsTTSClient inicializado correctamente")

    def generate_audio(self, text: str, save_to_disk: bool = True) -> Optional[bytes]:
        """
        Genera audio de voz a partir de texto usando Eleven Labs.

        Args:
            text: Texto a convertir en voz
            save_to_disk: Si es True, guarda el audio en disco para depuración

        Returns:
            Bytes del archivo de audio en formato MP3, o None si hay error
        """
        try:
            logger.info("="*80)
            logger.info("GENERACIÓN DE VOZ TTS (ELEVEN LABS) - INICIO")
            logger.info("="*80)

            # Registrar todos los parámetros de generación
            logger.info(f"Parámetros de generación de voz:")
            logger.info(f"  - Voice ID: {self.voice_id}")
            logger.info(f"  - Model ID: {self.model_id}")
            logger.info(f"  - Stability: {self.stability}")
            logger.info(f"  - Similarity Boost: {self.similarity_boost}")
            logger.info(f"  - Style: {self.style}")
            logger.info(f"  - Speaker Boost: {self.use_speaker_boost}")
            logger.info(f"  - Longitud del texto: {len(text)} caracteres")
            logger.info(f"Texto: '{text[:200]}{'...' if len(text) > 200 else ''}'")

            # Preparar la URL del endpoint
            url = f"{self.base_url}/text-to-speech/{self.voice_id}"

            # Preparar headers
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": self.api_key
            }

            # Preparar el payload
            payload = {
                "text": text,
                "model_id": self.model_id,
                "voice_settings": {
                    "stability": self.stability,
                    "similarity_boost": self.similarity_boost,
                    "style": self.style,
                    "use_speaker_boost": self.use_speaker_boost
                }
            }

            logger.info("Llamando a la API de Eleven Labs para generar audio...")

            # Hacer la petición POST
            response = requests.post(url, json=payload, headers=headers)

            # Verificar que la petición fue exitosa
            if response.status_code != 200:
                logger.error(f"Error en la API de Eleven Labs: {response.status_code}")
                logger.error(f"Respuesta: {response.text}")
                return None

            audio_data = response.content

            if not audio_data:
                logger.warning("No se encontró audio en la respuesta")
                logger.info("="*80)
                return None

            logger.info(f"✅ Audio generado exitosamente")
            logger.info(f"  - Tamaño del audio: {len(audio_data)} bytes")
            logger.info(f"  - Formato: MP3")

            # Guardar audio en disco si está habilitado
            if save_to_disk:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"audio_elevenlabs_{timestamp}.mp3"
                filepath = os.path.join(self.audio_dir, filename)

                with open(filepath, 'wb') as f:
                    f.write(audio_data)

                logger.info(f"  - Audio guardado en: {filepath}")

            logger.info("="*80)
            logger.info("GENERACIÓN DE VOZ TTS (ELEVEN LABS) - FIN EXITOSO")
            logger.info("="*80)

            return audio_data

        except Exception as e:
            logger.error("="*80)
            logger.error("GENERACIÓN DE VOZ TTS (ELEVEN LABS) - ERROR")
            logger.error("="*80)
            logger.error(f"Error al generar audio con Eleven Labs: {e}", exc_info=True)
            logger.error("="*80)
            return None

    def update_voice(self, voice_id: str):
        """
        Actualiza la voz a utilizar.

        Args:
            voice_id: ID de la nueva voz
        """
        logger.info(f"🔄 Actualizando voice_id de '{self.voice_id}' a '{voice_id}'")
        self.voice_id = voice_id

    def update_model(self, model_id: str):
        """
        Actualiza el modelo a utilizar.

        Args:
            model_id: ID del nuevo modelo
        """
        logger.info(f"🔄 Actualizando model_id de '{self.model_id}' a '{model_id}'")
        self.model_id = model_id

    def update_voice_settings(self, stability: Optional[float] = None,
                             similarity_boost: Optional[float] = None,
                             style: Optional[float] = None,
                             use_speaker_boost: Optional[bool] = None):
        """
        Actualiza los parámetros de voz.

        Args:
            stability: Nueva estabilidad (0.0-1.0)
            similarity_boost: Nuevo boost de similitud (0.0-1.0)
            style: Nuevo estilo (0.0-1.0)
            use_speaker_boost: Nuevo valor de speaker boost
        """
        if stability is not None:
            logger.info(f"🔄 Actualizando stability de {self.stability} a {stability}")
            self.stability = stability
        if similarity_boost is not None:
            logger.info(f"🔄 Actualizando similarity_boost de {self.similarity_boost} a {similarity_boost}")
            self.similarity_boost = similarity_boost
        if style is not None:
            logger.info(f"🔄 Actualizando style de {self.style} a {style}")
            self.style = style
        if use_speaker_boost is not None:
            logger.info(f"🔄 Actualizando use_speaker_boost de {self.use_speaker_boost} a {use_speaker_boost}")
            self.use_speaker_boost = use_speaker_boost

    def get_available_voices(self) -> Optional[dict]:
        """
        Obtiene la lista de voces disponibles en la cuenta de Eleven Labs.

        Returns:
            Diccionario con las voces disponibles, o None si hay error
        """
        try:
            url = f"{self.base_url}/voices"
            headers = {
                "Accept": "application/json",
                "xi-api-key": self.api_key
            }

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                logger.error(f"Error al obtener voces: {response.status_code}")
                logger.error(f"Respuesta: {response.text}")
                return None

            voices_data = response.json()
            logger.info(f"Voces disponibles obtenidas: {len(voices_data.get('voices', []))} voces")

            return voices_data

        except Exception as e:
            logger.error(f"Error al obtener voces disponibles: {e}", exc_info=True)
            return None
