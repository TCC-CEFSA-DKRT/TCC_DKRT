#!/usr/bin/env bash
# Executa um comando numa instância EC2 via SSM Run Command e falha se o
# comando falhar. Uso: ssm_run.sh <instance-id> "<comando>"
set -euo pipefail

INSTANCE_ID="${1:?Uso: ssm_run.sh <instance-id> \"<comando>\"}"
COMMAND="${2:?Uso: ssm_run.sh <instance-id> \"<comando>\"}"

# A instância recém-criada pode levar alguns minutos para registrar o SSM Agent.
for _ in $(seq 1 30); do
  ONLINE="$(aws ssm describe-instance-information \
    --filters "Key=InstanceIds,Values=$INSTANCE_ID" \
    --query 'InstanceInformationList[0].PingStatus' --output text 2> /dev/null || true)"
  [ "$ONLINE" = "Online" ] && break
  sleep 10
done
[ "$ONLINE" = "Online" ] || { echo "Instância $INSTANCE_ID não está online no SSM" >&2; exit 1; }

COMMAND_ID="$(aws ssm send-command \
  --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --comment "pipeline ${GITHUB_RUN_ID:-manual}" \
  --timeout-seconds 900 \
  --parameters "$(jq -n --arg c "$COMMAND" '{commands: [$c]}')" \
  --query 'Command.CommandId' --output text)"

STATUS="InProgress"
while [ "$STATUS" = "Pending" ] || [ "$STATUS" = "InProgress" ] || [ "$STATUS" = "Delayed" ]; do
  sleep 5
  STATUS="$(aws ssm get-command-invocation --command-id "$COMMAND_ID" --instance-id "$INSTANCE_ID" \
    --query 'Status' --output text 2> /dev/null || echo InProgress)"
done

aws ssm get-command-invocation --command-id "$COMMAND_ID" --instance-id "$INSTANCE_ID" \
  --query '{stdout: StandardOutputContent, stderr: StandardErrorContent}' --output json |
  jq -r '"--- stdout ---\n" + .stdout + "\n--- stderr ---\n" + .stderr'

[ "$STATUS" = "Success" ] || { echo "Comando terminou com status $STATUS" >&2; exit 1; }
