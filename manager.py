"""Entrada de desenvolvimento; usa a mesma aplicação da produção."""
import os
from app import app

if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG") == "1")
