(() => {
    const boton = document.getElementById('alternar-motivo-rechazo');
    const motivo = document.getElementById('motivo-rechazo');
    if (!boton || !motivo) return;

    function mostrarMotivo(abierto) {
        motivo.hidden = !abierto;
        boton.setAttribute('aria-expanded', String(abierto));
        boton.textContent = abierto ? 'Ocultar motivo' : 'Ver motivo';
    }

    function abrirDesdeEnlace() {
        if (window.location.hash === '#motivo-rechazo') {
            mostrarMotivo(true);
            motivo.scrollIntoView({block: 'nearest'});
        }
    }

    boton.addEventListener('click', () => mostrarMotivo(motivo.hidden));
    window.addEventListener('hashchange', abrirDesdeEnlace);
    abrirDesdeEnlace();
})();
