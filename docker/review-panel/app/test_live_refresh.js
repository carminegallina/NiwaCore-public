const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(`${__dirname}/app.py`, 'utf8');
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
