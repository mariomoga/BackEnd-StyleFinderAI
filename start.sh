#!/bin/bash

# Script per avviare l'applicazione Flask

echo "🚀 Avvio StyleFinderAI Backend..."

# Verifica se esiste il virtual environment
if [ ! -d "venv" ]; then
    echo "📦 Creazione virtual environment..."
    python3 -m venv venv
fi

# Attiva il virtual environment
echo "🔧 Attivazione virtual environment..."
source venv/bin/activate

# Aggiorna pip
echo "⬆️  Aggiornamento pip..."
pip install --upgrade pip

# Installa/aggiorna le dipendenze
echo "📥 Installazione dipendenze..."
pip install -r requirements.txt

# Verifica che esista il file .env
if [ ! -f ".env" ]; then
    echo "⚠️  File .env non trovato!"
    echo "Copia .env.example in .env e configura le tue credenziali"
    cp .env.example .env
    echo "✅ File .env creato da .env.example"
    echo "⚠️  IMPORTANTE: Modifica il file .env con le tue credenziali prima di continuare!"
    exit 1
fi

# Avvia l'applicazione
echo "✨ Avvio applicazione Flask..."
python app.py
