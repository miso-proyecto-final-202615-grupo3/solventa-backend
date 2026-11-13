#!/bin/sh
# Se ejecuta cuando LocalStack está listo (/etc/localstack/init/ready.d).
# Crea la cola del evento PagoAprobado y su cola de mensajes fallidos (DLQ).
set -eu

QUEUE=solventa-pago-aprobado
DLQ="${QUEUE}-dlq"

awslocal sqs create-queue --queue-name "$DLQ" >/dev/null
DLQ_URL=$(awslocal sqs get-queue-url --queue-name "$DLQ" --query QueueUrl --output text)
DLQ_ARN=$(awslocal sqs get-queue-attributes --queue-url "$DLQ_URL" \
  --attribute-names QueueArn --query Attributes.QueueArn --output text)

cat > /tmp/redrive.json <<EOF
{"RedrivePolicy": "{\"deadLetterTargetArn\":\"${DLQ_ARN}\",\"maxReceiveCount\":\"5\"}"}
EOF
awslocal sqs create-queue --queue-name "$QUEUE" --attributes file:///tmp/redrive.json >/dev/null

echo "Colas SQS creadas: $QUEUE (DLQ: $DLQ)"
