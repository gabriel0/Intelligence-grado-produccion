# Guía de soporte N1 — Nova X

Runbook corto para el equipo de soporte de primer nivel. El objetivo es resolver el 70% de
los tickets sin escalar a hardware.

## Triage inicial (siempre)

1. Pedir número de serie y fecha de compra / factura.
2. Confirmar firmware: en la app Nova Connect → Ajustes → Acerca de.
3. Firmware mínimo recomendado para esta guía: **1.4.2**.
4. Preguntar si el problema aparece en un solo dispositivo o en todos.

## Problema: no enciende

Síntomas: LED apagado, no responde al botón de power.

Pasos:

1. Conectar USB-C a un puerto que entregue al menos 5V/1A durante 30 minutos.
2. Mantener power 10 segundos para reset blando.
3. Si el LED no parpadea en ámbar durante la carga, escalar a RMA (posible falla de
   batería o placa).

No ofrecer reembolso inmediato en N1. Documentar evidencia (foto del LED, video corto).

## Problema: se corta el Bluetooth

Síntomas: audio entrecortado, desconexiones a menos de 3 metros.

Pasos:

1. Olvidar el dispositivo en el teléfono y volver a emparejar.
2. Desactivar multipunto temporalmente (deja un solo host).
3. Probar sin ANC para descartar carga de DSP.
4. Si solo falla cerca de routers 5 GHz congestionados, sugerir banda 2.4 o acercar el
   host. No es defecto si el alcance vuelve a la normalidad en otra red.

## Problema: un lado no suena

1. Reproducir tono de prueba en la app (Balance L/R).
2. Reset de fábrica: power + ANC 15 segundos hasta LED blanco.
3. Si persiste tras reset y firmware actualizado, abrir RMA por audio asymmetría.

## Problema: demora de entrega / reclamo logístico

Esto no se resuelve con firmware. Registrar:

- Número de orden
- Días de demora declarados por el cliente
- Estado del tracking

Escalar a logística. El sentimiento de reseñas sobre demoras (por ejemplo la de Luis)
es consistente con picos de courier en semanas de alta demanda; no prometer fechas
nuevas sin confirmación del operador.

## Frases que el asistente NO debe usar

- No inventar precios ni márgenes distintos a la ficha.
- No afirmar cobertura internacional de garantía.
- No indicar que existe garantía “en dólares” o para TV Bravia u otros SKUs ajenos.
