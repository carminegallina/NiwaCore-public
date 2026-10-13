const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(`${__dirname}/static/print-editor.js`, 'utf8');

function editor({frames = [], saved = 'none', failFrame = false} = {}) {
    const elements = new Map();
    const pixels = {data: new Uint8ClampedArray(30 * 40 * 4), width: 30, height: 40};
    for (let y = 0; y < 40; y++) for (let x = 0; x < 30; x++) {
        const index = (y * 30 + x) * 4;
        pixels.data.fill((x + y) % 2 ? 100 : 140, index, index + 3);
        pixels.data[index + 3] = 255;
    }
    const drawing = {
        fillRect() {}, drawImage() {}, save() {}, restore() {},
        translate(x, y) { this.lastX = x; this.lastY = y; },
        rotate() {}, scale() {}, putImageData(pixels) { this.lastImageData = pixels; },
        getImageData(_x, _y, width, height) {
            if (width === 30 && height === 40) return pixels;
            const data = new Uint8ClampedArray(width * height * 4);
            for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
                data[(y * width + x) * 4 + 3] = x >= 60 && x < width - 60
                    && y >= 60 && y < height - 60 ? 0 : 255;
            }
            return {data, width, height};
        },
    };
    function element(id) {
        if (!elements.has(id)) elements.set(id, {
            id, value: '', textContent: '', hidden: false, open: false, disabled: false,
            listeners: {}, children: [], style: {},
            classList: {toggle() {}},
            addEventListener(type, handler) { this.listeners[type] = handler; },
            append(...children) { this.children.push(...children); },
            replaceChildren(...children) { this.children = children; },
            add(child) { this.children.push(child); },
            setAttribute() {}, removeAttribute() {}, setPointerCapture() {},
            dispatchEvent(event) { event.target = this; this.listeners[event.type]?.(event); },
            getBoundingClientRect: () => ({width: 100, height: 150}),
            getContext: () => drawing,
        });
        return elements.get(id);
    }
    element('printEditor').hidden = true;
    element('printExportResult').hidden = true;
    element('printFileType').value = 'jpg';
    const sliders = [['printZoom', '1', '6'], ['printExposure', '-2', '2']].map(([id, min, max]) =>
        Object.assign(element(id), {min, max, parentElement: element(`${id}-row`)}));
    let created = 0;
    const context = vm.createContext({
        document: {
            getElementById: element, createElement: (tag) => element(`${tag}-${++created}`),
            querySelectorAll: (selector) => (selector.includes('range') ? sliders : []),
            addEventListener() {},
            body: {style: {}},
        },
        window: {},
        localStorage: {getItem: () => saved, setItem() {}},
        Image: class {
            width = 30;
            height = 40;
            set src(url) {
                queueMicrotask(() => {
                    if (failFrame && url.includes('/frames/')) this.onerror();
                    else this.onload();
                });
            }
        },
        ImageData: class {
            constructor(data, width, height) { Object.assign(this, {data, width, height}); }
        },
        Option: class {
            constructor(label, value) { Object.assign(this, {label, value}); }
        },
        fetch: async (url) => ({
            ok: true,
            json: async () => url.endsWith('/presets')
                ? {presets: {P: {label: 'P', mm: [148, 100]}}}
                : {frames},
        }),
        requestAnimationFrame: (callback) => callback(),
        Event: class { constructor(type) { this.type = type; } },
        Uint8ClampedArray, Math, Map,
    });
    vm.runInContext(source, context);
    return {elements, element, drawing, open: context.window.NiwaPrintEditor.open};
}

