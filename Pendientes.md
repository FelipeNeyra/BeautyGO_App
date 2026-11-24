## Lista de Pendientes

##### Necesarios a realizar (Particulares)

1. Corregir error que permite reservar más de una agenda en un mismo horario. (Debe bloquearse) ✅
2. En relación al anterior, corregir forma de almacenamietno de hora de reserva, actualmente se desplaza en tres horas hacia adelante
   - Si se reserva a las 11:30 horas, se guarda un registro para las 14:30 horas. ✅
3. Implementar filtros para solicitudes de prestadores (Pendientes, Aprobadas, Rechazadas). ✅
4. En conjunto al punto anterior, incoporar paginación y dashboard análitico (Promedios de tipos de solicitudes (Rechazadas y Aprobadas)).
5. Mostrar montos totaltes adquiridos en base a las suscripciones.
   - De forma total (Es decir, de todas las suscripciones ya pagadas).
   - Por mes, a forma de filtro.Mostrar montos totaltes adquiridos en base a las suscripciones.


6. Filtrar suscripciones que aún no hayan sido pagadas.
7. (**Evaluar su implementación**) Implementar sistema de pago automatico de suscripciones.

   - Puede ser viable dada la naturaleza de pasarela de pago Webpay Plus.
8. Errores gráficos de mediana a pequeña escala presentes.

##### Necesarios a realizar (Conjunto)

###### Sistema de validación para evitar agendamiento que solapen otros

- Implica un/os nuevo@ modúlo@ que bloqueen dos o más horarios según la duración de una reserva.
- Por ejemplo, Si una reserva con horario a las 18:00 horas dura 1 hora, debe bloquearse el bloque de las 18:30 horas.

##### Evaluar si se deben hacer

1. Modificar relación entre tablas **Reserva** y **Servicio**. Resulta innecesaria una relación ManyToMany pero tampoco afecta.
