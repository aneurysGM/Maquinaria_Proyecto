(() => {
    const form = document.getElementById('pago-recibido-form');
    const revision = document.getElementById('confirmacion-reserva');
    if (!form || !revision) return;
    const enviaAvisos = revision.querySelectorAll('textarea').length > 0;
    const entero = value => Number(String(value).replace(/,/g, '')) || 0;
    function actualizar() {
        const concepto = form.elements.concepto.value;
        const monto = entero(form.elements.monto.value);
        const renta = entero(form.dataset.rentaPendiente);
        const deposito = entero(form.dataset.depositoPendiente);
        const confirma = renta <= (concepto === 'renta' ? monto : 0)
            && deposito <= (concepto === 'deposito' ? monto : 0);
        revision.hidden = !confirma;
        revision.querySelectorAll('textarea').forEach(campo => {
            campo.required = confirma;
            campo.disabled = !confirma;
        });
        document.getElementById('guardar-pago').textContent = confirma
            ? (enviaAvisos ? 'Confirmar pago y enviar avisos' : 'Confirmar pago y reserva')
            : 'Guardar pago';
    }
    form.addEventListener('input', actualizar);
    form.addEventListener('change', actualizar);
    actualizar();
})();
