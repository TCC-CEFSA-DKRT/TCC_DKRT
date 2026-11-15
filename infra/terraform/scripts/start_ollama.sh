#!/bin/bash
# Fase 9 (.cursor/specs/fase9.spec.md, secao 6 -- decisão Ollama-EC2) --
# liga a instância Ollama sob demanda. `aws_instance` do Terraform não tem
# um argumento de "estado desejado" (só existe/não existe); ligar/desligar é
# feito aqui, fora do apply/destroy, para que a instância NUNCA fique
# ligada por padrão (custo: g4dn.xlarge ~ USD 0,53/h on-demand em us-east-1,
# revisto pela adr-0015 -- era t3.large ~ USD 0,0832/h antes da GPU;
# consultar o preço atual antes de decidir quanto tempo deixar ligada,
# preços mudam).
set -euo pipefail

INSTANCE_ID="${1:?Uso: start_ollama.sh <instance-id> (ver: terraform output -raw ollama_instance_id)}"

aws ec2 start-instances --instance-ids "$INSTANCE_ID"
echo "Aguardando a instância $INSTANCE_ID ficar 'running'..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"

PRIVATE_IP=$(aws ec2 describe-instances \
  --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PrivateIpAddress' \
  --output text)

echo "Ollama ligado. IP privado: $PRIVATE_IP"
echo "Lembre-se de rodar stop_ollama.sh quando terminar -- a instância não desliga sozinha."
