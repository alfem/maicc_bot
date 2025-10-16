# Bot Compañero para Telegram

Un bot de Telegram diseñado para actuar como compañero conversacional, especialmente orientado a personas mayores. El bot utiliza inteligencia artificial (Google Gemini 2.0 Flash) para mantener conversaciones naturales y empáticas, guardando el contexto de cada usuario de forma separada.

## Características

- **Conversaciones personalizadas**: Cada usuario tiene su propio contexto de conversación que se mantiene entre sesiones
- **IA conversacional**: Utiliza Google Gemini 2.0 Flash para generar respuestas naturales y empáticas
- **Mensajes proactivos**: El bot inicia conversaciones cuando el usuario lleva tiempo sin escribir
- **Noticias RSS**: Consulta feeds RSS diariamente y las usa para iniciar conversaciones sobre temas actuales
- **Retrasos humanos**: Simula tiempo de escritura variable según la longitud de la respuesta
- **Almacenamiento persistente**: Todas las conversaciones se guardan en archivos JSON
- **Interfaz web**: Panel de administración para consultar y revisar conversaciones
- **Filtros por fecha**: Posibilidad de filtrar conversaciones por rangos de fechas
- **Configuración flexible**: Toda la configuración se gestiona desde un archivo JSON

## Estructura del Proyecto

```
.
├── telegram_bot.py           # Bot principal de Telegram
├── web_interface.py          # Interfaz web para administración
├── conversation_manager.py   # Gestión de conversaciones
├── llm_client.py            # Cliente para la API de Google Gemini
├── news_manager.py          # Gestor de feeds RSS y noticias
├── config.json              # Archivo de configuración
├── requirements.txt         # Dependencias de Python
├── templates/               # Plantillas HTML
│   ├── login.html
│   ├── index.html
│   └── conversation.html
├── conversations/           # Directorio de conversaciones (se crea automáticamente)
└── news_cache.json          # Caché de noticias (se crea automáticamente)
```

## Instalación

### 1. Requisitos previos

