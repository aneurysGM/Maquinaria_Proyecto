(() => {
    const form = document.getElementById('pago-recibido-form');
    const revision = document.getElementById('confirmacion-reserva');
    if (!form || !revision) return;
    const centavos = value => Math.round(Number(value) * 100);
    function actualizar() {
        const concepto = form.elements.concepto.value;
        const monto = centavos(form.elements.monto.value);
        const renta = centavos(form.dataset.rentaPendiente);
        const deposito = centavos(form.dataset.depositoPendiente);
        const confirma = renta <= (concepto === 'renta' ? monto : 0)
            && deposito <= (concepto === 'deposito' ? monto : 0);
        revision.hidden = !confirma;
        revision.querySelectorAll('textarea').forEach(campo => {
            campo.required = confirma;
            campo.disabled = !confirma;
        });
        document.getElementById('guardar-pago').textContent = confirma ? 'Confirmar pago y reserva' : 'Guardar pago';
    }
    form.addEventListener('input', actualizar);
    form.addEventListener('change', actualizar);
    actualizar();
})();
