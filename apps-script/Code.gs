/**
 * PCN Explorer – progress sync backend (Google Apps Script web app).
 *
 * Stores which park-connector segments you've covered in this spreadsheet:
 *   "Segments" sheet – one row per covered segment (id, name, metres, lat, lon, date)
 *   "Log" sheet      – one row per route marked done / GPX import
 *
 * Setup (once):
 *   1. Create a Google Sheet, then Extensions → Apps Script, and paste this file.
 *   2. Project Settings → Script properties → add SECRET = <a long random string>.
 *   3. Deploy → New deployment → Web app. Execute as: Me. Who has access: Anyone.
 *   4. Copy the /exec URL. In PCN Explorer open "Sync settings" and paste the URL and SECRET.
 *
 * "Anyone" only means the URL can be called without a Google login; every call must
 * carry SECRET, and calls without it are refused.
 */
const SEG = 'Segments', LOG = 'Log';
const SEG_HEAD = ['segment_id', 'name', 'metres', 'mid_lat', 'mid_lon', 'covered_on', 'network_version'];
const LOG_HEAD = ['timestamp', 'from', 'to', 'km', 'mode', 'new_metres'];

function doGet(e) {
  return handle_(e.parameter || {});
}

function doPost(e) {
  let body = {};
  try { body = JSON.parse((e.postData && e.postData.contents) || '{}'); } catch (err) { return out_({ ok: false, error: 'bad json' }); }
  return handle_(body);
}

function handle_(req) {
  const secret = PropertiesService.getScriptProperties().getProperty('SECRET');
  if (!secret) return out_({ ok: false, error: 'SECRET script property is not set' });
  if (req.key !== secret) return out_({ ok: false, error: 'wrong key' });
  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    const action = req.action || 'get';
    if (action === 'get') return out_(read_());
    if (action === 'add') return out_(add_(req));
    if (action === 'reset') return out_(reset_());
    return out_({ ok: false, error: 'unknown action' });
  } finally {
    lock.releaseLock();
  }
}

function sheet_(name, head) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
    sh.appendRow(head);
    sh.setFrozenRows(1);
    sh.getRange(1, 1, 1, head.length).setFontWeight('bold');
  }
  return sh;
}

function read_() {
  const seg = sheet_(SEG, SEG_HEAD), log = sheet_(LOG, LOG_HEAD);
  const sv = seg.getLastRow() > 1 ? seg.getRange(2, 1, seg.getLastRow() - 1, SEG_HEAD.length).getValues() : [];
  const lv = log.getLastRow() > 1 ? log.getRange(2, 1, log.getLastRow() - 1, LOG_HEAD.length).getValues() : [];
  return {
    ok: true,
    segments: sv.map(r => ({ id: Number(r[0]), lat: Number(r[3]), lon: Number(r[4]), v: String(r[6]) })),
    hist: lv.slice(-200).map(r => ({ t: new Date(r[0]).getTime(), from: r[1], to: r[2], km: Number(r[3]), mode: r[4] }))
  };
}

// req.segments: [{id, name, len, lat, lon}], req.v: network version, req.hist: [{t, from, to, km, mode, add}]
function add_(req) {
  const seg = sheet_(SEG, SEG_HEAD), log = sheet_(LOG, LOG_HEAD);
  const have = new Set();
  if (seg.getLastRow() > 1) seg.getRange(2, 1, seg.getLastRow() - 1, 1).getValues().forEach(r => have.add(String(r[0])));
  const now = new Date();
  const rows = (req.segments || []).filter(s => !have.has(String(s.id)))
    .map(s => [s.id, s.name || '', Math.round(s.len || 0), s.lat, s.lon, now, req.v || '']);
  if (rows.length) seg.getRange(seg.getLastRow() + 1, 1, rows.length, SEG_HEAD.length).setValues(rows);
  const haveT = new Set();
  if (log.getLastRow() > 1) log.getRange(2, 1, log.getLastRow() - 1, 1).getValues().forEach(r => haveT.add(new Date(r[0]).getTime()));
  const lrows = (req.hist || []).filter(h => !haveT.has(h.t))
    .map(h => [new Date(h.t), h.from || '', h.to || '', h.km || 0, h.mode || '', Math.round(h.add || 0)]);
  if (lrows.length) log.getRange(log.getLastRow() + 1, 1, lrows.length, LOG_HEAD.length).setValues(lrows);
  return { ok: true, added: rows.length, logged: lrows.length };
}

function reset_() {
  [[SEG, SEG_HEAD], [LOG, LOG_HEAD]].forEach(([n, h]) => {
    const sh = sheet_(n, h);
    if (sh.getLastRow() > 1) sh.deleteRows(2, sh.getLastRow() - 1);
  });
  return { ok: true };
}

function out_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
