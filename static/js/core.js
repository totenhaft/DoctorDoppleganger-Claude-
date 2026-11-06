/* 공통 도구: 서버 요청, 화면 그리기 도우미, 모달, 알림, 메뉴, 로그인 */
'use strict';

const App = {
  user: null,
  settings: null,   // /api/settings 결과
  pages: {},        // 각 화면: App.pages.script = { title, render(main) }
  timers: [],
};

/* ---------- 화면 요소 만들기 ----------
   h('div', {class: 'card', onclick: fn}, '글자', 다른요소...) */
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'html') el.innerHTML = v;
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
const $ = (sel, root = document) => root.querySelector(sel);
/* 요소 끝에 덧붙임 (null·false 는 건너뜀) */
function add(el, ...kids) {
  el.append(...kids.flat(Infinity).filter((k) => k !== null && k !== undefined && k !== false));
  return el;
}
/* 요소 안을 새 내용으로 바꿈 (null·false 는 건너뜀) */
function put(el, ...kids) {
  el.replaceChildren(...kids.flat(Infinity).filter((k) => k !== null && k !== undefined && k !== false));
  return el;
}

const ICONS = {
  pen: '<path d="M4 20h4L19 9l-4-4L4 16v4z"/><path d="M13 7l4 4"/>',
  play: '<path d="M7 5l12 7-12 7z"/>',
  list: '<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1 1"/><path d="M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1-1"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
  out: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
  help: '<circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3M12 17h.01"/>',
  eye: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
  copy: '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  down: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
  trash: '<path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
  ext: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/>',
  layers: '<path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>',
  edit: '<path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  menu: '<path d="M3 6h18M3 12h18M3 18h18"/>',
  x: '<path d="M18 6L6 18M6 6l12 12"/>',
  film: '<rect x="2" y="2" width="20" height="20" rx="2.18"/><path d="M7 2v20M17 2v20M2 12h20M2 7h5M2 17h5M17 17h5M17 7h5"/>',
  face: '<circle cx="12" cy="8" r="4"/><path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1"/>',
  mic: '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v1a7 7 0 0 0 14 0v-1M12 18v4"/>',
  refresh: '<path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.5 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.5 15"/>',
};
function icon(name) {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('viewBox', '0 0 24 24');
  s.innerHTML = ICONS[name] || '';
  return s;
}
function iconBtn(name, title, onclick, extra = {}) {
  return h('button', { class: 'icon-btn' + (extra.danger ? ' danger' : ''), title, 'aria-label': title, onclick, disabled: extra.disabled }, icon(name));
}

/* ---------- 서버 요청 ---------- */
async function api(method, url, data, opts = {}) {
  const init = { method, headers: { 'X-Requested-With': 'dd' }, credentials: 'same-origin' };
  if (data instanceof FormData) init.body = data;
  else if (data !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(data); }
  let res;
  try { res = await fetch(url, init); }
  catch (e) { throw new Error('프로그램(서버)에 연결하지 못했습니다. 검은 명령창이 켜져 있는지 확인해 주세요.'); }
  if (opts.raw) return res;
  let body = null;
  const text = await res.text();
  try { body = text ? JSON.parse(text) : null; } catch { body = text; }
  if (!res.ok) {
    if (res.status === 401 && !opts.allow401) { App.user = null; App.render(); }
    const msg = (body && body.detail) ? (typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)) : `요청이 실패했습니다 (${res.status})`;
    const err = new Error(msg); err.status = res.status; throw err;
  }
  return body;
}

/* ---------- 알림·모달 ---------- */
function toast(msg, opts = {}) {
  const t = h('div', { class: 'toast' + (opts.bad ? ' bad' : '') }, h('span', {}, msg),
    opts.action ? h('button', { onclick: () => { opts.action.fn(); t.remove(); } }, opts.action.label) : null);
  $('#toasts').append(t);
  setTimeout(() => t.remove(), opts.ms || (opts.action ? 7000 : 3500));
}
function fail(e) { toast(e.message || String(e), { bad: true, ms: 6000 }); }

function modal({ title, body, foot, size, onClose }) {
  const close = () => { wrap.remove(); document.removeEventListener('keydown', esc); onClose && onClose(); };
  const esc = (e) => { if (e.key === 'Escape') close(); };
  const box = h('div', { class: 'modal' + (size ? ' ' + size : ''), role: 'dialog', 'aria-modal': 'true' },
    h('div', { class: 'modal-head' }, h('h3', {}, title), iconBtn('x', '닫기', () => close())),
    h('div', { class: 'modal-body' }, body),
    foot ? h('div', { class: 'modal-foot' }, foot) : null);
  const wrap = h('div', { class: 'modal-wrap', onmousedown: (e) => { if (e.target === wrap) close(); } }, box);
  document.body.append(wrap);
  document.addEventListener('keydown', esc);
  return { close, box };
}

