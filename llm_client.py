"""
Cliente para interactuar con APIs de LLM (Google Gemini y OpenAI).
"""
from typing import List, Dict, Optional
from logger_config import get_logger

# Logger específico para LLM
logger = get_logger('llm')


class BaseLLMClient:
    """Clase base para clientes LLM."""

    def __init__(self, api_key: str, model: str, max_tokens: int = 1024,
                 temperature: float = 0.7, system_prompt: str = ""):
        """
        Inicializa el cliente base del LLM.

        Args:
            api_key: Clave de API
            model: Nombre del modelo a usar
            max_tokens: Número máximo de tokens en la respuesta
            temperature: Temperatura para la generación
            system_prompt: Prompt del sistema que define el comportamiento del asistente
        """
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.system_prompt = system_prompt
        self.current_additional_context = ""

    def update_system_prompt(self, additional_context: str = ""):
        """
        Actualiza el system prompt del modelo con contexto adicional.

        Args:
            additional_context: Texto adicional para agregar al system prompt
        """
        logger.debug("Actualizando system prompt con contexto adicional")

        if additional_context:
            self.current_additional_context = additional_context
            logger.debug(f"Contexto adicional agregado (longitud: {len(additional_context)} caracteres)")
        else:
            self.current_additional_context = ""

    def get_response(self, messages: List[Dict[str, str]], mood_context: str = "") -> str:
        """
        Obtiene una respuesta del LLM basada en el historial de mensajes.
        Debe ser implementado por las subclases.

        Args:
            messages: Lista de mensajes en formato [{"role": "user/assistant", "content": "..."}]
            mood_context: Contexto adicional sobre el estado de ánimo (opcional)

        Returns:
            Respuesta generada por el LLM
        """
        raise NotImplementedError("Subclasses must implement get_response()")

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


