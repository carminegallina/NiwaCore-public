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
    ['trashCard', 'setTrashCount']
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
    CURRENT_PAGE: 1,
    SELECTING: false,
    LOAD_SEQUENCE: 0,
    PAGE_SIZE: 80,
    PHOTOS: [{id: 'old'}],
    TOTAL_ITEMS: 1,
    LAST_MEDIA_STATUS: '1/1 file caricati',
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

    context.SELECTING = true;
    await vm.runInContext('refreshLivePhotos()', context);
    assert.equal(requests, 2, 'selection mode does not poll');
})().catch((error)=>{
    console.error(error);
    process.exitCode = 1;
});