/* "삭제"처럼 단어를 직접 입력해야 진행되는 확인 창 */
function confirmTyped({ title, message, word, okLabel, danger = true }) {
  return new Promise((resolve) => {
    const inp = h('input', { class: 'input', placeholder: word, autocomplete: 'off' });
    const ok = h('button', { class: 'btn ' + (danger ? 'danger solid' : 'primary'), disabled: true }, okLabel || word);
    inp.addEventListener('input', () => { ok.disabled = inp.value.trim() !== word; });
    let done = false;
    const m = modal({
      title, body: h('div', { class: 'stack' }, h('p', { style: { margin: 0 } }, message),
        h('label', { class: 'lbl' }, `확인을 위해 「${word}」라고 입력해 주세요`), inp),
      foot: [h('button', { class: 'btn', onclick: () => m.close() }, '취소'), ok],
      onClose: () => { if (!done) resolve(false); },
    });
    ok.onclick = () => { done = true; m.close(); resolve(true); };
    setTimeout(() => inp.focus(), 50);
  });
}
function confirmBox({ title, message, okLabel = '확인', danger = false }) {
  return new Promise((resolve) => {
    let done = false;
    const m = modal({
      title, body: h('p', { style: { margin: 0, whiteSpace: 'pre-line' } }, message),
      foot: [h('button', { class: 'btn', onclick: () => m.close() }, '취소'),
        h('button', { class: 'btn ' + (danger ? 'danger solid' : 'primary'), onclick: () => { done = true; m.close(); resolve(true); } }, okLabel)],
      onClose: () => { if (!done) resolve(false); },
    });
  });
}