class GeminiLLMClient(BaseLLMClient):
    """Cliente para hacer llamadas a la API de Google Gemini."""

    def __init__(self, api_key: str, model: str, max_tokens: int = 1024,
                 temperature: float = 0.7, system_prompt: str = "",
                 api_url: str = ""):
        """
        Inicializa el cliente de Google Gemini.

        Args:
            api_key: Clave de API de Google Gemini
            model: Nombre del modelo a usar (ej: gemini-2.0-flash-exp)
            max_tokens: Número máximo de tokens en la respuesta
            temperature: Temperatura para la generación
            system_prompt: Prompt del sistema que define el comportamiento del asistente
            api_url: No usado para Gemini (mantenido por compatibilidad)
        """
        super().__init__(api_key, model, max_tokens, temperature, system_prompt)

        logger.info(f"Inicializando GeminiLLMClient con modelo: {model}")
        logger.debug(f"Configuración - max_tokens: {max_tokens}, temperature: {temperature}")

        # Crear cliente con API key
        from google import genai
        from google.genai import types

        self.client = genai.Client(api_key=api_key)
        self.types = types
        self.base_model_name = model

        logger.info("GeminiLLMClient inicializado correctamente")

    def get_response(self, messages: List[Dict[str, str]], mood_context: str = "") -> str:
        """
        Obtiene una respuesta de Google Gemini basada en el historial de mensajes.

        Args:
            messages: Lista de mensajes en formato [{"role": "user/assistant", "content": "..."}]
            mood_context: Contexto adicional sobre el estado de ánimo (opcional)

        Returns:
            Respuesta generada por el LLM
        """
        try:
            logger.info(f"Solicitando respuesta de Gemini (mensajes en contexto: {len(messages)})")

            # Actualizar el system prompt si hay contexto de mood
            if mood_context:
                logger.debug("Incluyendo contexto de mood en la solicitud")
                self.update_system_prompt(mood_context)

            # Preparar system instruction completo
            system_instruction = self.system_prompt
            if self.current_additional_context:
                system_instruction += "\n" + self.current_additional_context

            # Log del system prompt utilizado
            logger.debug(f"System prompt base (longitud: {len(self.system_prompt)} caracteres): '{self.system_prompt[:150]}...'")
            if self.current_additional_context:
                logger.debug(f"Contexto adicional (longitud: {len(self.current_additional_context)} caracteres): '{self.current_additional_context[:150]}...'")
            logger.debug(f"System instruction completo (longitud: {len(system_instruction) if system_instruction else 0} caracteres)")

            # Convertir formato de mensajes a formato Gemini
            # Gemini usa 'user' y 'model' en lugar de 'user' y 'assistant'
            contents = []
            for msg in messages:
                role = "user" if msg["role"] == "user" else "model"
                contents.append(self.types.Content(
                    role=role,
                    parts=[self.types.Part(text=msg["content"])]
                ))

            logger.debug(f"Historial convertido: {len(contents)} mensajes")

            # Configurar la generación
            config = self.types.GenerateContentConfig(
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
            logger.info(f"Respuesta recibida de Gemini (longitud: {len(response_text)} caracteres)")
            return response_text

        except Exception as e:
            logger.error(f"Error al comunicarse con la API de Gemini: {e}", exc_info=True)
            return "Disculpa, hubo un problema al comunicarme con el servicio. ¿Podrías intentarlo de nuevo?"


class OpenAILLMClient(BaseLLMClient):
    """Cliente para hacer llamadas a la API de OpenAI."""

    def __init__(self, api_key: str, model: str, max_tokens: int = 1024,
                 temperature: float = 0.7, system_prompt: str = "",
                 base_url: str = ""):
        """
        Inicializa el cliente de OpenAI.

        Args:
            api_key: Clave de API de OpenAI
            model: Nombre del modelo a usar (ej: gpt-4o-mini, gpt-4o, gpt-3.5-turbo)
            max_tokens: Número máximo de tokens en la respuesta
            temperature: Temperatura para la generación
            system_prompt: Prompt del sistema que define el comportamiento del asistente
            base_url: URL base opcional para endpoints personalizados
        """
        super().__init__(api_key, model, max_tokens, temperature, system_prompt)

        logger.info(f"Inicializando OpenAILLMClient con modelo: {model}")
        logger.debug(f"Configuración - max_tokens: {max_tokens}, temperature: {temperature}")

        # Crear cliente de OpenAI
        from openai import OpenAI

        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
            logger.info(f"Usando base_url personalizada: {base_url}")

        self.client = OpenAI(**client_kwargs)

        logger.info("OpenAILLMClient inicializado correctamente")

    def get_response(self, messages: List[Dict[str, str]], mood_context: str = "") -> str:
        """
        Obtiene una respuesta de OpenAI basada en el historial de mensajes.

        Args:
            messages: Lista de mensajes en formato [{"role": "user/assistant", "content": "..."}]
            mood_context: Contexto adicional sobre el estado de ánimo (opcional)

        Returns:
            Respuesta generada por el LLM
        """
        try:
            logger.info(f"Solicitando respuesta de OpenAI (mensajes en contexto: {len(messages)})")

            # Actualizar el system prompt si hay contexto de mood
            if mood_context:
                logger.debug("Incluyendo contexto de mood en la solicitud")
                self.update_system_prompt(mood_context)

            # Preparar system instruction completo
            system_instruction = self.system_prompt
            if self.current_additional_context:
                system_instruction += "\n" + self.current_additional_context

            # Log del system prompt utilizado
            logger.debug(f"System prompt base (longitud: {len(self.system_prompt)} caracteres): '{self.system_prompt[:150]}...'")
            if self.current_additional_context:
                logger.debug(f"Contexto adicional (longitud: {len(self.current_additional_context)} caracteres): '{self.current_additional_context[:150]}...'")
            logger.debug(f"System instruction completo (longitud: {len(system_instruction) if system_instruction else 0} caracteres)")

            # Preparar mensajes para OpenAI (incluir system prompt como primer mensaje)
            api_messages = []
            if system_instruction:
                api_messages.append({"role": "system", "content": system_instruction})

            # Añadir mensajes de conversación
            api_messages.extend(messages)

            logger.debug(f"Total de mensajes enviados a OpenAI: {len(api_messages)}")

            # Llamar a la API de OpenAI
            response = self.client.chat.completions.create(
                model=self.model,
                messages=api_messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )

            response_text = response.choices[0].message.content
            logger.info(f"Respuesta recibida de OpenAI (longitud: {len(response_text)} caracteres)")
            logger.debug(f"Uso de tokens - prompt: {response.usage.prompt_tokens}, completion: {response.usage.completion_tokens}, total: {response.usage.total_tokens}")

            return response_text

        except Exception as e:
            logger.error(f"Error al comunicarse con la API de OpenAI: {e}", exc_info=True)
            return "Disculpa, hubo un problema al comunicarme con el servicio. ¿Podrías intentarlo de nuevo?"


def create_llm_client(provider: str, config: Dict) -> BaseLLMClient:
    """
    Función factory para crear un cliente LLM según el proveedor especificado.

    Args:
        provider: Nombre del proveedor ("gemini" o "openai")
        config: Diccionario con la configuración completa del LLM

    Returns:
        Instancia del cliente LLM apropiado

    Raises:
        ValueError: Si el proveedor no es soportado
    """
    provider = provider.lower()

    # Parámetros comunes
    max_tokens = config.get("max_tokens", 1024)
    temperature = config.get("temperature", 0.7)
    system_prompt = config.get("system_prompt", "")

    if provider == "gemini":
        gemini_config = config.get("gemini", {})
        return GeminiLLMClient(
            api_key=gemini_config.get("api_key", ""),
            model=gemini_config.get("model", "gemini-2.0-flash-exp"),
            max_tokens=max_tokens,
            temperature=temperature,
            system_prompt=system_prompt,
            api_url=""
        )
    elif provider == "openai":
        openai_config = config.get("openai", {})
        return OpenAILLMClient(
            api_key=openai_config.get("api_key", ""),
            model=openai_config.get("model", "gpt-4o-mini"),
            max_tokens=max_tokens,
            temperature=temperature,
            system_prompt=system_prompt,
            base_url=openai_config.get("base_url", "")
        )
    else:
        raise ValueError(f"Proveedor LLM no soportado: {provider}. Use 'gemini' o 'openai'.")


# Mantener compatibilidad con código existente que usa LLMClient directamente
# Esta clase actúa como alias de GeminiLLMClient para compatibilidad
LLMClient = GeminiLLMClient
