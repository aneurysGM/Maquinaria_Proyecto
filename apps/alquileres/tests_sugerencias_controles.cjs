// Ejecutar con: node apps/alquileres/tests_sugerencias_controles.cjs
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

class Elemento {
    constructor(id = '') {
        this.id = id;
        this.value = '';
        this.children = [];
        this.listeners = {};
        this.attrs = {};
        this.classList = {toggle() {}};
    }
    addEventListener(tipo, accion) { this.listeners[tipo] = accion; }
    setAttribute(nombre, valor) { this.attrs[nombre] = valor; }
    removeAttribute(nombre) { delete this.attrs[nombre]; }
    replaceChildren() { this.children = []; }
    append(elemento) { this.children.push(elemento); }
    scrollIntoView() {}
}

async function probarSugerencias() {
    const campo = new Elemento();
    const exacto = new Elemento();
    const lista = new Elemento('sugerencias-codigos');
    const estado = new Elemento();
    const form = new Elemento('filtros-solicitudes');
    form.dataset = {codigosUrl: '/alquileres/solicitudes/sugerencias-codigos/'};
    form.elements = {q: campo, codigo_exacto: exacto, estado: {value: 'Pendiente'},
                     desde: {value: '2026-11-18'}, hasta: {value: '2026-11-25'}};
    let envios = 0;
    form.requestSubmit = () => { envios++; };
    const elementos = {'filtros-solicitudes': form, 'sugerencias-codigos': lista, 'estado-sugerencias': estado};
    const document = {getElementById: id => elementos[id], createElement: () => new Elemento(), activeElement: campo};
    const temporizadores = new Map();
    let siguiente = 0;
    let ultimaURL;
    let ultimaSenal;
    let responder = async () => ['EXC-PR-001', 'EXC-PR-002', 'EXC-PR-003'];
    const context = {
        document, URLSearchParams, AbortController,
        FormData: class {
            constructor(formulario) { this.datos = Object.entries(formulario.elements).map(([k, v]) => [k, v.value]); }
            [Symbol.iterator]() { return this.datos[Symbol.iterator](); }
        },
        setTimeout: accion => { const id = ++siguiente; temporizadores.set(id, accion); return id; },
        clearTimeout: id => temporizadores.delete(id),
        fetch: async (url, opciones) => {
            ultimaURL = url;
            ultimaSenal = opciones.signal;
            const codigos = await responder();
            return {ok: true, json: async () => ({codigos})};
        },
    };
    function iniciarPeticion() {
        const acciones = [...temporizadores.values()];
        temporizadores.clear();
        assert.equal(acciones.length, 1);
        return acciones[0]();
    }
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, 'static/alquileres/sugerencias_codigos.js'), 'utf8'), context);
    campo.value = 'exc-pr-00';
    campo.listeners.input();
    await iniciarPeticion();
    assert.equal(lista.hidden, false);
    assert.deepEqual(lista.children.map(e => e.textContent), ['EXC-PR-001', 'EXC-PR-002', 'EXC-PR-003']);
    const parametros = new URLSearchParams(ultimaURL.split('?')[1]);
    assert.equal(parametros.get('estado'), 'Pendiente');
    assert.equal(parametros.get('desde'), '2026-11-18');
    assert.equal(parametros.get('hasta'), '2026-11-25');
    assert.equal(parametros.has('codigo_exacto'), false);
    lista.children[1].listeners.click();
    assert.equal(campo.value, 'EXC-PR-002');
    assert.equal(exacto.value, 'EXC-PR-002');
    assert.equal(envios, 1);
    assert.equal(form.elements.estado.value, 'Pendiente');
    assert.equal(form.elements.desde.value, '2026-11-18');
    assert.equal(form.elements.hasta.value, '2026-11-25');

    campo.value = 'Nombre de un cliente';
    campo.listeners.input();
    assert.equal(exacto.value, '');
    await iniciarPeticion();
    let prevenido = false;
    campo.listeners.keydown({key: 'Enter', preventDefault: () => { prevenido = true; }});
    assert.equal(prevenido, false, 'Enter sin opción activa conserva la búsqueda libre');
    campo.listeners.keydown({key: 'ArrowUp', preventDefault() {}});
    assert.equal(campo.attrs['aria-activedescendant'], 'codigo-sugerido-2');
    campo.listeners.keydown({key: 'Enter', preventDefault() {}});
    assert.equal(exacto.value, 'EXC-PR-003');
    assert.equal(envios, 2);

    let resolverAntigua;
    responder = () => new Promise(resolve => { resolverAntigua = resolve; });
    campo.value = 'EXC';
    campo.listeners.input();
    const antigua = iniciarPeticion();
    const senalAntigua = ultimaSenal;
    responder = async () => ['EXC-PR-002'];
    campo.value = 'EXC-PR-002';
    campo.listeners.input();
    await iniciarPeticion();
    assert.equal(senalAntigua.aborted, true);
    resolverAntigua(['EXC-PR-001', 'EXC-PR-002', 'EXC-PR-003']);
    await antigua;
    assert.deepEqual(lista.children.map(e => e.textContent), ['EXC-PR-002'], 'Una respuesta antigua no repone el prefijo incompleto');
    campo.listeners.keydown({key: 'Escape'});
    assert.equal(lista.hidden, true);
    assert.equal(campo.attrs['aria-expanded'], 'false');

    responder = async () => { throw new Error('Red no disponible'); };
    campo.value = 'EXC';
    campo.listeners.input();
    await iniciarPeticion();
    assert.equal(lista.hidden, true);
    assert.equal(exacto.value, '');
    campo.value = '';
    campo.listeners.input();
    assert.equal(temporizadores.size, 0);
    return 'Sugerencias JavaScript: lista completa, selección exacta con filtros, búsqueda libre, teclado, Escape, fallo de red y respuestas fuera de orden verificados.';
}

module.exports = probarSugerencias;
if (require.main === module) probarSugerencias().then(console.log).catch(error => { console.error(error); process.exitCode = 1; });
