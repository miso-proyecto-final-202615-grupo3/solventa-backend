#!/bin/sh
# Se ejecuta cuando LocalStack está listo (/etc/localstack/init/ready.d).
# Crea las colas de los eventos del flujo de adquisición, cada una con su cola de mensajes
# fallidos (DLQ):
#   solventa-pago-aprobado   PagoAprobado, lo publica payments_service y lo consume insurancepolicies_service
#   solventa-poliza-emitida  PolizaEmitida, lo publica y lo consume insurancepolicies_service (certificado PDF)
set -eu

crear_cola() {
  cola="$1"
  dlq="${cola}-dlq"

  awslocal sqs create-queue --queue-name "$dlq" >/dev/null
  dlq_url=$(awslocal sqs get-queue-url --queue-name "$dlq" --query QueueUrl --output text)
  dlq_arn=$(awslocal sqs get-queue-attributes --queue-url "$dlq_url" \
    --attribute-names QueueArn --query Attributes.QueueArn --output text)

  # Tras 5 recepciones fallidas el mensaje pasa a la DLQ. El tiempo de visibilidad cubre lo que
  # tarda procesar un mensaje (emitir la póliza o renderizar el PDF).
  cat > "/tmp/${cola}-atributos.json" <<EOF
{"VisibilityTimeout": "120", "RedrivePolicy": "{\"deadLetterTargetArn\":\"${dlq_arn}\",\"maxReceiveCount\":\"5\"}"}
EOF
  awslocal sqs create-queue --queue-name "$cola" --attributes "file:///tmp/${cola}-atributos.json" >/dev/null

  echo "Cola SQS creada: $cola (DLQ: $dlq)"
}

crear_cola solventa-pago-aprobado
crear_cola solventa-poliza-emitida
