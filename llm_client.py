"""
Cliente para interactuar con la API de Google Gemini usando REST API.
Compatible con Python 3.7+
"""
import requests
import json
from typing import List, Dict, Optional


class LLMClient:
    """Cliente para hacer llamadas a la API de LLM usando REST."""

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
            api_url: URL base de la API (si está vacío, usa la URL por defecto de Gemini)
        """
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.system_prompt = system_prompt

        # URL base de la API de Gemini
        if api_url:
            self.base_url = api_url
        else:
            self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    def get_response(self, messages: List[Dict[str, str]]) -> str:
        """
        Obtiene una respuesta del LLM basada en el historial de mensajes.

        Args:
            messages: Lista de mensajes en formato [{"role": "user/assistant", "content": "..."}]

        Returns:
            Respuesta generada por el LLM
        """
        try:
            # Construir el contenido para la API de Gemini
            contents = []

            # Si hay system prompt, agregarlo como primer mensaje del usuario
            if self.system_prompt and (not messages or messages[0].get("role") != "system"):
                contents.append({
                    "role": "user",
                    "parts": [{"text": self.system_prompt}]
                })
                contents.append({
                    "role": "model",
                    "parts": [{"text": "Entendido. Actuaré según estas instrucciones."}]
                })

            # Convertir mensajes al formato de Gemini
            # Gemini usa 'user' y 'model' en lugar de 'user' y 'assistant'
            for msg in messages:
                if msg["role"] == "system":
                    # Ignorar mensajes de sistema adicionales, ya se manejó arriba
                    continue

                role = "user" if msg["role"] == "user" else "model"
                contents.append({
                    "role": role,
                    "parts": [{"text": msg["content"]}]
                })

            # Preparar la solicitud
            url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"

            payload = {
                "contents": contents,
                "generationConfig": {
                    "temperature": self.temperature,
                    "maxOutputTokens": self.max_tokens,
                }
            }

            # Si hay system prompt, agregarlo a systemInstruction
            if self.system_prompt:
                payload["systemInstruction"] = {
                    "parts": [{"text": self.system_prompt}]
                }

            # Hacer la solicitud
            headers = {"Content-Type": "application/json"}
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            # Extraer la respuesta
            result = response.json()

            if "candidates" in result and len(result["candidates"]) > 0:
                candidate = result["candidates"][0]
                if "content" in candidate and "parts" in candidate["content"]:
                    text_parts = [part.get("text", "") for part in candidate["content"]["parts"]]
                    return "".join(text_parts)

            return "Lo siento, no pude generar una respuesta. ¿Podrías intentarlo de nuevo?"

        except requests.exceptions.Timeout:
            print("Error: Timeout en la solicitud a la API")
            return "Disculpa, la solicitud tardó demasiado. ¿Podrías intentarlo de nuevo?"
        except requests.exceptions.RequestException as e:
            print(f"Error de API: {e}")
            return "Disculpa, hubo un problema al comunicarme con el servicio. ¿Podrías intentarlo de nuevo?"
        except Exception as e:
            print(f"Error inesperado: {e}")
            return "Disculpa, ocurrió un error inesperado. ¿Podrías intentarlo de nuevo?"

    def chat(self, user_message: str, context: List[Dict[str, str]] = None) -> str:
        """
        Método simplificado para chatear con el LLM.

        Args:
            user_message: Mensaje del usuario
            context: Contexto previo de la conversación (opcional)

        Returns:
            Respuesta del asistente
        """
        messages = context.copy() if context else []
        messages.append({"role": "user", "content": user_message})

        return self.get_response(messages)
