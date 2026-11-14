(() => {
    const form = document.getElementById('solicitud-alquiler-form');
    if (!form) return;
    const inicio = form.elements.fecha_inicio;
    const plan = form.elements.plan;
    const cantidad = form.elements.cantidad;
    const periodos = JSON.parse(document.getElementById('periodos-ocupados').textContent);
    const parse = value => new Date(`${value}T00:00:00Z`);
    const iso = fecha => fecha.toISOString().slice(0, 10);
    const hoy = form.dataset.hoy;
    inicio.min = hoy;
    let mes = parse(inicio.value || hoy);
    mes.setUTCDate(1);
    function ocupado(fecha) {
        return periodos.some(p => p.inicio <= fecha && p.fin >= fecha);
    }
    function periodoLibre(fecha) {
        const dias = ({diario: 1, semanal: 7, mensual: 30}[plan.value] || 1) * Number(cantidad.value);
        if (!Number.isSafeInteger(dias) || dias < 1) return false;
        const fin = parse(fecha);
        fin.setUTCDate(fin.getUTCDate() + dias - 1);
        if (!Number.isFinite(fin.getTime()) || fin.getUTCFullYear() > 9999) return false;
        return !periodos.some(p => p.inicio <= iso(fin) && p.fin >= fecha);
    }
    function actualizar() {
        const aviso = document.getElementById('aviso-disponibilidad');
        const valido = !inicio.value || periodoLibre(inicio.value);
        aviso.textContent = valido ? 'Selecciona una fecha disponible para solicitar.' : 'El período completo incluye fechas ocupadas. Elige otra fecha de inicio.';
        aviso.classList.toggle('text-danger', !valido);
        inicio.setCustomValidity(valido ? '' : aviso.textContent);
        form.querySelector('button[type="submit"]').disabled = !valido;
        const contenedor = document.getElementById('calendario-dias');
        contenedor.replaceChildren();
        document.getElementById('calendario-mes').textContent = new Intl.DateTimeFormat('es-DO', {month: 'long', year: 'numeric', timeZone: 'UTC'}).format(mes);
        ['Lu', 'Ma', 'Mi', 'Ju', 'Vi', 'Sá', 'Do'].forEach(dia => {
            const label = document.createElement('span');
            label.className = 'text-center small fw-bold';
            label.textContent = dia;
            contenedor.append(label);
        });
        const desfase = (mes.getUTCDay() + 6) % 7;
        for (let i = 0; i < desfase; i++) contenedor.append(document.createElement('span'));
        const ultimo = new Date(Date.UTC(mes.getUTCFullYear(), mes.getUTCMonth() + 1, 0)).getUTCDate();
        for (let dia = 1; dia <= ultimo; dia++) {
            const fecha = iso(new Date(Date.UTC(mes.getUTCFullYear(), mes.getUTCMonth(), dia)));
            const boton = document.createElement('button');
            const ocupadoDia = ocupado(fecha);
            const libre = periodoLibre(fecha);
            boton.type = 'button';
            boton.textContent = dia;
            boton.className = `btn btn-sm ${ocupadoDia ? 'btn-danger' : 'btn-outline-success'}`;
            boton.disabled = fecha < hoy || !libre;
            boton.setAttribute('aria-label', `${fecha}: ${ocupadoDia ? 'Ocupada' : libre ? 'Disponible para solicitar' : 'El plan incluye fechas ocupadas'}`);
            boton.setAttribute('aria-pressed', String(inicio.value === fecha));
            if (inicio.value === fecha) boton.classList.add('active');
            boton.addEventListener('click', () => {
                inicio.value = fecha;
                inicio.dispatchEvent(new Event('change', {bubbles: true}));
            });
            contenedor.append(boton);
        }
    }
    document.getElementById('mes-anterior').addEventListener('click', () => { mes.setUTCMonth(mes.getUTCMonth() - 1); actualizar(); });
    document.getElementById('mes-siguiente').addEventListener('click', () => { mes.setUTCMonth(mes.getUTCMonth() + 1); actualizar(); });
    form.addEventListener('input', actualizar);
    form.addEventListener('change', actualizar);
    form.addEventListener('submit', event => { if (!inicio.reportValidity()) event.preventDefault(); });
    actualizar();
})();
