#!/bin/bash

# Track-V Backend Setup Script

echo "🚀 Setting up Track-V Backend..."

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt

# Create directories
mkdir -p videos/junction_{1..4}
mkdir -p logs

# Copy environment template
if [ ! -f .env ]; then
    cp .env.example .env
    echo "⚠️  Please configure .env file with your Supabase and SMTP credentials"
fi

echo "✅ Backend setup complete!"
echo "📝 Next steps:"
echo "   1. Configure .env file"
echo "   2. Run database migrations: python -m scripts.01-create-database-schema"
echo "   3. Start server: python -m backend.main"
