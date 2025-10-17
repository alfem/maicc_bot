"""
Cliente para interactuar con la API de Google Gemini.
"""
import google.generativeai as genai
from typing import List, Dict, Optional
from logger_config import get_logger

# Logger específico para LLM
logger = get_logger('llm')


class LLMClient:
    """Cliente para hacer llamadas a la API de LLM."""

    def __init__(self, api_key: str, model: str, max_tokens: int = 1024,
                 temperature: float = 0.7, system_prompt: str = "",
                 api_url: str = ""):
        """
        Inicializa el cliente del LLM.

        Args:
            api_key: Clave de API de Google Gemini
            model: Nombre del modelo a usar (ej: gemini-2.0-flash-exp)
            max_tokens: Número máximo de tokens en la respuesta
            temperature: Temperatura para la generación
            system_prompt: Prompt del sistema que define el comportamiento del asistente
            api_url: No usado para Gemini (mantenido por compatibilidad)
        """
        logger.info(f"Inicializando LLMClient con modelo: {model}")
        logger.debug(f"Configuración - max_tokens: {max_tokens}, temperature: {temperature}")

        # Configurar API key
        genai.configure(api_key=api_key)

        # Configurar generación
        self.generation_config = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }

        # Crear modelo con system instruction
        self.model = genai.GenerativeModel(
            model_name=model,
            generation_config=self.generation_config,
            system_instruction=system_prompt if system_prompt else None
        )

        self.system_prompt = system_prompt
        self.base_model_name = model
        self.api_key = api_key

        logger.info("LLMClient inicializado correctamente")

    def update_system_prompt(self, additional_context: str = ""):
        """
        Actualiza el system prompt del modelo con contexto adicional.

        Args:
            additional_context: Texto adicional para agregar al system prompt
        """
        logger.debug("Actualizando system prompt con contexto adicional")

        full_prompt = self.system_prompt
        if additional_context:
            full_prompt += "\n" + additional_context
            logger.debug(f"Contexto adicional agregado (longitud: {len(additional_context)} caracteres)")

        # Recrear el modelo con el nuevo system instruction
        self.model = genai.GenerativeModel(
            model_name=self.base_model_name,
            generation_config=self.generation_config,
            system_instruction=full_prompt if full_prompt else None
        )

    def get_response(self, messages: List[Dict[str, str]], mood_context: str = "") -> str:
        """
        Obtiene una respuesta del LLM basada en el historial de mensajes.

        Args:
            messages: Lista de mensajes en formato [{"role": "user/assistant", "content": "..."}]
            mood_context: Contexto adicional sobre el estado de ánimo (opcional)

        Returns:
            Respuesta generada por el LLM
        """
        try:
            logger.info(f"Solicitando respuesta del LLM (mensajes en contexto: {len(messages)})")

            # Actualizar el system prompt si hay contexto de mood
            if mood_context:
                logger.debug("Incluyendo contexto de mood en la solicitud")
                self.update_system_prompt(mood_context)

            # Convertir formato de mensajes a formato Gemini
            # Gemini usa 'user' y 'model' en lugar de 'user' y 'assistant'
            history = []
            for msg in messages[:-1]:  # Todos menos el último
                role = "user" if msg["role"] == "user" else "model"
                history.append({
                    "role": role,
                    "parts": [msg["content"]]
                })

            logger.debug(f"Historial convertido: {len(history)} mensajes")

            # Crear chat con historial
            chat = self.model.start_chat(history=history)

            # Enviar el último mensaje
            last_message = messages[-1]["content"] if messages else ""
            logger.debug(f"Enviando mensaje al LLM: '{last_message[:50]}...'")

            response = chat.send_message(last_message)

            logger.info(f"Respuesta recibida del LLM (longitud: {len(response.text)} caracteres)")
            return response.text

        except Exception as e:
            logger.error(f"Error al comunicarse con la API de Gemini: {e}", exc_info=True)
            return "Disculpa, hubo un problema al comunicarme con el servicio. ¿Podrías intentarlo de nuevo?"

    def chat(self, user_message: str, context: List[Dict[str, str]] = None) -> str:
        """
        Método simplificado para chatear con el LLM.

        Args:
            user_message: Mensaje del usuario
            context: Contexto previo de la conversación (opcional)

        Returns:
            Respuesta del asistente
        """
        logger.debug(f"Método chat llamado con mensaje: '{user_message[:50]}...'")
        messages = context.copy() if context else []
        messages.append({"role": "user", "content": user_message})

        return self.get_response(messages)
