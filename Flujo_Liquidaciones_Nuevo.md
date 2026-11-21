Dado a que una reserva debe ser primero **Confirmada** y finalmente **Completada** desde el panel de prestador por alguien homónimo, junto a que el pago del abono inicial se almacena en los registros, pero no el pago total, se debe hacer lo siguiente:

### Monto de pago de reservas

1. Mantener monto total de abono en registro de pago al hacer una reserva de forma inicial.
2. Si un prestador decide marcar como **Completa** una reserva, hacer las siguientes acciones:
   - Verificar fecha y hora presentes: Si la fecha y hora actuales son anteriores o corresponden a las mismas de la fecha preservada para la reserva, impedir marcar como completa la misma y alertar mediante un mensaje en una pantalla en bloque.
   - Establecer una reserva como completada: Se debe actualizar el registro de pago asociado a la reserva para que almacene el monto total del servicio solicitado.
3. Generar registro de liquidación automático para servicio:
   - EL registro debe generar de forma automática para las tablas `liquidacion` y `servicio_has_liquidacion`.
   - Establecer porcentaje de comisión en 15% para todas la liquidaciones.

### Sección de liquidaciones (Interfaz de Administración)

Se ha determinado cambiar el flujo original establecido, consistente en mantener en deposito las ganancias obtenidas por las reservas completadas y ser la administración quien debía llevar a cabo el pago de liquidaciones de forma manual (Leer documentos en carpeta `/documentos_evaluaciones` para obtener contexto de implementación completo). Este flujo responde directamente a la generación automática de registros de liquidación para servicios cuya reserva ya haya sido completada.

1. Obtener y listar únicamente reservas completadas.
2. Mantener columnas de datos ya definidas a excepción de "Servicios y Profesionales", la cuál debe ser dividida en dos columnas distintas ("Profesional" y "Servicio") respectivamente, y agregar campo "Neto Comisión", que muestre la cantidad de dinero obtenida por el porcentaje de comisión.
3. Generación de dashboard completo, funcionalidad de filtros y paginación de listado:
   - Incorporar un campo gráfico (Tipo `Label`) de nombre "Montos totales:" que muestre la suma de los montos netos de comisión generados.
   - Hacer funcionales las opciones de filtrado presentes utilizando el método `_filtered_services()` del archivo `views.py`. Se debe hacer énfasis en la presencia de los prestadores aprobados y que contengan servicios registrados, de igual forma que en la vista principal (`home`).
   - Hacer un conteo de registros de liquidaciones presentes y mostrarlo en el panel de titulo "Resumen" presente en la sección izquierda de la sección.
   - De igual forma que con los listados de servicios en la vista principal y de prestador, incorporar la paginación en base a la función `_paginated_services()` presente en `views.py`.
