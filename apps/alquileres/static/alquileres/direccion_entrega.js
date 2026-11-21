(() => {
    'use strict';
    const guardar = document.getElementById('id_guardar');
    const grupo = document.getElementById('nombre-direccion');
    const nombre = document.getElementById('id_nombre');
    if (!guardar || !grupo || !nombre) return;
    const actualizar = () => {
        grupo.hidden = !guardar.checked;
        nombre.required = guardar.checked;
        nombre.disabled = !guardar.checked;
    };
    guardar.addEventListener('change', actualizar);
    actualizar();
})();