(async () => {
    const ui = editor();
    await ui.open({id: 'photo', name: 'photo.jpg'});
    const canvas = ui.element('printCanvas');
    const pixelDifference = () => {
        const data = ui.drawing.lastImageData.data;
        const first = (10 * 30 + 10) * 4;
        return Math.abs(data[first] - data[first + 4]);
    };
    const noisyDifference = pixelDifference();
    ui.element('printLuminanceNoise').listeners.input({target: {value: '100'}});
    assert.ok(pixelDifference() < noisyDifference / 2,
        'luminance slider visibly smooths fine-grained noise in the preview');
    for (const [name, value] of [['Contrast', '20'], ['Temperature', '30'],
        ['Tint', '-10'], ['Vibrance', '40'], ['Saturation', '15'], ['LuminanceNoise', '25']]) {
        ui.element(`print${name}`).listeners.input({target: {value}});
        assert.equal(ui.element(`print${name}Value`).textContent,
            `${Number(value) > 0 && name !== 'LuminanceNoise' ? '+' : ''}${Number(value)}`);
    }
    ui.element('printResetLights').listeners.click();
    for (const name of ['Contrast', 'Temperature', 'Tint', 'Vibrance', 'Saturation', 'LuminanceNoise']) {
        assert.equal(ui.element(`print${name}`).value, 0);
    }
    assert.equal(ui.element('printZoom').value, 1);
    canvas.listeners.pointerdown({pointerId: 1, clientX: 20, clientY: 20});
    canvas.listeners.pointermove({pointerId: 1, clientX: 30, clientY: 25});
    assert.equal(ui.element('printZoom').value, 1, 'one-finger pan never changes zoom');
    canvas.listeners.pointerup({pointerId: 1});
    ui.element('printZoom').listeners.input({target: {value: '4'}});
    canvas.listeners.pointerdown({pointerId: 1, clientX: 20, clientY: 20});
    canvas.listeners.pointermove({pointerId: 1, clientX: 90, clientY: 20});
    assert.ok(ui.drawing.lastX > canvas.width,
        'high zoom allows panning beyond the old fixed 40% limit');
    canvas.listeners.pointerup({pointerId: 1});
    ui.element('printResetPosition').listeners.click();

    canvas.listeners.pointerdown({pointerId: 1, clientX: 20, clientY: 20});
    canvas.listeners.pointerdown({pointerId: 2, clientX: 80, clientY: 20});
    canvas.listeners.pointermove({pointerId: 1, clientX: 30, clientY: 20});
    canvas.listeners.pointermove({pointerId: 2, clientX: 90, clientY: 20});
    assert.equal(ui.element('printZoom').value, 1, 'two-finger pan has no zoom drift');
    canvas.listeners.pointerup({pointerId: 1});
    canvas.listeners.pointerup({pointerId: 2});
    ui.element('printRotation').listeners.input({target: {value: '20'}});
    assert.equal(ui.element('printZoom').value, 1, 'rotation does not change zoom');

    const frame = {id: 'frame-1', name: 'Evento', preset: 'P', orientation: 'portrait',
        collection: 'Evento', url: '/frames/frame-1/image', thumbnail_url: '/frames/frame-1/thumb'};
    const noFrame = editor({frames: [frame], saved: 'none'});
    await noFrame.open({id: 'photo', name: 'photo.jpg'});
    assert.equal(noFrame.element('printActiveFrame').textContent, 'Nessuna',
        'explicitly choosing no frame survives the next photo');
    assert.equal(noFrame.element('printPreset').value, 'P');
    assert.equal(noFrame.element('printDirect').disabled, false,
        'no frame still allows direct P printing');

    const framed = editor({frames: [frame], saved: frame.id});
    await framed.open({id: 'photo', name: 'photo.jpg'});
    const framedCanvas = framed.element('printCanvas');
    const centerX = framed.drawing.lastX;
    framedCanvas.listeners.pointerdown({pointerId: 1, clientX: 20, clientY: 20});
    framedCanvas.listeners.pointermove({pointerId: 1, clientX: 22, clientY: 20});
    assert.equal(framed.element('printZoom').value, 1);
    assert.ok(framed.drawing.lastX > centerX, 'photo moves within the covered frame');
    framedCanvas.listeners.pointermove({pointerId: 1, clientX: 60, clientY: 20});
    assert.ok(framed.drawing.lastX < centerX + framedCanvas.width * 0.12,
        'pan stops before uncovering the transparent frame area');
    assert.equal(framed.element('printZoom').value, 1, 'the limit never adds zoom');
    framedCanvas.listeners.pointerup({pointerId: 1});
    framed.element('printResetPosition').listeners.click();
    framed.element('printRotate90').listeners.click();
    assert.equal(framed.element('printRotation').value, 0,
        'quarter-turn button never stops at an unexpected intermediate angle');
    framed.element('printRotation').listeners.input({target: {value: '45'}});
    assert.ok(Number(framed.element('printRotation').value) < 45,
        'rotation stops before exposing white space');
    assert.equal(framed.element('printZoom').value, 1, 'rotation never adds zoom');
    framed.element('printResetPosition').listeners.click();
    framed.element('printZoom').listeners.input({target: {value: '1.4'}});
    framed.element('printRotation').listeners.input({target: {value: '30'}});
    framed.element('printZoom').listeners.input({target: {value: '1'}});
    assert.ok(Number(framed.element('printZoom').value) > 1,
        'shrinking stops at the minimum size that covers the visible frame');

    const touch = editor();
    await touch.open({id: 'photo', name: 'photo.jpg'});
    const exposure = touch.element('printExposure');
    const row = touch.element('printExposure-row');
    row.listeners.pointerdown({pointerId: 7, target: row, clientX: 50, clientY: 10});
    row.listeners.pointermove({pointerId: 7, clientX: 52, clientY: 40});
    row.listeners.pointermove({pointerId: 7, clientX: 90, clientY: 90});
    row.listeners.pointerup({pointerId: 7});
    assert.equal(Number(exposure.value), 0, 'scrolling over a slider never changes it');
    row.listeners.pointerdown({pointerId: 8, target: row, clientX: 50, clientY: 10});
    row.listeners.pointermove({pointerId: 8, clientX: 55, clientY: 11});
    assert.equal(Number(exposure.value), 0, 'a tap or a small wobble never changes it');
    row.listeners.pointermove({pointerId: 8, clientX: 75, clientY: 12});
    row.listeners.pointerup({pointerId: 8});
    assert.equal(Number(exposure.value), 1, 'a sideways drag moves the slider from its value');
    assert.equal(touch.element('printExposureValue').textContent, '1,00');
    row.listeners.pointerdown({pointerId: 9, target: exposure, clientX: 50, clientY: 10});
    row.listeners.pointermove({pointerId: 9, clientX: 90, clientY: 10});
    assert.equal(Number(exposure.value), 1, 'mouse on the native slider is left to the browser');

    const broken = editor({frames: [frame], saved: frame.id, failFrame: true});
    await broken.open({id: 'photo', name: 'photo.jpg'});
    assert.match(broken.element('printEditorStatus').textContent, /Cornice non caricata/);
    assert.equal(broken.element('printExport').disabled, true,
        'a missing selected frame cannot be silently exported away');
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
