(() => {
    const form = document.getElementById('solicitud-alquiler-form');
    if (!form) return;

    const plan = document.getElementById('id_plan');
    const cantidad = document.getElementById('id_cantidad');
    const fechaInicio = document.getElementById('id_fecha_inicio');
    const duracion = document.getElementById('presupuesto-duracion');
    const fechaFin = document.getElementById('presupuesto-fecha-fin');
    const renta = document.getElementById('presupuesto-renta');
    const deposito = document.getElementById('presupuesto-deposito');
    const total = document.getElementById('presupuesto-total');
    const moneda = new Intl.NumberFormat('es-DO', {
        style: 'currency',
        currency: 'DOP',
    });

    const tarifas = {
        diario: Number(form.dataset.tarifaDiaria),
        semanal: Number(form.dataset.tarifaSemanal),
        mensual: Number(form.dataset.tarifaMensual),
    };
    const depositoGarantia = Number(form.dataset.deposito);
    const diasPlan = { diario: 1, semanal: 7, mensual: 30 };

    function actualizarPresupuesto() {
        const cantidadPlan = Math.max(Number.parseInt(cantidad.value, 10) || 0, 0);
        const importeRenta = (tarifas[plan.value] || 0) * cantidadPlan;
        const importeDeposito = depositoGarantia;
        const dias = (diasPlan[plan.value] || 1) * cantidadPlan;

        duracion.textContent = `${dias} día(s)`;
        renta.textContent = moneda.format(importeRenta);
        deposito.textContent = moneda.format(importeDeposito);
        total.textContent = moneda.format(importeRenta + importeDeposito);

        if (!fechaInicio.value || !cantidadPlan) {
            fechaFin.textContent = 'Selecciona fecha y cantidad';
            return;
        }

        const [anio, mes, dia] = fechaInicio.value.split('-').map(Number);
        const fin = new Date(Date.UTC(anio, mes - 1, dia + dias - 1));
        fechaFin.textContent = new Intl.DateTimeFormat('es-DO', {
            dateStyle: 'long',
            timeZone: 'UTC',
        }).format(fin);
    }

    form.addEventListener('input', actualizarPresupuesto);
    form.addEventListener('change', actualizarPresupuesto);
    actualizarPresupuesto();
})();
