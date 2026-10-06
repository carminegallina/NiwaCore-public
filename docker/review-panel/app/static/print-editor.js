(() => {
    const $ = (id) => document.getElementById(id);
    const canvas = $('printCanvas');
    const context = canvas.getContext('2d', {alpha: false});
    const state = {
        item: null, step: 2, presets: {}, frames: [], frame: null,
        frameImage: null, coverageMask: null, sourceImage: null, basePixels: null,
        adjusted: document.createElement('canvas'),
        exposure: 0, shadows: 0, highlights: 0,
        contrast: 0, temperature: 0, tint: 0, vibrance: 0, saturation: 0,
        luminanceNoise: 0,
        preset: 'P', orientation: 'landscape', zoom: 1,
        offsetX: 0, offsetY: 0, rotation: 0,
        pointers: new Map(), gesture: null, updateQueued: false, loadingFrame: false,
        frameError: false, frameThumbs: [],
        exporting: false, printing: false, openToken: 0, revision: 0,
    };

    const savedFrameKey = 'niwaPrintFrameId';

    function savedFrameId() {
        try { return localStorage.getItem(savedFrameKey); } catch (_) { return null; }
    }

    function rememberFrame(frame) {
        try {
            if (frame) localStorage.setItem(savedFrameKey, frame.id);
            else localStorage.setItem(savedFrameKey, 'none');
        } catch (_) { /* Private browsing may disable storage. */ }
    }

    function changed() {
        state.revision++;
        if (!$('printExportResult').hidden) status('Modifiche non ancora esportate.');
        $('printExportResult').hidden = true;
        $('printRedownload').removeAttribute('href');
    }

    function updateExportUi() {
        const config = state.presets[state.preset];
        const format = config?.label || state.preset;
        const direction = state.orientation === 'portrait' ? 'verticale' : 'orizzontale';
        const file = $('printFileType').value.toUpperCase();
        $('printActiveFrame').textContent = state.loadingFrame ? 'Caricamento...'
            : state.frameError ? 'Cornice non disponibile' : (state.frame?.name || 'Nessuna');
        $('printPreset').disabled = !!state.frame;
        $('printOrientation').disabled = !!state.frame;
        $('printExportSummary').textContent = `${format} · ${direction} · ${file}`;
        $('printExport').textContent = `Esporta ${file}`;
        $('printExport').disabled = !state.basePixels || state.loadingFrame || state.frameError
            || state.exporting || !state.item;
        // Direct printing is measured for P only; one print at a time.
        $('printDirect').disabled = $('printExport').disabled || state.printing || state.preset !== 'P';
        $('printDirect').title = state.preset === 'P' ? '' : 'Stampa diretta per ora solo nel formato P';
    }

    function status(message, error = false) {
        const element = $('printEditorStatus');
        element.textContent = message;
        element.classList.toggle('print-editor-status-error', error);
    }

    async function jsonResponse(response) {
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
        return data;
    }

    function loadImage(url) {
        return new Promise((resolve, reject) => {
            const image = new Image();
            image.onload = () => resolve(image);
            image.onerror = () => reject(new Error('Impossibile caricare l’immagine.'));
            image.src = url;
        });
    }

    function presetRatio() {
        const config = state.presets[state.preset];
        if (!config) return 1.48;
        const pair = config.mm || config.ratio;
        if (!pair) {
            return state.adjusted.width && state.adjusted.height
                ? state.adjusted.width / state.adjusted.height : 1.48;
        }
        const longSide = Math.max(...pair);
        const shortSide = Math.min(...pair);
        if (longSide === shortSide) return 1;
        return state.orientation === 'landscape' ? longSide / shortSide : shortSide / longSide;
    }

    function resetPosition() {
        state.zoom = 1;
        state.offsetX = 0;
        state.offsetY = 0;
        state.rotation = 0;
        updatePositionLabels();
        changed();
        draw();
    }

    function updatePositionLabels() {
        $('printZoom').value = state.zoom;
        $('printRotation').value = state.rotation;
        $('printZoomValue').textContent = `${state.zoom.toFixed(2).replace('.', ',')}×`;
        $('printRotationValue').textContent = `${Math.round(state.rotation)}°`;
    }

    function updateLightLabels() {
        for (const [key, value] of [
            ['Exposure', state.exposure], ['Shadows', state.shadows],
            ['Highlights', state.highlights],
        ]) {
            $(`print${key}Value`).textContent = value.toFixed(2).replace('.', ',');
        }
        for (const [key, value] of [
            ['Contrast', state.contrast], ['Temperature', state.temperature],
            ['Tint', state.tint], ['Vibrance', state.vibrance],
            ['Saturation', state.saturation], ['LuminanceNoise', state.luminanceNoise],
        ]) {
            $(`print${key}Value`).textContent = `${value > 0 && key !== 'LuminanceNoise' ? '+' : ''}${value}`;
        }
    }

    function clampByte(value) {
        return Math.round(Math.max(0, Math.min(255, value)));
    }

    function tunePreview() {
        state.updateQueued = false;
        if (!state.basePixels) return;
        const source = state.basePixels;
        const output = new ImageData(new Uint8ClampedArray(source.data), source.width, source.height);
        const lut = new Uint8Array(256);
        const channels = [new Uint8Array(256), new Uint8Array(256), new Uint8Array(256)];
        const contrast = state.contrast / 100;
        const temperature = state.temperature / 100;
        const tint = state.tint / 100;
        const gains = [1 + temperature * 0.15 + tint * 0.08,
            1 - tint * 0.16, 1 - temperature * 0.15 + tint * 0.08];
        for (let level = 0; level < 256; level++) {
            let value = Math.pow(Math.pow(level / 255, 2.2) * Math.pow(2, state.exposure), 1 / 2.2);
            value = Math.min(1, value);
            value += state.shadows * 0.30 * Math.pow(1 - value, 2);
            value += state.highlights * 0.30 * Math.pow(value, 2);
            lut[level] = Math.round(Math.max(0, Math.min(1, value)) * 255);
            for (let channel = 0; channel < 3; channel++) {
                channels[channel][level] = clampByte(((level - 127.5) * (1 + contrast) + 127.5) * gains[channel]);
            }
        }
        const saturation = state.saturation / 100;
        const vibrance = state.vibrance / 100;
        for (let index = 0; index < output.data.length; index += 4) {
            let red = channels[0][lut[source.data[index]]];
            let green = channels[1][lut[source.data[index + 1]]];
            let blue = channels[2][lut[source.data[index + 2]]];
            if (saturation) {
                const gray = Math.round(red * 0.299 + green * 0.587 + blue * 0.114);
                red = clampByte(gray + (red - gray) * (1 + saturation));
                green = clampByte(gray + (green - gray) * (1 + saturation));
                blue = clampByte(gray + (blue - gray) * (1 + saturation));
            }
            if (vibrance) {
                const gray = Math.round(red * 0.299 + green * 0.587 + blue * 0.114);
                const lowColor = 1 - (Math.max(red, green, blue) - Math.min(red, green, blue)) / 255;
                const factor = 1 + vibrance * lowColor;
                red = clampByte(gray + (red - gray) * factor);
                green = clampByte(gray + (green - gray) * factor);
                blue = clampByte(gray + (blue - gray) * factor);
            }
            output.data[index] = red;
            output.data[index + 1] = green;
            output.data[index + 2] = blue;
        }
        if (state.luminanceNoise) denoisePreview(output);
        state.adjusted.getContext('2d').putImageData(output, 0, 0);
        state.frameThumbs.forEach(drawFrameThumb);
        updateLightLabels();
        changed();
        draw();
    }

    function queueTunePreview() {
        if (state.updateQueued) return;
        state.updateQueued = true;
        requestAnimationFrame(tunePreview);
    }

    function wrapRotation(degrees) {
        return ((degrees + 180) % 360 + 360) % 360 - 180;
    }

    function visibleEdges() {
        const width = canvas.width;
        const height = canvas.height;
        const cached = state.coverageMask;
        if (cached && cached.frame === state.frameImage && cached.width === width && cached.height === height) {
            return cached.points;
        }
        let points;
        if (!state.frameImage) {
            points = [[0, 0], [width, 0], [0, height], [width, height]];
        } else {
            const mask = document.createElement('canvas');
            mask.width = width;
            mask.height = height;
            const maskContext = mask.getContext('2d', {willReadFrequently: true});
            maskContext.drawImage(state.frameImage, 0, 0, width, height);
            const pixels = maskContext.getImageData(0, 0, width, height).data;
            points = [];
            for (let y = 0; y < height; y++) {
                let left = width;
                let right = -1;
                for (let x = 0; x < width; x++) {
                    if (pixels[(y * width + x) * 4 + 3] < 223) {
                        left = Math.min(left, x);
                        right = x;
                    }
                }
                if (right >= 0) points.push(
                    [left, y], [right + 1, y], [left, y + 1], [right + 1, y + 1]);
            }
        }
        state.coverageMask = {frame: state.frameImage, width, height, points};
        return points;
    }

    function coversVisibleArea(transform) {
        if (!state.adjusted.width || !canvas.width) return false;
        const width = canvas.width;
        const height = canvas.height;
        const imageWidth = state.adjusted.width;
        const imageHeight = state.adjusted.height;
        const scale = Math.max(width / imageWidth, height / imageHeight) * transform.zoom;
        const radians = transform.rotation * Math.PI / 180;
        const cosine = Math.cos(radians);
        const sine = Math.sin(radians);
        const centerX = width * (0.5 + transform.offsetX);
        const centerY = height * (0.5 + transform.offsetY);
        const margin = state.frameImage ? 2 : 0;
        for (const [x, y] of visibleEdges()) {
            const dx = x - centerX;
            const dy = y - centerY;
            const sourceX = imageWidth / 2 + (cosine * dx + sine * dy) / scale;
            const sourceY = imageHeight / 2 + (-sine * dx + cosine * dy) / scale;
            if (sourceX < margin - 0.01 || sourceX > imageWidth - margin + 0.01
                || sourceY < margin - 0.01 || sourceY > imageHeight - margin + 0.01) return false;
        }
        return true;
    }

    function applyTransform(next) {
        const before = {
            zoom: state.zoom, rotation: state.rotation,
            offsetX: state.offsetX, offsetY: state.offsetY,
        };
        let target = next;
        if (!coversVisibleArea(target)) {
            let valid = 0;
            let invalid = 1;
            for (let attempt = 0; attempt < 12; attempt++) {
                const fraction = (valid + invalid) / 2;
                const candidate = {
                    zoom: before.zoom + (next.zoom - before.zoom) * fraction,
                    rotation: wrapRotation(before.rotation + wrapRotation(next.rotation - before.rotation) * fraction),
                    offsetX: before.offsetX + (next.offsetX - before.offsetX) * fraction,
                    offsetY: before.offsetY + (next.offsetY - before.offsetY) * fraction,
                };
                if (coversVisibleArea(candidate)) valid = fraction;
                else invalid = fraction;
            }
            target = {
                zoom: before.zoom + (next.zoom - before.zoom) * valid,
                rotation: wrapRotation(before.rotation + wrapRotation(next.rotation - before.rotation) * valid),
                offsetX: before.offsetX + (next.offsetX - before.offsetX) * valid,
                offsetY: before.offsetY + (next.offsetY - before.offsetY) * valid,
            };
            status('Limite della cornice raggiunto. Ingrandisci la foto per muoverla o ruotarla di più.');
        }
        if (Object.keys(before).every((key) => Math.abs(before[key] - target[key]) < 0.00001)) {
            updatePositionLabels();
            return;
        }
        Object.assign(state, target);
        updatePositionLabels();
        changed();
        draw();
    }

    function draw() {
        if (!state.adjusted.width || $('printEditor').hidden) return;
        const ratio = presetRatio();
        const width = ratio >= 1 ? 900 : Math.round(900 * ratio);
        const height = ratio >= 1 ? Math.round(900 / ratio) : 900;
        if (canvas.width !== width || canvas.height !== height) {
            canvas.width = width;
            canvas.height = height;
        }
        context.fillStyle = '#ffffff';
        context.fillRect(0, 0, width, height);
        const imageWidth = state.adjusted.width;
        const imageHeight = state.adjusted.height;
        const scale = Math.max(width / imageWidth, height / imageHeight) * state.zoom;
        context.save();
        context.translate(width * (0.5 + state.offsetX), height * (0.5 + state.offsetY));
        context.rotate(state.rotation * Math.PI / 180);
        context.scale(scale, scale);
        context.drawImage(state.adjusted, -imageWidth / 2, -imageHeight / 2);
        context.restore();
        if (state.frameImage) context.drawImage(state.frameImage, 0, 0, width, height);
    }

    function denoisePreview(pixels) {
        const {width, height} = pixels;
        const original = pixels.data;
        const luminance = new Float32Array(width * height);
        const horizontal = new Float32Array(width * height);
        for (let position = 0; position < luminance.length; position++) {
            const index = position * 4;
            luminance[position] = original[index] * 0.299 + original[index + 1] * 0.587
                + original[index + 2] * 0.114;
        }
        for (let y = 0; y < height; y++) {
            for (let x = 2; x < width - 2; x++) {
                const position = y * width + x;
                horizontal[position] = (luminance[position - 2] + 4 * luminance[position - 1]
                    + 6 * luminance[position] + 4 * luminance[position + 1]
                    + luminance[position + 2]) / 16;
            }
        }
        const strength = state.luminanceNoise / 100;
        for (let y = 2; y < height - 2; y++) {
            for (let x = 2; x < width - 2; x++) {
                const position = y * width + x;
                const blurred = (horizontal[position - 2 * width] + 4 * horizontal[position - width]
                    + 6 * horizontal[position] + 4 * horizontal[position + width]
                    + horizontal[position + 2 * width]) / 16;
                const correction = (blurred - luminance[position]) * strength;
                const index = position * 4;
                for (let channel = 0; channel < 3; channel++) {
                    pixels.data[index + channel] = clampByte(original[index + channel] + correction);
                }
            }
        }
    }

    function step(number) {
        state.step = number;
        $('printStepFrames').hidden = number !== 2;
        $('printStepManage').hidden = number !== 3;
        draw();
    }

    function badge(frame) {
        const config = state.presets[frame.preset] || {};
        const pair = config.mm;
        const size = pair ? ` · ${Math.min(...pair)} × ${Math.max(...pair)} mm` : '';
        return `${config.label || frame.preset}${size} · ${frame.orientation === 'portrait' ? 'verticale' : 'orizzontale'}`;
    }

    function renderCollections() {
        const select = $('printCollectionFilter');
        const selected = select.value;
        select.replaceChildren(new Option('Tutte le collezioni', ''));
        const collections = [...new Set(state.frames.map((frame) => frame.collection))].sort();
        for (const collection of collections) select.add(new Option(collection, collection));
        select.value = collections.includes(selected) ? selected : '';
        $('printCollectionFilterLabel').hidden = collections.length < 2;
    }

    // Manage step only: shows name, collection and transparency for deletion.
    function frameCard(frame) {
        const card = document.createElement('div');
        card.className = 'print-frame-card';
        const preview = document.createElement('img');
        preview.src = frame.thumbnail_url;
        preview.alt = '';
        card.append(preview);
        const title = document.createElement('span');
        title.className = 'print-frame-title';
        title.textContent = frame.name;
        card.append(title);
        const tag = document.createElement('span');
        tag.className = 'print-frame-badge';
        tag.textContent = badge(frame);
        card.append(tag);
        const collection = document.createElement('span');
        collection.className = 'print-frame-collection';
        collection.textContent = frame.collection;
        card.append(collection);
        return card;
    }

    // Cover-fit and centred, like the main preview at 1×.
    function drawFrameThumb(thumb) {
        const source = state.adjusted;
        if (!source.width) return;
        const scale = Math.max(thumb.width / source.width, thumb.height / source.height);
        const width = source.width * scale;
        const height = source.height * scale;
        thumb.getContext('2d').drawImage(source, (thumb.width - width) / 2,
            (thumb.height - height) / 2, width, height);
    }

    // Carousel card: the current photo under the frame thumbnail, format only.
    function frameOption(frame) {
        const card = document.createElement('div');
        card.className = 'print-frame-option';
        const box = document.createElement('span');
        box.className = 'print-frame-thumb';
        const thumb = document.createElement('canvas');
        thumb.height = 240;
        // "No frame" keeps the photo's own shape so cards never shift when choosing.
        const photoRatio = state.adjusted.width ? state.adjusted.width / state.adjusted.height : 1;
        thumb.width = Math.round(240 * (frame ? frame.width / frame.height : photoRatio));
        drawFrameThumb(thumb);
        state.frameThumbs.push(thumb);
        box.append(thumb);
        if (frame) {
            const overlay = document.createElement('img');
            overlay.src = frame.thumbnail_url;
            overlay.alt = '';
            box.append(overlay);
        }
        const format = document.createElement('span');
        format.className = 'print-frame-format';
        format.textContent = frame
            ? `${frame.preset} · ${frame.orientation === 'portrait' ? 'verticale' : 'orizzontale'}`
            : 'Senza cornice';
        card.append(box, format);
        card.setAttribute('aria-label', frame ? `${frame.name}, ${format.textContent}` : format.textContent);
        return card;
    }

    // The frame step only chooses; uploads and deletions live in the manage step.
    function renderGallery() {
        const gallery = $('printFrameGallery');
        const focused = [...gallery.children].indexOf(document.activeElement);
        gallery.replaceChildren();
        state.frameThumbs = [];
        const filter = $('printCollectionFilter').value;
        const entries = [null, ...state.frames.filter((frame) => !filter || frame.collection === filter)];
        for (const frame of entries) {
            const card = frameOption(frame);
            const active = state.frame?.id === frame?.id;
            card.setAttribute('role', 'button');
            card.setAttribute('aria-pressed', String(active));
            card.tabIndex = 0;
            card.classList.toggle('active', active);
            card.addEventListener('click', () => chooseFrame(frame));
            card.addEventListener('keydown', (event) => {
                if (event.target !== card) return;
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    chooseFrame(frame);
                } else if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
                    event.preventDefault();
                    (event.key === 'ArrowRight' ? card.nextElementSibling : card.previousElementSibling)?.focus();
                }
            });
            gallery.append(card);
        }
        // Rebuilding drops keyboard focus; put it back on the same card.
        gallery.children[focused]?.focus();
        const list = $('printFrameManageList');
        list.replaceChildren();
        if (!state.frames.length) {
            const empty = document.createElement('p');
            empty.className = 'print-muted';
            empty.textContent = 'Nessuna cornice caricata.';
            list.append(empty);
        }
        for (const frame of state.frames) {
            const card = frameCard(frame);
            const remove = document.createElement('button');
            remove.type = 'button';
            remove.className = 'print-frame-delete';
            remove.textContent = 'Elimina cornice';
            remove.addEventListener('click', () => deleteFrame(frame));
            card.append(remove);
            list.append(card);
        }
    }

    async function chooseFrame(frame) {
        const token = state.openToken;
        const previousRatio = presetRatio();
        state.frame = frame;
        state.frameImage = null;
        state.loadingFrame = !!frame;
        state.frameError = false;
        if (!frame) {
            state.preset = 'original';
            state.orientation = state.adjusted.width >= state.adjusted.height
                ? 'landscape' : 'portrait';
            $('printPreset').value = state.preset;
            $('printOrientation').value = state.orientation;
        }
        changed();
        updateExportUi();
        if (frame) {
            state.preset = frame.preset;
            state.orientation = frame.orientation;
            $('printPreset').value = frame.preset;
            $('printOrientation').value = frame.orientation;
            try {
                const image = await loadImage(frame.url);
                if (state.openToken !== token || state.frame !== frame) return;
                state.frameImage = image;
            } catch (error) {
                if (state.openToken !== token || state.frame !== frame) return;
                state.frame = null;
                state.frameError = true;
                status(`Cornice non caricata: ${error.message} Scegline un'altra o seleziona Nessuna cornice.`, true);
            }
        }
        state.loadingFrame = false;
        if (!state.frameError) rememberFrame(state.frame);
        if (Math.abs(presetRatio() - previousRatio) > 0.001) resetPosition();
        updateExportUi();
        renderGallery();
        draw();
        if (!coversVisibleArea(state)) resetPosition();
        return !state.frameError;
    }

    async function deleteFrame(frame) {
        if (!confirm(`Eliminare la cornice “${frame.name}”? Le esportazioni già salvate resteranno disponibili.`)) return;
        try {
            await jsonResponse(await fetch(`/api/print/frames/${frame.id}`, {method: 'DELETE'}));
            if (state.frame?.id === frame.id) {
                state.frame = null;
                state.frameImage = null;
                rememberFrame(null);
            }
            await refreshFrames();
            changed();
            updateExportUi();
            draw();
        } catch (error) {
            status(error.message, true);
        }
    }

    async function refreshFrames() {
        state.frames = (await jsonResponse(await fetch('/api/print/frames'))).frames;
        renderCollections();
        renderGallery();
    }

    function updatePreset() {
        state.preset = $('printPreset').value;
        state.orientation = $('printOrientation').value;
        if (state.frame && (state.frame.preset !== state.preset || state.frame.orientation !== state.orientation)) {
            state.frame = null;
            state.frameImage = null;
        }
        resetPosition();
        changed();
        updateExportUi();
        renderGallery();
    }

    async function open(item) {
        const token = ++state.openToken;
        state.item = item;
        state.frame = null;
        state.frameImage = null;
        state.basePixels = null;
        state.loadingFrame = false;
        state.frameError = false;
        state.exporting = false;
        state.printing = false;
        state.adjusted.width = 0;
        state.exposure = state.shadows = state.highlights = 0;
        state.contrast = state.temperature = state.tint = 0;
        state.vibrance = state.saturation = state.luminanceNoise = 0;
        state.preset = 'P';
        state.orientation = 'landscape';
        $('printFileType').value = 'jpg';
        $('printStepLights').open = false;
        $('printExportOptions').open = false;
        changed();
        for (const key of ['Exposure', 'Shadows', 'Highlights', 'Contrast', 'Temperature',
            'Tint', 'Vibrance', 'Saturation', 'LuminanceNoise']) $(`print${key}`).value = 0;
        updateLightLabels();
        resetPosition();
        $('printEditorName').textContent = item.name;
        $('printEditor').hidden = false;
        document.body.style.overflow = 'hidden';
        step(2);
        updateExportUi();
        status('Preparazione anteprima dalla foto originale...');
        try {
            const [presetData, frameData, preview] = await Promise.all([
                jsonResponse(await fetch('/api/print/presets')),
                jsonResponse(await fetch('/api/print/frames')),
                loadImage(`/api/print/editor-preview/${item.id}`),
            ]);
            if (state.openToken !== token) return;
            state.presets = presetData.presets;
            state.frames = frameData.frames;
            const presets = Object.entries(state.presets);
            $('printPreset').replaceChildren(
                ...presets.map(([key, config]) => new Option(config.label, key))
            );
            $('printUploadPreset').replaceChildren(
                ...presets.filter(([key]) => key !== 'original')
                    .map(([key, config]) => new Option(config.label, key))
            );
            $('printPreset').value = 'P';
            $('printUploadPreset').value = 'P';
            $('printOrientation').value = 'landscape';
            state.sourceImage = preview;
            const factor = Math.min(1, 1400 / Math.max(preview.width, preview.height));
            state.adjusted.width = Math.round(preview.width * factor);
            state.adjusted.height = Math.round(preview.height * factor);
            const adjustedContext = state.adjusted.getContext('2d', {willReadFrequently: true});
            adjustedContext.drawImage(preview, 0, 0, state.adjusted.width, state.adjusted.height);
            state.basePixels = adjustedContext.getImageData(0, 0, state.adjusted.width, state.adjusted.height);
            renderCollections();
            renderGallery();
            tunePreview();
            const remembered = savedFrameId();
            const preferred = state.frames.find((frame) => frame.id === remembered)
                || (remembered !== 'none' && state.frames.length === 1 ? state.frames[0] : null);
            const frameReady = await chooseFrame(preferred || null);
            if (state.openToken !== token) return;
            updateExportUi();
            if (frameReady) status('Pronta per la stampa. Controlla l’inquadratura e scarica il file.');
        } catch (error) {
            if (state.openToken !== token) return;
            status(error.message, true);
        }
    }

    function close() {
        state.openToken++;
        $('printEditor').hidden = true;
        document.body.style.overflow = '';
        state.item = null;
        state.loadingFrame = false;
        state.exporting = false;
        state.printing = false;
        state.pointers.clear();
        state.gesture = null;
        $('modal').classList.add('open');
    }

    async function uploadFrame(event) {
        event.preventDefault();
        const form = $('printFrameUpload');
        const button = form.querySelector('button[type=submit]');
        button.disabled = true;
        status('Caricamento della cornice...');
        try {
            const frame = await jsonResponse(await fetch('/api/print/frames', {
                method: 'POST', body: new FormData(form),
            }));
            await refreshFrames();
            const selected = await chooseFrame(frame);
            form.querySelector('input[type=file]').value = '';
            if (selected) status('Cornice caricata e selezionata.');
        } catch (error) {
            status(error.message, true);
        } finally {
            button.disabled = false;
        }
    }

    function exportPayload(fileType) {
        return {
            id: state.item.id, preset: state.preset,
            orientation: state.orientation,
            file_type: fileType,
            frame_id: state.frame?.id || null,
            exposure: state.exposure, shadows: state.shadows,
            highlights: state.highlights, contrast: state.contrast,
            temperature: state.temperature, tint: state.tint,
            vibrance: state.vibrance, saturation: state.saturation,
            luminance_noise: state.luminanceNoise, zoom: state.zoom,
            offset_x: state.offsetX, offset_y: state.offsetY,
            rotation: state.rotation,
        };
    }

    // Stampa: the same picture as Esporta, saved in Review, sent to the SELPHY
    // instead of downloaded; then the job is followed until it ends.
    async function printPhoto() {
        if (!state.item || !state.basePixels || state.loadingFrame || state.exporting || state.printing) return;
        const token = state.openToken;
        state.exporting = true;
        state.printing = true;
        updateExportUi();
        status('Preparazione della stampa sul Raspberry...');
        try {
            const result = await jsonResponse(await fetch('/api/print/print', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(exportPayload('jpg')),
            }));
            if (state.openToken !== token) return;
            state.exporting = false;
            updateExportUi();
            const saved = result.beside_original
                ? ` Salvata accanto all'originale: ${result.beside_original}.` : '';
            status(`Inviata alla stampante.${saved}`);
            await followPrint(result.job_id, token, saved);
        } catch (error) {
            if (state.openToken === token) status(error.message, true);
        } finally {
            if (state.openToken === token) {
                state.exporting = false;
                state.printing = false;
                updateExportUi();
            }
        }
    }

    async function followPrint(jobId, token, saved) {
        if (jobId == null) return;
        const until = Date.now() + 5 * 60 * 1000;
        while (Date.now() < until && state.openToken === token) {
            await new Promise((resolve) => setTimeout(resolve, 3000));
            let report;
            try {
                report = await jsonResponse(await fetch(`/api/print/jobs/${jobId}`, {cache: 'no-store'}));
            } catch (_) {
                continue; // a missed status poll is retried, not reported
            }
            if (state.openToken !== token) return;
            status(report.message + (report.done ? saved : ''), report.done && report.ok === false);
            if (report.done) return;
        }
    }

    async function exportPhoto() {
        if (!state.item || !state.basePixels || state.loadingFrame || state.exporting) return;
        const token = state.openToken;
        const item = state.item;
        const button = $('printExport');
        state.exporting = true;
        button.disabled = true;
        changed();
        const revision = state.revision;
        status('Esportazione ad alta qualità in corso sul Raspberry...');
        try {
            const result = await jsonResponse(await fetch('/api/print/export', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(exportPayload($('printFileType').value)),
            }));
            if (state.openToken !== token || state.item !== item) return;
            const link = document.createElement('a');
            link.href = result.download_url;
            link.download = result.name;
            document.body.append(link);
            link.click();
            link.remove();
            const changedDuringExport = state.revision !== revision;
            $('printExportResultText').textContent = `${changedDuringExport ? 'Versione precedente' : 'Pronta'}: ${result.name} · ${result.width} × ${result.height} px`;
            $('printRedownload').href = result.download_url;
            $('printRedownload').download = result.name;
            $('printExportResult').hidden = false;
            status(changedDuringExport
                ? 'Download avviato con le impostazioni precedenti. Esporta di nuovo le ultime modifiche.'
                : `Salvata: ${result.name} · ${result.width} × ${result.height} px`
                  + (result.beside_original ? `, copia accanto all'originale: ${result.beside_original}` : '')
                  + '. Download avviato.');
        } catch (error) {
            if (state.openToken === token) status(error.message, true);
        } finally {
            if (state.openToken === token) {
                state.exporting = false;
                updateExportUi();
            }
        }
    }

    for (const [id, key] of [
        ['printExposure', 'exposure'], ['printShadows', 'shadows'],
        ['printHighlights', 'highlights'], ['printContrast', 'contrast'],
        ['printTemperature', 'temperature'], ['printTint', 'tint'],
        ['printVibrance', 'vibrance'], ['printSaturation', 'saturation'],
        ['printLuminanceNoise', 'luminanceNoise'],
    ]) {
        $(id).addEventListener('input', (event) => {
            state[key] = Number(event.target.value);
            queueTunePreview();
        });
    }
    // On touch screens the native slider jumps to any finger that lands on it, even mid-scroll.
    // CSS hands those touches to the label; here only a sideways drag moves the value.
    for (const slider of document.querySelectorAll('.print-controls input[type=range]')) {
        const row = slider.parentElement;
        let drag = null;
        row.style.touchAction = 'pan-y';
        row.addEventListener('pointerdown', (event) => {
            if (event.target === slider) return;
            const box = slider.getBoundingClientRect();
            if (event.clientY < box.top - 12 || event.clientY > box.bottom + 12) return;
            drag = {id: event.pointerId, x: event.clientX, y: event.clientY,
                value: Number(slider.value), sliding: false};
        });
        row.addEventListener('pointermove', (event) => {
            if (!drag || event.pointerId !== drag.id) return;
            const dx = event.clientX - drag.x;
            if (!drag.sliding) {
                const dy = event.clientY - drag.y;
                if (Math.abs(dy) >= Math.abs(dx) && Math.abs(dy) >= 10) drag = null;
                if (!drag || Math.abs(dx) < 10) return;
                drag.sliding = true;
                row.setPointerCapture(event.pointerId);
            }
            slider.value = drag.value + dx / slider.getBoundingClientRect().width * (slider.max - slider.min);
            slider.dispatchEvent(new Event('input', {bubbles: true}));
        });
        for (const type of ['pointerup', 'pointercancel']) row.addEventListener(type, () => { drag = null; });
    }
    $('printResetLights').addEventListener('click', () => {
        state.exposure = state.shadows = state.highlights = 0;
        state.contrast = state.temperature = state.tint = 0;
        state.vibrance = state.saturation = state.luminanceNoise = 0;
        for (const key of ['Exposure', 'Shadows', 'Highlights', 'Contrast', 'Temperature',
            'Tint', 'Vibrance', 'Saturation', 'LuminanceNoise']) $(`print${key}`).value = 0;
        queueTunePreview();
    });
    $('printManageFrames').addEventListener('click', () => step(3));
    $('printManageDone').addEventListener('click', () => step(2));
    $('printRotate90').addEventListener('click', () => {
        const next = {zoom: state.zoom, rotation: wrapRotation(state.rotation + 90),
            offsetX: state.offsetX, offsetY: state.offsetY};
        if (!coversVisibleArea(next)) {
            status('Per ruotare di 90°, ingrandisci prima la foto.');
            return;
        }
        applyTransform(next);
    });
    $('printEditorClose').addEventListener('click', close);
    $('printResetPosition').addEventListener('click', resetPosition);
    $('printExport').addEventListener('click', exportPhoto);
    $('printDirect').addEventListener('click', printPhoto);
    $('printFrameUpload').addEventListener('submit', uploadFrame);
    $('printCollectionFilter').addEventListener('change', renderGallery);
    // A vertical mouse wheel scrolls the carousel sideways, then hands back to the page.
    $('printFrameGallery').addEventListener('wheel', (event) => {
        const gallery = event.currentTarget;
        if (Math.abs(event.deltaX) >= Math.abs(event.deltaY)) return;
        const end = gallery.scrollWidth - gallery.clientWidth;
        const delta = event.deltaMode === 1 ? event.deltaY * 16 : event.deltaY;
        const next = Math.max(0, Math.min(end, gallery.scrollLeft + delta));
        if (next === gallery.scrollLeft) return;
        event.preventDefault();
        gallery.scrollLeft = next;
    }, {passive: false});
    $('printPreset').addEventListener('change', updatePreset);
    $('printOrientation').addEventListener('change', updatePreset);
    $('printFileType').addEventListener('change', () => { changed(); updateExportUi(); });
    $('printZoom').addEventListener('input', (event) => {
        applyTransform({zoom: Number(event.target.value), rotation: state.rotation,
            offsetX: state.offsetX, offsetY: state.offsetY});
    });
    $('printRotation').addEventListener('input', (event) => {
        applyTransform({zoom: state.zoom, rotation: Number(event.target.value),
            offsetX: state.offsetX, offsetY: state.offsetY});
    });
    canvas.addEventListener('pointerdown', (event) => {
        if (state.step !== 2 || state.pointers.size >= 2) return;
        canvas.setPointerCapture(event.pointerId);
        state.pointers.set(event.pointerId, {x: event.clientX, y: event.clientY});
        if (state.pointers.size === 2) {
            const [first, second] = [...state.pointers.values()];
            state.gesture = {
                distance: Math.hypot(second.x - first.x, second.y - first.y),
                angle: Math.atan2(second.y - first.y, second.x - first.x),
                centerX: (first.x + second.x) / 2,
                centerY: (first.y + second.y) / 2,
                zoom: state.zoom, rotation: state.rotation,
                offsetX: state.offsetX, offsetY: state.offsetY,
            };
        }
    });
    canvas.addEventListener('pointermove', (event) => {
        if (!state.pointers.has(event.pointerId) || state.step !== 2) return;
        const previous = state.pointers.get(event.pointerId);
        if (event.clientX === previous.x && event.clientY === previous.y) return;
        const bounds = canvas.getBoundingClientRect();
        state.pointers.set(event.pointerId, {x: event.clientX, y: event.clientY});
        let next;
        if (state.pointers.size === 1) {
            next = {
                zoom: state.zoom, rotation: state.rotation,
                offsetX: state.offsetX + (event.clientX - previous.x) / bounds.width,
                offsetY: state.offsetY + (event.clientY - previous.y) / bounds.height,
            };
        } else if (state.gesture) {
            const [first, second] = [...state.pointers.values()];
            const gesture = state.gesture;
            const centerX = (first.x + second.x) / 2;
            const centerY = (first.y + second.y) / 2;
            next = {
                zoom: state.zoom, rotation: state.rotation,
                offsetX: gesture.offsetX + (centerX - gesture.centerX) / bounds.width,
                offsetY: gesture.offsetY + (centerY - gesture.centerY) / bounds.height,
            };
            if (gesture.distance > 8) {
                const distance = Math.hypot(second.x - first.x, second.y - first.y);
                next.zoom = Math.max(1, Math.min(6, gesture.zoom * distance / gesture.distance));
                const angle = Math.atan2(second.y - first.y, second.x - first.x);
                next.rotation = wrapRotation(gesture.rotation + (angle - gesture.angle) * 180 / Math.PI);
            }
        }
        if (next) applyTransform(next);
    });
    for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) {
        canvas.addEventListener(type, (event) => {
            state.pointers.delete(event.pointerId);
            if (state.pointers.size < 2) state.gesture = null;
        });
    }
    canvas.addEventListener('wheel', (event) => {
        if (state.step !== 2) return;
        event.preventDefault();
        applyTransform({zoom: Math.max(1, Math.min(6, state.zoom * (event.deltaY < 0 ? 1.08 : 0.92))),
            rotation: state.rotation, offsetX: state.offsetX, offsetY: state.offsetY});
    }, {passive: false});
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && !$('printEditor').hidden) close();
    });

    window.NiwaPrintEditor = {open};
})();
