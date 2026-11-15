// Ejecutar con: node apps/tecnico_mantenimiento/tests_controles.cjs
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

function ejecutarScript(archivo, elementos, indice = 0) {
    const html = fs.readFileSync(archivo, 'utf8');
    const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
    vm.runInNewContext(scripts[indice][1], {
        document: {getElementById: id => elementos[id]},
        Option: function(text, value) { this.text = text; this.value = value; },
    });
}

const selector = {value: 'Hidráulica', addEventListener(evento, fn) { this.cambiar = fn; }};
const campo = {focus() { this.enfocado = true; }};
const contenedor = {};
ejecutarScript(path.join(__dirname, 'templates/tecnico_mantenimiento/especialidad_script.html'), {
    id_especialidad: selector, id_nueva_especialidad: campo, 'campo-nueva-especialidad': contenedor,
});
assert.equal(contenedor.hidden, true);
assert.equal(campo.disabled, true);
selector.value = '__nueva__';
selector.cambiar();
assert.equal(contenedor.hidden, false);
assert.equal(campo.disabled, false);
assert.equal(campo.required, true);
assert.equal(campo.enfocado, true);
selector.value = 'Mecánica';
selector.cambiar();
assert.equal(contenedor.hidden, true);
assert.equal(campo.required, false);

const filtro = {value: '', addEventListener(evento, fn) { this.cambiar = fn; }};
const responsable = {
    value: '1', opciones: [],
    replaceChildren(...opciones) { this.opciones = opciones; },
    add(opcion) { this.opciones.push(opcion); },
};
const aviso = {};
const tecnicos = [
    {id: 1, nombre: 'Ana · Hidráulica', especialidad: 'Hidráulica'},
    {id: 2, nombre: 'Luis · Electricidad', especialidad: 'Electricidad'},
    {id: 3, nombre: 'Eva · Motores', especialidad: 'Motores'},
];
ejecutarScript(path.join(__dirname, '../mantenimiento/templates/mantenimiento/mantenimiento_form.html'), {
    id_especialidad: filtro, id_tecnico_responsable: responsable, 'aviso-sin-tecnicos': aviso,
    'tecnicos-disponibles': {textContent: JSON.stringify(tecnicos)},
}, 1);
assert.equal(responsable.opciones.length, 4);
assert.equal(responsable.value, '1');
filtro.value = 'Hidráulica';
filtro.cambiar();
assert.deepEqual(responsable.opciones.map(opcion => opcion.value), ['', '1']);
assert.equal(responsable.value, '1');
filtro.value = 'Electricidad';
filtro.cambiar();
assert.equal(responsable.value, '');
assert.equal(aviso.hidden, true);
assert.deepEqual(responsable.opciones.map(opcion => opcion.value), ['', '2']);
filtro.value = 'Mecánica';
filtro.cambiar();
assert.equal(aviso.hidden, false);
assert.equal(responsable.opciones.length, 1);
filtro.value = 'Motores';
filtro.cambiar();
assert.equal(aviso.hidden, true);
assert.deepEqual(responsable.opciones.map(opcion => opcion.value), ['', '3']);
filtro.value = '';
filtro.cambiar();
assert.equal(responsable.opciones.length, 4);
console.log('OK: campo de especialidad, filtrado, selección y aviso sin coincidencias.');
