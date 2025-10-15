#!/bin/bash

# Script para iniciar tanto el bot de Telegram como la interfaz web

echo "🚀 Iniciando Bot Compañero..."
echo ""

# Verificar que existe config.json
if [ ! -f "config.json" ]; then
    echo "❌ Error: No se encuentra config.json"
    echo "Por favor, copia config.json.example y configúralo con tus credenciales."
    exit 1
fi

# Verificar dependencias
echo "📦 Verificando dependencias..."
pip install -r requirements.txt --quiet

# Iniciar el bot de Telegram en segundo plano
echo "🤖 Iniciando bot de Telegram..."
python3 telegram_bot.py &
BOT_PID=$!

# Esperar un momento
sleep 2

# Iniciar la interfaz web
echo "🌐 Iniciando interfaz web..."
python3 web_interface.py &
WEB_PID=$!

echo ""
echo "✅ Servicios iniciados:"
echo "   - Bot de Telegram (PID: $BOT_PID)"
echo "   - Interfaz Web (PID: $WEB_PID)"
echo ""
echo "📱 El bot está disponible en Telegram"
echo "🌐 La interfaz web está en http://localhost:8080"
echo ""
echo "Para detener los servicios, presiona Ctrl+C"

# Función para limpiar al salir
cleanup() {
    echo ""
    echo "🛑 Deteniendo servicios..."
    kill $BOT_PID 2>/dev/null
    kill $WEB_PID 2>/dev/null
    echo "✅ Servicios detenidos"
    exit 0
}

# Capturar Ctrl+C
trap cleanup SIGINT SIGTERM

# Mantener el script corriendo
wait
