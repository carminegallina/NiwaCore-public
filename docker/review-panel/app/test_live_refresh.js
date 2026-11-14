/* Copyright (c) 2026 Carmine Gallina - https://github.com/carminegallina */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(`${__dirname}/app.py`, 'utf8');
const functionSource = (name, next)=>{
    const functionStart = source.indexOf(`function ${name}(`);
    const functionEnd = source.indexOf(`function ${next}(`, functionStart);
    assert.ok(functionStart >= 0 && functionEnd > functionStart, `${name} function found`);
    return source.slice(functionStart, functionEnd);
};
for(const [name, next] of [
    ['fillMediaCard', 'setLabeledStatus'],
    ['setLabeledStatus', 'itemCard'],
    ['itemCard', 'renderLoadMore'],
    ['trashCard', 'setTrashCount'],
    ['incomingCard', 'loadIncoming']
]){
    const body = functionSource(name, next);
    assert.doesNotMatch(body, /innerHTML/, `${name} does not parse media names as HTML`);
}
assert.match(functionSource('fillMediaCard', 'setLabeledStatus'), /textContent/,
    'media metadata is inserted as text');
const suffixLine = source.match(/const SAME_NAME_SUFFIX = .*;/)[0];
const sameName = vm.runInNewContext(`${suffixLine} SAME_NAME_SUFFIX`);
for(const [name, shown] of [
    ['_DSC7969_conflict_9e92b859.NEF', '_DSC7969.NEF'],
    ['_DSC7969_conflict_9e92b859_2.NEF', '_DSC7969.NEF'],
    ['_DSC7969.NEF', '_DSC7969.NEF'],
    ['my_conflict_notes.JPG', 'my_conflict_notes.JPG']
]){
    assert.equal(name.replace(sameName, ''), shown, `${name} is shown as ${shown}`);
}
const start = source.indexOf('async function refreshLivePhotos(){');
const end = source.indexOf('async function loadIndexStatus(){', start);
assert.ok(start >= 0 && end > start, 'refreshLivePhotos function found');

let requests = 0;
let reloads = 0;
let items = [{id: 'old'}];
const status = {textContent: ''};
const context = vm.createContext({
    LIVE_REFRESH_BUSY: false,
    CURRENT_SECTION: 'photo',
    PHOTO_FILTER: 'all',
    CURRENT_PAGE: 1,
    SELECTING: false,
    LOAD_SEQUENCE: 0,
    PAGE_SIZE: 80,
    PHOTOS: [{id: 'old'}],
    TOTAL_ITEMS: 1,
    LAST_MEDIA_STATUS: '1/1 file caricati',
    LIVE_REFRESH_TOP: 300,
    window: {scrollY: 0},
    document: {
        visibilityState: 'visible',
        getElementById: (id)=>id === 'status' ? status : {
            classList: {contains: ()=>false}
        }
    },
    fetch: async ()=>{
        requests++;
        return {ok: true, json: async ()=>({
            items,
            pagination: {total: items.length}
        })};
    },
    loadMedia: async ()=>{ reloads++; }
});
vm.runInContext(source.slice(start, end), context);

(async ()=>{
    await vm.runInContext('refreshLivePhotos()', context);
    assert.equal(reloads, 0, 'unchanged gallery does not reload');
    assert.equal(status.textContent, '1/1 file caricati', 'successful poll clears an old error');

    items = [{id: 'new'}, {id: 'old'}];
    await vm.runInContext('refreshLivePhotos()', context);
    assert.equal(reloads, 1, 'new photo reloads the gallery');

    // Three pages loaded, first page unchanged: no reload.
    context.PHOTOS = [{id: 'new'}, {id: 'old'}, {id: 'page2'}, {id: 'page3'}];
    context.TOTAL_ITEMS = 2;
    await vm.runInContext('refreshLivePhotos()', context);
    assert.equal(reloads, 1, 'later pages do not count as a change');

    context.window.scrollY = 2000;
    await vm.runInContext('refreshLivePhotos()', context);
    assert.equal(requests, 3, 'deep in the grid the gallery is left alone');
    context.window.scrollY = 0;

    context.SELECTING = true;
    await vm.runInContext('refreshLivePhotos()', context);
    assert.equal(requests, 3, 'selection mode does not poll');

    // Load more: one page at a time, a failed page is not skipped.
    const more = vm.createContext({
        HAS_MORE: true, LOADING_MORE: false, CURRENT_PAGE: 1, pages: [], ok: true, near: false,
        window: {innerHeight: 800},
        document: {getElementById: ()=>({getBoundingClientRect: ()=>({top: more.near ? 100 : 5000})})}
    });
    vm.runInContext(source.slice(source.indexOf('async function loadMoreMedia('),
        source.indexOf('async function refreshLivePhotos(')) +
        'async function loadMedia(){ pages.push(CURRENT_PAGE); await null; return ok; }', more);
    await Promise.all([vm.runInContext('loadMoreMedia()', more), vm.runInContext('loadMoreMedia()', more)]);
    assert.deepEqual(more.pages, [2], 'a second trigger while loading is ignored');
    more.ok = false;
    await vm.runInContext('loadMoreMedia()', more);
    assert.equal(more.CURRENT_PAGE, 2, 'a failed page is rolled back, not skipped');
    assert.deepEqual(more.pages, [2, 3], 'a failure does not retry in a loop');
})().catch((error)=>{
    console.error(error);
    process.exitCode = 1;
});
