(() => {
    const form = document.getElementById('filtros-solicitudes');
    if (!form) return;
    const campo = form.elements.q;
    const exacto = form.elements.codigo_exacto;
    const lista = document.getElementById('sugerencias-codigos');
    const estado = document.getElementById('estado-sugerencias');
    let opciones = [];
    let activo = -1;
    let version = 0;
    let temporizador;
    let peticion;
    campo.setAttribute('role', 'combobox');
    campo.setAttribute('aria-autocomplete', 'list');
    campo.setAttribute('aria-controls', lista.id);
    campo.setAttribute('aria-expanded', 'false');
    campo.setAttribute('autocomplete', 'off');

    function cerrar() {
        version++;
        clearTimeout(temporizador);
        peticion?.abort();
        lista.hidden = true;
        campo.setAttribute('aria-expanded', 'false');
        campo.removeAttribute('aria-activedescendant');
        activo = -1;
        estado.textContent = '';
    }

    function elegir(codigo) {
        campo.value = codigo;
        exacto.value = codigo;
        cerrar();
        form.requestSubmit();
    }

    function mostrar(codigos) {
        lista.replaceChildren();
        opciones = codigos.map((codigo, indice) => {
            const opcion = document.createElement('button');
            opcion.type = 'button';
            opcion.className = 'list-group-item list-group-item-action';
            opcion.id = `codigo-sugerido-${indice}`;
            opcion.tabIndex = -1;
            opcion.setAttribute('role', 'option');
            opcion.setAttribute('aria-selected', 'false');
            opcion.textContent = codigo;
            opcion.addEventListener('pointerdown', evento => evento.preventDefault());
            opcion.addEventListener('click', () => elegir(codigo));
            lista.append(opcion);
            return opcion;
        });
        lista.hidden = opciones.length === 0;
        campo.setAttribute('aria-expanded', String(opciones.length > 0));
        estado.textContent = opciones.length ? `${opciones.length} códigos disponibles. Usa las flechas para elegir o Buscar para búsqueda libre.` : '';
    }

    function buscar() {
        cerrar();
        if (!campo.value.trim()) return;
        const actual = version;
        temporizador = setTimeout(async () => {
            const parametros = new URLSearchParams(new FormData(form));
            parametros.delete('codigo_exacto');
            peticion = new AbortController();
            try {
                const respuesta = await fetch(`${form.dataset.codigosUrl}?${parametros}`, {
                    signal: peticion.signal, headers: {'Accept': 'application/json'},
                });
                if (!respuesta.ok) return;
                const datos = await respuesta.json();
                if (actual === version && document.activeElement === campo) mostrar(datos.codigos);
            } catch {
                // La búsqueda normal sigue disponible si no se pueden cargar sugerencias.
            }
        }, 120);
    }

    campo.addEventListener('input', () => { exacto.value = ''; buscar(); });
    campo.addEventListener('focus', buscar);
    campo.addEventListener('blur', cerrar);
    form.addEventListener('change', evento => {
        if (evento.target !== campo && document.activeElement === campo) buscar();
    });
    campo.addEventListener('keydown', evento => {
        if (evento.key === 'Escape') { cerrar(); return; }
        if (lista.hidden || !opciones.length) return;
        if (evento.key === 'ArrowDown' || evento.key === 'ArrowUp') {
            evento.preventDefault();
            const paso = evento.key === 'ArrowDown' ? 1 : -1;
            activo = activo < 0 ? (paso === 1 ? 0 : opciones.length - 1)
                : (activo + paso + opciones.length) % opciones.length;
            opciones.forEach((opcion, indice) => {
                opcion.classList.toggle('active', indice === activo);
                opcion.setAttribute('aria-selected', String(indice === activo));
            });
            campo.setAttribute('aria-activedescendant', opciones[activo].id);
            opciones[activo].scrollIntoView({block: 'nearest'});
        } else if (evento.key === 'Enter' && activo >= 0) {
            evento.preventDefault();
            elegir(opciones[activo].textContent);
        }
    });
})();
