"""
Cliente para interactuar con la API de Google Gemini.
"""
from google import genai
from google.genai import types
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

        # Crear cliente con API key
        self.client = genai.Client(api_key=api_key)

        # Guardar configuración
        self.temperature = temperature
        self.max_tokens = max_tokens
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

        # Solo guardamos el contexto adicional para usarlo en get_response
        if additional_context:
            self.current_additional_context = additional_context
            logger.debug(f"Contexto adicional agregado (longitud: {len(additional_context)} caracteres)")
        else:
            self.current_additional_context = ""

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

            # Preparar system instruction completo
            system_instruction = self.system_prompt
            if hasattr(self, 'current_additional_context') and self.current_additional_context:
                system_instruction += "\n" + self.current_additional_context

            # Log del system prompt utilizado
            logger.debug(f"System prompt base (longitud: {len(self.system_prompt)} caracteres): '{self.system_prompt[:150]}...'")
            if hasattr(self, 'current_additional_context') and self.current_additional_context:
                logger.debug(f"Contexto adicional (longitud: {len(self.current_additional_context)} caracteres): '{self.current_additional_context[:150]}...'")
            logger.debug(f"System instruction completo (longitud: {len(system_instruction) if system_instruction else 0} caracteres)")

            # Convertir formato de mensajes a formato Gemini
            # Gemini usa 'user' y 'model' en lugar de 'user' y 'assistant'
            contents = []
            for msg in messages:
                role = "user" if msg["role"] == "user" else "model"
                contents.append(types.Content(
                    role=role,
                    parts=[types.Part(text=msg["content"])]
                ))

            logger.debug(f"Historial convertido: {len(contents)} mensajes")

            # Configurar la generación
            config = types.GenerateContentConfig(
                temperature=self.temperature,
                max_output_tokens=self.max_tokens,
                system_instruction=system_instruction if system_instruction else None
            )

            # Generar respuesta
            response = self.client.models.generate_content(
                model=self.base_model_name,
                contents=contents,
                config=config
            )

            response_text = response.text
            logger.info(f"Respuesta recibida del LLM (longitud: {len(response_text)} caracteres)")
            return response_text

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
