#!/bin/bash
set -e

echo "▶ Iniciando Gestor Jurídico..."
docker compose up --build "$@"