- Python 3.8 o superior
- Una cuenta de Telegram y un bot token (obtener de @BotFather)
- Una API key de Google AI Studio (obtener de https://aistudio.google.com/app/apikey)

### 2. Clonar o descargar el proyecto

```bash
cd agentrouter
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar el bot

Edita el archivo `config.json` con tus credenciales:

```json
{
  "telegram": {
    "bot_token": "TU_TOKEN_DE_TELEGRAM_AQUI",
    "allowed_users": []
  },
  "llm": {
    "api_url": "",
    "api_key": "TU_API_KEY_DE_GEMINI_AQUI",
    "model": "gemini-2.0-flash-exp",
    "max_tokens": 8192,
    "temperature": 0.7,
    "system_prompt": "Eres un compañero amigable y empático..."
  },
  "storage": {
    "conversations_dir": "./conversations",
    "max_context_messages": 20
  },
  "proactive": {
    "enabled": true,
    "inactivity_minutes": 60,
    "check_interval_minutes": 15
  },
  "news": {
    "rss_feeds": [
      "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada",
      "https://www.elmundo.es/rss/portada.xml"
    ],
    "cache_file": "./news_cache.json"
  },
  "web": {
    "host": "0.0.0.0",
    "port": 8080,
    "admin_password": "cambiar_password"
  }
}
```

**Importante**:
- Obtén tu bot token hablando con @BotFather en Telegram
- Obtén tu API key de Google Gemini en https://aistudio.google.com/app/apikey
- Cambia el `admin_password` por una contraseña segura

## Uso

### Iniciar el bot de Telegram

```bash
python telegram_bot.py
```

El bot estará disponible en Telegram. Los usuarios pueden:
- `/start` - Iniciar el bot y ver mensaje de bienvenida
- `/help` - Ver ayuda y comandos disponibles
- `/reset` - Borrar el historial y empezar una nueva conversación
- Enviar cualquier mensaje para conversar

### Iniciar la interfaz web

En otra terminal:

```bash
python web_interface.py
```

La interfaz estará disponible en `http://localhost:8080`

Credenciales por defecto:
- Usuario: admin
- Contraseña: (la que configuraste en `config.json`)

## Interfaz Web

La interfaz web permite:

1. **Ver lista de usuarios**: Muestra todos los usuarios que han interactuado con el bot
2. **Ver conversaciones**: Accede al historial completo de conversación de cada usuario
3. **Filtrar por fechas**: Consulta conversaciones en rangos de fechas específicos
4. **Estadísticas**: Número de mensajes, última actividad, etc.

## Personalización

### Modificar el comportamiento del bot

Edita el `system_prompt` en `config.json` para cambiar la personalidad y comportamiento del bot:

```json
"system_prompt": "Eres un compañero amigable y empático para personas mayores..."
```

### Ajustar el contexto

Modifica `max_context_messages` para controlar cuántos mensajes se envían como contexto al LLM:

```json
"max_context_messages": 20
```

### Cambiar el modelo de IA

Puedes usar diferentes modelos de Gemini modificando:

```json
"model": "gemini-2.0-flash-exp"
```

Modelos disponibles de Google Gemini:
- `gemini-2.0-flash-exp` (recomendado, experimental, última versión)
- `gemini-1.5-pro` (alta calidad, contexto largo)
- `gemini-1.5-flash` (rápido y eficiente)
- `gemini-1.0-pro` (modelo estable)

### Configurar mensajes proactivos

El bot puede enviar mensajes automáticamente cuando un usuario lleva tiempo sin escribir:

```json
"proactive": {
  "enabled": true,
  "inactivity_minutes": 60,
  "check_interval_minutes": 15,
  "quiet_hours": {
    "enabled": true,
    "start": "22:00",
    "end": "09:00"
  }
}
```

- `enabled`: Activa o desactiva los mensajes proactivos
- `inactivity_minutes`: Tiempo de inactividad (en minutos) antes de enviar un mensaje
- `check_interval_minutes`: Frecuencia con la que se verifica la inactividad
- `quiet_hours`: Horario de "no molestar" durante la noche
  - `enabled`: Activa o desactiva el horario de no molestar
  - `start`: Hora de inicio (formato 24h: "HH:MM")
  - `end`: Hora de fin (formato 24h: "HH:MM")

**Ejemplo**: Con la configuración por defecto:
- El bot verificará cada 15 minutos si hay usuarios inactivos
- Si encuentra un usuario que no ha escrito en 60 minutos, le enviará un mensaje proactivo
- NO enviará mensajes entre las 22:00 y las 09:00 (horario de descanso)
- El horario de "no molestar" funciona correctamente aunque cruce la medianoche

### Configurar noticias RSS

El bot puede consultar noticias de feeds RSS y usarlas para iniciar conversaciones:

```json
"news": {
  "rss_feeds": [
    "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada",
    "https://www.elmundo.es/rss/portada.xml",
    "https://www.bbc.com/mundo/topics/cyx5krnw38vt/rss.xml"
  ],
  "cache_file": "./news_cache.json"
}
```

- `rss_feeds`: Lista de URLs de feeds RSS para consultar (puedes agregar todos los que quieras)
- `cache_file`: Archivo donde se guardan las noticias (opcional, por defecto `./news_cache.json`)

**Cómo funciona**:
1. El bot consulta los feeds RSS **una vez al día** automáticamente
2. Guarda las 10 noticias más recientes de cada feed en caché
3. Cuando envía un mensaje proactivo, tiene **50% de probabilidad** de usar una noticia aleatoria
4. El LLM comenta la noticia de forma natural, no la copia literalmente

**Ejemplos de feeds RSS en español**:
- El País: `https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada`
- El Mundo: `https://www.elmundo.es/rss/portada.xml`
- BBC Mundo: `https://www.bbc.com/mundo/topics/cyx5krnw38vt/rss.xml`
- 20 Minutos: `https://www.20minutos.es/rss/`

## Estructura de Datos

Las conversaciones se almacenan en archivos JSON individuales por usuario:

```json
{
  "user_id": 123456789,
  "username": "usuario_telegram",
  "first_name": "Juan",
  "created_at": "2025-01-15T10:30:00",
  "messages": [
    {
      "role": "user",
      "content": "Hola, ¿cómo estás?",
      "timestamp": "2025-01-15T10:30:00"
    },
    {
      "role": "assistant",
      "content": "¡Hola! Estoy muy bien, gracias...",
      "timestamp": "2025-01-15T10:30:05"
    }
  ]
}
```

## Seguridad

- La interfaz web está protegida por contraseña
- Las conversaciones se almacenan localmente
- Cambia la contraseña por defecto en `config.json`
- No compartas tu API key de Google Gemini
- No compartas tu bot token de Telegram

## Consideraciones de Costos

Google Gemini tiene un tier gratuito generoso:
- **Gemini 2.0 Flash**: 10 RPM gratuito, 1500 RPD
- **Gemini 1.5 Flash**: 15 RPM gratuito, 1500 RPD
- **Gemini 1.5 Pro**: 2 RPM gratuito, 50 RPD

Para mayor uso, consulta https://ai.google.dev/pricing

## Solución de Problemas

### El bot no responde

- Verifica que el token de Telegram sea correcto
- Comprueba que el bot esté corriendo (`python telegram_bot.py`)
- Revisa los logs en la consola

### Error de API

- Verifica que tu API key de Google Gemini sea válida
- Obtén una nueva key en https://aistudio.google.com/app/apikey
- Comprueba que tengas acceso al modelo especificado
- Revisa los logs en la consola para más detalles

### La interfaz web no se ve correctamente

- Verifica que Flask esté instalado correctamente
- Comprueba que el puerto 8080 no esté en uso
- Intenta acceder desde `http://localhost:8080`

## Licencia

Este proyecto es de código abierto y está disponible para uso personal y educativo.

## Soporte

Para reportar problemas o sugerencias, crea un issue en el repositorio del proyecto.