/* ---------- 작은 도구 ---------- */
const fmtDate = (t) => {
  const d = new Date(t * 1000), p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
};
const fmtDur = (s) => { s = Math.round(s || 0); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };
const fmtDurKo = (s) => { s = Math.round(s || 0); const m = Math.floor(s / 60); return m ? `${m}분 ${s % 60}초` : `${s}초`; };
const STEP_COLORS = ['#2F6BFF', '#12A37F', '#E07B16', '#8B5CF6'];
const stepColor = (i) => STEP_COLORS[i % STEP_COLORS.length];
const langLabel = (code) => ((App.settings?.settings.languages || []).find((l) => l.code === code) || {}).label || code;
const isOperator = () => App.user && App.user.role === 'operator';
const CHARS_PER_SEC = { ko: 5.5, ja: 6.5, zh: 4.5 };
function splitSentences(text) {
  return (text || '').trim().split(/(?<=[.!?。！？…]["'”’)\]」』]*)\s+|\n+/).map((s) => s.trim()).filter(Boolean);
}
function estimateSeconds(steps, lang) {
  const rate = CHARS_PER_SEC[(lang || 'ko').split('-')[0]] || 14;
  let chars = 0, sents = 0;
  for (const s of steps) { chars += (s.body || '').replace(/\s+/g, '').length; sents += splitSentences(s.body).length; }
  return Math.round((chars / rate + sents * 0.35 + 1) * 10) / 10;
}
function counter(input, max, rec) {
  const c = h('span', { class: 'count' });
  const upd = () => {
    const n = input.value.length;
    c.textContent = rec ? `${n}/${rec} 권장 · 최대 ${max}자` : `${n}/${max}`;
    c.classList.toggle('over', n > (rec || max));
  };
  input.addEventListener('input', upd); upd();
  return c;
}
function download(name, text, type = 'application/json') {
  const a = h('a', { href: URL.createObjectURL(new Blob([text], { type })), download: name });
  document.body.append(a); a.click(); a.remove();
}
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; }
  catch { return false; }
}
function pickFile(accept) {
  return new Promise((resolve) => {
    const i = h('input', { type: 'file', accept, style: { display: 'none' } });
    i.onchange = () => { resolve(i.files[0] || null); i.remove(); };
    document.body.append(i); i.click();
  });
}
function clearTimers() { App.timers.forEach(clearInterval); App.timers = []; }

/* ---------- 메뉴·화면 전환 ---------- */
const NAV = [
  { id: 'script', label: '스크립트 등록', icon: 'pen' },
  { id: 'create', label: '영상 만들기', icon: 'play' },
  { id: 'history', label: '생성 이력', icon: 'list' },
  { id: 'studio', label: '아바타·목소리', icon: 'face' },
  { id: 'share', label: '안내문구 설정', icon: 'link', op: true },
  { id: 'settings', label: '설정', icon: 'gear' },
];

function route() {
  const hash = location.hash.replace(/^#\/?/, '') || 'script';
  const [id, q] = hash.split('?');
  return { id, query: new URLSearchParams(q || '') };
}
function go(path) { location.hash = '#/' + path; }

App.render = async function () {
  clearTimers();
  const root = $('#app');
  if (!App.user) {
    let s;
    try { s = await api('GET', '/api/session', undefined, { allow401: true }); } catch (e) { put(root, h('div', { class: 'boot' }, e.message)); return; }
    if (s.user) { App.user = s.user; } else { put(root, s.setup_needed ? setupScreen(s) : loginScreen(s)); return; }
  }
  if (App.user.must_change) { put(root, changePwScreen()); return; }
  if (!App.settings) {
    try { App.settings = await api('GET', '/api/settings'); } catch (e) { fail(e); return; }
  }
  const r = route();
  const page = App.pages[r.id] || App.pages.script;
  const main = h('main', { class: 'main' });
  put(root, layout(r.id, main));
  document.title = `${page.title} · Doctor Doppelganger`;
  try { await page.render(main, r.query); } catch (e) { fail(e); }
};
App.reloadSettings = async () => { App.settings = await api('GET', '/api/settings'); };

function layout(active, main) {
  const shell = h('div', { class: 'shell' });
  const navLink = (n) => h('a', { href: '#/' + n.id, class: active === n.id ? 'on' : '' }, icon(n.icon), n.label);
  const side = h('aside', { class: 'side' },
    h('div', { class: 'brand' },
      h('div', { class: 'logo' }, h('span', { class: 'mark', html: '<svg viewBox="0 0 24 24"><path d="M7 4l14 8-14 8z" fill="#fff"/></svg>' }), 'Doctor Doppelganger'),
      h('div', { class: 'sub' }, `${App.settings.settings.org_name} · 진료안내 영상`)),
    h('nav', { class: 'nav' }, NAV.filter((n) => !n.op || isOperator()).map(navLink)),
    h('div', { class: 'side-foot' },
      h('div', { class: 'whoami' }, h('b', {}, App.user.role === 'operator' ? '운영자' : '담당자'), ' · ', App.user.username),
      isOperator() ? h('a', { href: '#/accounts', class: active === 'accounts' ? 'on' : '' }, icon('users'), '계정 관리') : null,
      h('a', { href: '#/password' }, icon('pen'), '비밀번호 바꾸기'),
      h('a', { href: '#/guide', class: active === 'guide' ? 'on' : '' }, icon('help'), '사용 가이드'),
      h('button', { onclick: logout }, icon('out'), '로그아웃')));
  const top = h('div', { class: 'topbar' },
    iconBtn('menu', '메뉴', () => shell.classList.toggle('menu-open')), h('b', {}, 'Doctor Doppelganger'));
  side.addEventListener('click', (e) => { if (e.target.closest('a')) shell.classList.remove('menu-open'); });
  shell.append(side, h('div', {}, top, main));
  return shell;
}
function pageHead(title, desc, ...right) {
  return h('div', { class: 'page-head row between' }, h('div', {}, h('h1', {}, title), desc ? h('p', {}, desc) : null), right.length ? h('div', { class: 'row' }, right) : null);
}

async function logout() {
  try { await api('POST', '/api/logout'); } catch { /* 무시 */ }
  App.user = null; App.settings = null; location.hash = ''; App.render();
}

/* ---------- 로그인 화면 ---------- */
function authCard(...kids) {
  return h('div', { class: 'auth' }, h('div', { class: 'card' },
    h('div', { class: 'brand-t' }, h('b', {}, 'Doctor Doppelganger'), h('div', {}, '원장님 아바타 진료안내 영상 자동화')),
    ...kids, h('div', { class: 'foot' }, '이 프로그램은 병원 PC 에서 실행됩니다.')));
}
function loginScreen(s) {
  const u = h('input', { class: 'input', autocomplete: 'username', placeholder: '아이디' });
  const p = h('input', { class: 'input', type: 'password', autocomplete: 'current-password', placeholder: '비밀번호' });
  const err = h('div', { class: 'err' });
  const btn = h('button', { class: 'btn primary xl', type: 'submit' }, '로그인');
  const form = h('form', { class: 'stack', onsubmit: async (e) => {
    e.preventDefault(); err.textContent = ''; btn.disabled = true; btn.textContent = '확인 중…';
    try { await api('POST', '/api/login', { username: u.value, password: p.value }, { allow401: true }); App.user = null; await App.render(); }
    catch (ex) { err.textContent = ex.message; btn.disabled = false; btn.textContent = '로그인'; }
  } },
  h('div', {}, h('h1', {}, '로그인'), h('p', { class: 'muted', style: { margin: 0 } }, `${s.org_name || '병원'}에서 받은 아이디로 들어갑니다.`)),
  h('div', {}, h('label', { class: 'lbl' }, '아이디'), u),
  h('div', {}, h('label', { class: 'lbl' }, '비밀번호'), p), err, btn,
  h('p', { class: 'hint', style: { textAlign: 'center' } }, '비밀번호를 잊었으면 운영자에게 재설정을 요청하세요.'));
  setTimeout(() => u.focus(), 50);
  return authCard(form);
}
function setupScreen(s) {
  const org = h('input', { class: 'input', value: s.org_name || '', maxlength: 40 });
  const u = h('input', { class: 'input', placeholder: '예: director', autocomplete: 'username' });
  const p = h('input', { class: 'input', type: 'password', autocomplete: 'new-password' });
  const p2 = h('input', { class: 'input', type: 'password', autocomplete: 'new-password' });
  const err = h('div', { class: 'err' });
  const form = h('form', { class: 'stack', onsubmit: async (e) => {
    e.preventDefault(); err.textContent = '';
    if (p.value !== p2.value) { err.textContent = '비밀번호 두 칸이 같지 않습니다.'; return; }
    try { await api('POST', '/api/setup', { username: u.value, password: p.value, org_name: org.value }); App.user = null; await App.render(); }
    catch (ex) { err.textContent = ex.message; }
  } },
  h('div', {}, h('h1', {}, '처음 설정'), h('p', { class: 'muted', style: { margin: 0 } }, '운영자(원장님) 계정을 만듭니다. 나중에 직원 계정을 초대할 수 있습니다.')),
  h('div', {}, h('label', { class: 'lbl' }, '병원명'), org),
  h('div', {}, h('label', { class: 'lbl' }, '운영자 아이디'), u, h('div', { class: 'hint' }, '영문 소문자·숫자, 3자 이상')),
  h('div', {}, h('label', { class: 'lbl' }, '비밀번호'), p, h('div', { class: 'hint' }, '10자 이상, 영문과 숫자를 섞어 주세요.')),
  h('div', {}, h('label', { class: 'lbl' }, '비밀번호 확인'), p2), err,
  h('button', { class: 'btn primary xl', type: 'submit' }, '시작하기'));
  return authCard(form);
}
function changePwScreen() {
  const p = h('input', { class: 'input', type: 'password', autocomplete: 'new-password' });
  const p2 = h('input', { class: 'input', type: 'password', autocomplete: 'new-password' });
  const err = h('div', { class: 'err' });
  const form = h('form', { class: 'stack', onsubmit: async (e) => {
    e.preventDefault(); err.textContent = '';
    try { await api('POST', '/api/password', { new_password: p.value, confirm: p2.value }); App.user = null; location.hash = ''; await App.render(); }
    catch (ex) { err.textContent = ex.message; }
  } },
  h('div', {}, h('h1', {}, '새 비밀번호 정하기'), h('p', { class: 'muted', style: { margin: 0 } }, '처음 로그인입니다. 앞으로 쓸 비밀번호를 정해 주세요. 10자 이상, 영문과 숫자를 섞습니다.')),
  h('div', {}, h('label', { class: 'lbl' }, '새 비밀번호'), p),
  h('div', {}, h('label', { class: 'lbl' }, '새 비밀번호 확인'), p2), err,
  h('button', { class: 'btn primary xl', type: 'submit' }, '비밀번호 바꾸고 들어가기'),
  h('button', { class: 'btn ghost', type: 'button', onclick: logout }, '로그아웃'));
  return authCard(form);
}

App.pages.password = {
  title: '비밀번호 바꾸기',
  render(main) {
    const cur = h('input', { class: 'input', type: 'password', autocomplete: 'current-password' });
    const p = h('input', { class: 'input', type: 'password', autocomplete: 'new-password' });
    const p2 = h('input', { class: 'input', type: 'password', autocomplete: 'new-password' });
    const err = h('div', { class: 'err' });
    add(main, pageHead('비밀번호 바꾸기', '바꾸면 다른 기기의 로그인은 모두 끊깁니다.'),
      h('form', { class: 'card stack', style: { maxWidth: '460px' }, onsubmit: async (e) => {
        e.preventDefault(); err.textContent = '';
        try { await api('POST', '/api/password', { current_password: cur.value, new_password: p.value, confirm: p2.value }); toast('비밀번호를 바꿨습니다.'); go('script'); }
        catch (ex) { err.textContent = ex.message; }
      } },
      h('div', {}, h('label', { class: 'lbl' }, '지금 비밀번호'), cur),
      h('div', {}, h('label', { class: 'lbl' }, '새 비밀번호'), p, h('div', { class: 'hint' }, '10자 이상, 영문과 숫자를 섞어 주세요.')),
      h('div', {}, h('label', { class: 'lbl' }, '새 비밀번호 확인'), p2), err,
      h('button', { class: 'btn primary', type: 'submit' }, '바꾸기')));
  },
};

App.start = function () {
  window.addEventListener('hashchange', () => App.render());
  App.render();
};
