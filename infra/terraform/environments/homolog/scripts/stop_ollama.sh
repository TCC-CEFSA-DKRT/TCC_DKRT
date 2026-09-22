#!/bin/bash
# Contraparte de start_ollama.sh -- desliga a instância Ollama. Rodar
# sempre ao final de uma sessão de uso/experimento (Fase 10) para não
# consumir custo desnecessário.
set -euo pipefail

INSTANCE_ID="${1:?Uso: stop_ollama.sh <instance-id> (ver: terraform output -raw ollama_instance_id)}"

aws ec2 stop-instances --instance-ids "$INSTANCE_ID"
echo "Aguardando a instância $INSTANCE_ID ficar 'stopped'..."
aws ec2 wait instance-stopped --instance-ids "$INSTANCE_ID"
echo "Ollama desligado."
