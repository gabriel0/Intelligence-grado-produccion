# Política interna de precios y márgenes — línea Nova X

Documento interno de merchandising. No es una lista de precios al público; define
cómo se interpretan los números de la ficha y cuándo hace falta aprobación humana
antes de publicar un cambio en el catálogo.

## Números de referencia en ficha

Según la ficha técnica vigente del auricular Nova X:

- Precio de venta: **89990 pesos**.
- Costo de reposición: **40000 pesos**.

El margen porcentual se calcula siempre así:

```text
margen_porcentual = (precio_venta - costo) / precio_venta * 100
```

Con los valores actuales:

```text
(89990 - 40000) / 89990 * 100 ≈ 55.56%
```

Cualquier respuesta automática que cite margen debe usar el resultado de la
herramienta `calcular_margen`, no un número redondeado “a ojo”.

## Umbrales de negocio

- Margen saludable: mayor o igual a 50%.
- Margen de alerta: entre 40% y 50% (revisión de pricing).
- Margen crítico: menor a 40% (no se publican descuentos sin aprobación de
  categoría).

Con la ficha actual, el Nova X está en zona saludable (~55.56%). Un descuento del
10% sobre el precio de venta dejaría el precio propuesto en **80991 pesos**. Ese
cambio **no** se escribe solo: debe pasar por el flujo HITL de aprobación
(`publicar_ajuste_precio`) porque altera el catálogo.

## Qué puede hacer el asistente sin aprobación

- Informar precio de venta y costo de reposición tal como figuran en la ficha.
- Calcular e informar el margen porcentual.
- Comparar el margen contra el umbral del 50%.
- Resumir sentimiento de reseñas.

## Qué requiere aprobación humana

- Publicar un descuento o precio nuevo en el catálogo.
- Cambiar el precio de venta publicado en canales.
- Cualquier acción que escriba en `ajustes.jsonl` / registro de catálogo.

## Fuera de alcance

- Precios de otros SKUs (televisores, parlantes, etc.).
- Cotizaciones en dólares u otras monedas: el catálogo local opera en pesos.
- Promociones bancarias de terceros: no están en este corpus.
