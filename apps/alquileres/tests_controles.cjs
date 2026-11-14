// Ejecutar con: node apps/alquileres/tests_controles.cjs
// DOM mínimo para verificar las reglas de los controles sin un navegador.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

class Elemento {
    constructor() {
        this.children = [];
        this.listeners = {};
        this.attrs = {};
        this.value = '';
        this.dataset = {};
        this.classList = {toggle() {}, add() {}};
    }
    addEventListener(tipo, accion) { this.listeners[tipo] = accion; }
    dispatchEvent(evento) { this.listeners[evento.type]?.(evento); this.parent?.listeners[evento.type]?.(evento); }
    append(hijo) { this.children.push(hijo); }
    replaceChildren() { this.children = []; }
    setAttribute(nombre, valor) { this.attrs[nombre] = valor; }
    setCustomValidity(mensaje) { this.error = mensaje; }
    reportValidity() { return !this.error; }
}

function probarControles() {
    const ids = Object.fromEntries(['solicitud-alquiler-form', 'periodos-ocupados', 'calendario-dias',
        'calendario-mes', 'aviso-disponibilidad', 'mes-anterior', 'mes-siguiente'].map(id => [id, new Elemento()]));
    const form = ids['solicitud-alquiler-form'];
    const fecha = new Elemento();
    form.dataset.hoy = '2026-11-13';
    form.elements = {fecha_inicio: fecha, plan: {value: 'diario'}, cantidad: {value: '1'}};
    fecha.parent = form;
    const enviar = new Elemento();
    form.querySelector = () => enviar;
    ids['periodos-ocupados'].textContent = JSON.stringify([{inicio: '2026-11-18', fin: '2026-11-20'}]);
    const document = {getElementById: id => ids[id], createElement: () => new Elemento()};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, 'static/alquileres/disponibilidad.js'), 'utf8'), {document, Event});
    const dia = numero => ids['calendario-dias'].children.find(e => e.textContent === numero);
    assert.equal(dia(18).disabled, true);
    assert.match(dia(18).attrs['aria-label'], /Ocupada/);
    assert.equal(dia(17).disabled, false);
    assert.equal(fecha.min, '2026-11-13');
    form.elements.plan.value = 'semanal';
    form.listeners.change();
    assert.equal(dia(17).disabled, true, 'Una semana iniciada en un día libre puede incluir ocupación');
    assert.equal(dia(21).disabled, false);
    fecha.value = '2026-11-17';
    form.listeners.change();
    assert.equal(enviar.disabled, true);
    assert.match(fecha.error, /período completo/);
    dia(21).listeners.click();
    assert.equal(fecha.value, '2026-11-21');
    assert.equal(enviar.disabled, false);
    assert.equal(fecha.error, '');
    ids['mes-siguiente'].listeners.click();
    assert.match(ids['calendario-mes'].textContent, /diciembre/);
    ids['mes-anterior'].listeners.click();
    assert.match(ids['calendario-mes'].textContent, /noviembre/);

    const pago = new Elemento();
    const revision = new Elemento();
    const motivo = new Elemento();
    const guardar = new Elemento();
    pago.dataset = {rentaPendiente: '0.00', depositoPendiente: '3000.00'};
    pago.elements = {concepto: {value: 'deposito'}, monto: {value: ''}};
    revision.querySelectorAll = () => [motivo];
    const elementosPago = {'pago-recibido-form': pago, 'confirmacion-reserva': revision, 'guardar-pago': guardar};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../ventas/static/ventas/confirmacion_reserva.js'), 'utf8'),
                       {document: {getElementById: id => elementosPago[id]}});
    assert.equal(revision.hidden, true);
    pago.elements.monto.value = '2999.99';
    pago.listeners.input();
    assert.equal(revision.hidden, true);
    assert.equal(motivo.disabled, true);
    pago.elements.monto.value = '3000.00';
    pago.listeners.input();
    assert.equal(revision.hidden, false);
    assert.equal(motivo.required, true);
    assert.equal(motivo.disabled, false);
    assert.equal(guardar.textContent, 'Confirmar pago y reserva');
    pago.dataset = {rentaPendiente: '500.00', depositoPendiente: '0.00'};
    pago.elements.concepto.value = 'renta';
    pago.elements.monto.value = '500.00';
    pago.listeners.input();
    assert.equal(revision.hidden, false);
    pago.elements.monto.value = '499.99';
    pago.listeners.input();
    assert.equal(revision.hidden, true);
    assert.equal(guardar.textContent, 'Guardar pago');
    return 'Controles JavaScript: calendario, período semanal, navegación mensual, selección de fecha, pago parcial y confirmación verificados.';
}

module.exports = probarControles;
if (require.main === module) console.log(probarControles());
