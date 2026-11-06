/* 스크립트 등록 화면 + 원고 편집 창 */
'use strict';

const MAX_STEPS = 4;
const EXAMPLE_SCRIPT = `수술 당일 안정
안녕하세요, 원장입니다. 시력교정 수술 후 관리 방법을 안내해 드리겠습니다. 수술 당일에는 눈을 비비지 마시고, 보호안경을 쓰고 주무세요.

안약 점안
처방해 드린 안약은 안내받은 시간에 맞춰 점안해 주세요. 안약 사이에는 5분 정도 간격을 두시면 됩니다.

다음 날 검진
다음 날 오전에 첫 검진이 있습니다. 통증이나 충혈이 심해지면 바로 병원으로 연락해 주세요.`;

/* 붙여넣은 원고 → 단계. 빈 줄로 나뉜 문단이 한 단계, 첫 줄이 짧으면 단계 제목 */
function pasteToSteps(text) {
  const paras = (text || '').replace(/\r/g, '').split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
  const steps = paras.map((p) => {
    const lines = p.split('\n').map((l) => l.trim()).filter(Boolean);
    if (lines.length > 1 && lines[0].length <= 30 && !/[.!?。！？]$/.test(lines[0])) {
      return { title: lines[0], body: lines.slice(1).join(' ') };
    }
    return { title: '', body: lines.join(' ') };
  });
  let merged = false;
  while (steps.length > MAX_STEPS) {
    const extra = steps.pop();
    steps[MAX_STEPS - 1].body += ' ' + (extra.title ? extra.title + '. ' : '') + extra.body;
    merged = true;
  }
  return { steps, merged, paragraphs: paras.length };
}

App.pages.script = {
  title: '스크립트 등록',
  state: { lang: 'all', q: '', page: 0 },
  async render(main, query) {
    const S = this.state;
    const data = await api('GET', '/api/scripts');
    const feats = await api('GET', '/api/features');
    const langs = App.settings.settings.languages;
    const all = data.scripts;
    const counts = {};
    all.forEach((s) => { counts[s.language] = (counts[s.language] || 0) + 1; });
    const list = all.filter((s) => (S.lang === 'all' || s.language === S.lang) && (!S.q || s.title.toLowerCase().includes(S.q.toLowerCase())));
    const pages = Math.max(1, Math.ceil(list.length / 10));
    S.page = Math.min(S.page, pages - 1);
    const shown = list.slice(S.page * 10, S.page * 10 + 10);
    const rerender = () => App.render();

    const search = h('input', { class: 'input', placeholder: '제목으로 찾기', value: S.q, style: { maxWidth: '260px' } });
    search.addEventListener('input', () => { S.q = search.value; S.page = 0; clearTimeout(search._t); search._t = setTimeout(() => { rerender().then(() => { const s = $('.main input.input'); if (s) { s.focus(); s.setSelectionRange(s.value.length, s.value.length); } }); }, 300); });

    const row = (s) => {
      const tr = h('tr', {},
        h('td', { class: 'title-cell' },
          h('div', { class: 'row' }, s.title, !s.reviewed ? h('span', { class: 'tag warn', title: '기계번역 · 의료진 검수 전' }, '검수 전') : null),
          h('div', { class: 'sub' }, s.steps.map((st, i) => h('span', { class: 'tag', style: { marginRight: '4px', background: stepColor(i) + '18', color: stepColor(i) } }, st.title || `${i + 1}단계`)))),
        h('td', { 'data-l': '언어' }, langLabel(s.language)),
        h('td', { 'data-l': '글자수', class: 'mono' }, `${s.chars}자`),
        h('td', { 'data-l': '예상 길이', class: 'mono' }, fmtDurKo(s.est_seconds)),
        h('td', { 'data-l': '등록일', class: 'mono small muted' }, fmtDate(s.created_at)),
        h('td', { 'data-l': '작업' }, h('div', { class: 'actions' },
          iconBtn('eye', '미리보기', () => previewScript(s)),
          iconBtn('edit', '수정', () => openScriptEditor(s, rerender)),
          iconBtn('copy', '복제', async () => { try { await api('POST', `/api/scripts/${s.id}/duplicate`); toast(`${s.title} 의 사본을 만들었습니다.`); rerender(); } catch (e) { fail(e); } }),
          iconBtn('down', '백업 (JSON 내려받기)', () => { download(`${s.title}.json`, JSON.stringify({ app: 'doctor-doppelganger', version: 1, title: s.title, language: s.language, steps: s.steps }, null, 2)); toast('백업 파일을 내려받았습니다.'); }),
          iconBtn('trash', '삭제', async () => {
            if (!await confirmTyped({ title: '스크립트 삭제', message: `「${s.title}」을(를) 지웁니다. 되돌릴 수 없습니다. 필요하면 먼저 백업하세요. (이미 만든 영상은 그대로 남습니다)`, word: '삭제' })) return;
            try { await api('DELETE', `/api/scripts/${s.id}`); toast('삭제했습니다.'); rerender(); } catch (e) { fail(e); }
          }, { danger: true })),
        feats.ai ? translateBox(s, langs, rerender) : null));
      return tr;
    };

    add(main, 
      pageHead('스크립트 등록', '원고를 붙여넣으면 빈 줄마다 단계가 나뉩니다. 단계 제목은 영상의 단계 배지에 나오고, 아바타는 말할 내용만 읽습니다.'),
      h('div', { class: 'card' },
        h('div', { class: 'row between', style: { marginBottom: '12px' } },
          h('h2', {}, `저장된 스크립트 (${all.length})`),
          h('div', { class: 'row' }, search, h('button', { class: 'btn primary', onclick: () => openScriptEditor(null, rerender) }, '+ 신규 등록'))),
        h('div', { class: 'chips', style: { marginBottom: '8px' } },
          h('button', { class: 'chip' + (S.lang === 'all' ? ' on' : ''), onclick: () => { S.lang = 'all'; S.page = 0; rerender(); } }, '전체', h('span', { class: 'n' }, all.length)),
          langs.map((l) => h('button', { class: 'chip' + (S.lang === l.code ? ' on' : ''), onclick: () => { S.lang = l.code; S.page = 0; rerender(); } }, l.label, h('span', { class: 'n' }, counts[l.code] || 0)))),
        shown.length ? h('table', { class: 'table responsive' },
          h('thead', {}, h('tr', {}, ['제목', '언어', '글자수', '예상 길이', '등록일', '작업'].map((t) => h('th', {}, t)))),
          h('tbody', {}, shown.map(row))) :
          h('div', { class: 'empty' }, h('b', {}, all.length ? '조건에 맞는 스크립트가 없습니다.' : '아직 저장한 스크립트가 없습니다.'),
            all.length ? '언어 탭을 「전체」로 바꾸거나 검색어를 지워 보세요.' : '「+ 신규 등록」으로 첫 원고를 저장해 보세요.'),
        pages > 1 ? h('div', { class: 'pager' },
          h('button', { class: 'btn sm', disabled: S.page === 0, onclick: () => { S.page--; rerender(); } }, '이전'),
          h('span', {}, `${S.page + 1} / ${pages}`),
          h('button', { class: 'btn sm', disabled: S.page >= pages - 1, onclick: () => { S.page++; rerender(); } }, '다음')) : null));

    if (query.get('new')) openScriptEditor(null, rerender);
  },
};

function translateBox(s, langs, done) {
  const others = langs.filter((l) => l.code !== s.language);
  if (!others.length) return null;
  const sel = h('select', { class: 'input', style: { width: 'auto', padding: '4px 8px', fontSize: '12px' }, 'aria-label': '번역할 언어' },
    others.map((l) => h('option', { value: l.code }, l.label)));
  const btn = h('button', { class: 'btn sm', onclick: async () => {
    btn.disabled = true; btn.textContent = '번역 중…';
    try { await api('POST', `/api/scripts/${s.id}/translate`, { language: sel.value }); toast('기계번역본을 만들었습니다. 의료진이 검수한 뒤 사용하세요.'); done(); }
    catch (e) { fail(e); btn.disabled = false; btn.textContent = '번역'; }
  } }, '번역');
  return h('div', { class: 'row', style: { flexWrap: 'nowrap', marginTop: '6px' }, title: 'AI 기계번역본을 새 스크립트로 만듭니다' }, sel, btn);
}

function sentencePanel(steps, lang) {
  const total = steps.reduce((n, s) => n + splitSentences(s.body).length, 0);
  let k = 0;
  const est = estimateSeconds(steps, lang);
  return h('div', { class: 'card', style: { boxShadow: 'none' } },
    h('div', { class: 'row between' }, h('h2', {}, '아바타가 읽을 문장'),
      total ? h('span', { class: 'tag' }, `문장 ${total}개 · 약 ${fmtDurKo(est)}`) : null),
    est > (App.settings.max_seconds || 300) ? h('div', { class: 'notice bad', style: { margin: '8px 0' } }, `예상 길이가 ${fmtDurKo(est)}입니다. 영상은 최대 ${fmtDurKo(App.settings.max_seconds)}까지 만들 수 있어요. 원고를 줄여 주세요.`) : null,
    !total ? h('p', { class: 'muted small' }, '원고를 붙여넣으면 아바타가 읽을 문장이 순서대로 여기에 나옵니다.') :
      h('div', { class: 'sent-list', style: { marginTop: '10px' } }, steps.map((s, i) => {
        const sents = splitSentences(s.body);
        return h('div', { class: 'sent-step' },
          h('div', { class: 'h', style: { color: stepColor(i) } }, h('span', { class: 'step-no' }, h('span', { class: 'dot', style: { background: stepColor(i) } }, i + 1)), s.title || `${i + 1}단계`),
          sents.length ? sents.map((t) => { k++; return h('div', { class: 'sent' + (t.length > 56 ? ' long' : '') }, h('span', { class: 'i' }, k), h('span', {}, t), h('span', { class: 'c' }, t.length > 56 ? `${t.length}자 · 자막이 두 화면 이상으로 나뉠 수 있습니다` : `${t.length}자`)); }) :
            h('div', { class: 'small', style: { color: 'var(--bad)' } }, '말할 내용이 비어 있습니다'));
      })),
    total && !/[.!?。！？]/.test(steps.map((s) => s.body).join('')) ? h('div', { class: 'notice warn', style: { marginTop: '8px' } }, '마침표가 없어 문장을 나누지 못했습니다. 문장 끝에 마침표를 넣으면 자막이 자연스럽게 나뉩니다.') : null);
}

function previewScript(s) {
  modal({ title: s.title, size: 'mid', body: h('div', { class: 'stack' },
    h('div', { class: 'row' }, h('span', { class: 'tag' }, langLabel(s.language)), h('span', { class: 'tag' }, `${s.chars}자`), h('span', { class: 'tag' }, `약 ${fmtDurKo(s.est_seconds)}`),
      !s.reviewed ? h('span', { class: 'tag warn' }, '기계번역 · 검수 전') : null),
    !s.reviewed ? h('div', { class: 'notice warn' }, '기계번역 결과입니다. 의료 내용을 아는 병원 담당자가 반드시 검토·수정한 뒤 「검수 완료」를 눌러 주세요.',
      h('div', { style: { marginTop: '8px' } }, h('button', { class: 'btn sm', onclick: async (e) => { try { await api('POST', `/api/scripts/${s.id}/review`); e.target.closest('.modal-wrap').remove(); toast('검수 완료로 표시했습니다.'); App.render(); } catch (er) { fail(er); } } }, '검수 완료로 표시'))) : null,
    sentencePanel(s.steps, s.language)) });
}

/* ---------- 원고 편집 창 ---------- */
function openScriptEditor(existing, onSaved) {
  const langs = App.settings.settings.languages;
  const st = {
    title: existing ? existing.title : '',
    language: existing ? existing.language : App.settings.settings.default_language,
    steps: existing ? existing.steps.map((s) => ({ ...s })) : [],
    mode: existing ? 'steps' : 'paste',
    tab: 'paste',
    paste: '',
    source: existing ? existing.source : 'manual',
    undo: null,
  };
  let aiOn = false;
  api('GET', '/api/features').then((f) => { aiOn = f.ai; draw(); }).catch(() => {});

  const left = h('div', {});
  const right = h('div', {});
  const saveBtn = h('button', { class: 'btn primary', style: { minWidth: '160px' } }, '스크립트 저장');
  const reason = h('span', { class: 'small muted' });
  const m = modal({ title: existing ? '스크립트 수정' : '새 스크립트', size: 'wide',
    body: h('div', { class: 'editor-grid' }, left, right),
    foot: [reason, h('button', { class: 'btn', onclick: () => m.close() }, '취소'), saveBtn] });

  const titleIn = h('input', { class: 'input', value: st.title, maxlength: 60, placeholder: '예: 시력교정 수술 후 관리 안내' });
  titleIn.addEventListener('input', () => { st.title = titleIn.value; check(); });

  function check() {
    let why = '';
    if (st.mode === 'paste' && !st.steps.length) why = st.paste.trim() ? '원고 칸 밖을 누르면 단계로 나뉩니다' : '원고를 붙여넣으면 저장할 수 있습니다';
    else if (!st.title.trim()) why = '스크립트 제목을 입력해 주세요';
    else if (st.steps.some((s) => !s.body.trim())) why = '비어 있는 단계의 말할 내용을 채워 주세요';
    else if (st.steps.some((s) => /[<>]/.test(s.title + s.body))) why = '< > 기호는 쓸 수 없습니다';
    saveBtn.disabled = !!why;
    reason.textContent = why;
    put(right, sentencePanel(st.steps, st.language));
  }
  function setSteps(steps, msg) {
    st.undo = st.steps.length ? st.steps.map((s) => ({ ...s })) : null;
    st.steps = steps; st.mode = 'steps'; draw();
    if (msg) toast(msg, st.undo ? { action: { label: '되돌리기', fn: () => { st.steps = st.undo; st.undo = null; draw(); } } } : {});
  }
  function applyPaste() {
    if (!st.paste.trim()) return;
    const r = pasteToSteps(st.paste);
    st.steps = r.steps; st.mode = 'steps'; st.paste = '';
    if (r.merged) toast(`문단이 ${r.paragraphs}개라 4단계까지만 나눴습니다. 5번째 문단부터는 4단계 뒤에 붙였습니다.`, { ms: 6000 });
    draw();
  }

  function pasteView() {
    const ta = h('textarea', { class: 'input', rows: 10, placeholder: '여기에 원고를 붙여넣으세요 (Ctrl+V)', value: st.paste });
    ta.value = st.paste;
    ta.addEventListener('input', () => { st.paste = ta.value; check(); });
    ta.addEventListener('blur', () => applyPaste());
    setTimeout(() => ta.focus(), 30);
    return h('div', { class: 'paste-box' },
      h('b', {}, '원고 붙여넣기'),
      h('p', { class: 'small muted', style: { margin: '4px 0 10px' } }, '빈 줄로 나뉜 문단이 한 단계가 됩니다. 문단 첫 줄이 짧으면 단계 제목으로 씁니다. 단계는 4개까지입니다.'),
      ta,
      h('div', { class: 'row', style: { marginTop: '10px' } },
        h('button', { class: 'btn sm', onclick: () => { st.paste = EXAMPLE_SCRIPT; applyPaste(); } }, '예시 원고 넣기'),
        h('button', { class: 'btn sm', onclick: async () => { try { const t = await navigator.clipboard.readText(); if (!t.trim()) { toast('클립보드가 비어 있습니다.'); return; } st.paste = t; applyPaste(); } catch { toast('Ctrl+V 로 직접 붙여넣어 주세요.'); } } }, '클립보드에서 붙여넣기'),
        h('button', { class: 'btn sm ghost', onclick: () => { st.steps = [{ title: '', body: '' }]; st.mode = 'steps'; draw(); } }, '한 단계씩 직접 쓰기'),
        h('button', { class: 'btn sm ghost', onclick: loadBackup }, '백업 파일 불러오기')));
  }

  function stepsView() {
    const wrap = h('div', {});
    st.steps.forEach((s, i) => {
      const tIn = h('input', { class: 'input', value: s.title, maxlength: 40, placeholder: `예: 안약 점안 (영상의 단계 배지에 나옵니다)` });
      tIn.addEventListener('input', () => { s.title = tIn.value; check(); });
      const bIn = h('textarea', { class: 'input', rows: 4, placeholder: '예: 수술 당일에는 눈을 비비지 마세요.' });
      bIn.value = s.body;
      const cnt = h('span', { class: 'count' }, `${s.body.length}자`);
      bIn.addEventListener('input', () => { s.body = bIn.value; cnt.textContent = `${s.body.length}자`; check(); });
      wrap.append(h('div', { class: 'step-card' },
        h('div', { class: 'step-top' },
          h('span', { class: 'step-no', style: { color: stepColor(i) } }, h('span', { class: 'dot', style: { background: stepColor(i) } }, i + 1), `${i + 1}단계`),
          h('span', { class: 'step-bars' }, st.steps.map((_, j) => h('i', { style: { background: j === i ? stepColor(i) : null } }))),
          h('span', { class: 'grow' }),
          h('button', { class: 'btn sm', disabled: st.steps.length >= MAX_STEPS, title: st.steps.length >= MAX_STEPS ? '단계가 4개라 더 나눌 수 없습니다' : '커서 위치에서 두 단계로 나눕니다', onclick: () => {
            const pos = bIn.selectionStart;
            if (!pos || pos >= s.body.length) { toast('나눌 곳에 커서를 두세요'); return; }
            const a = s.body.slice(0, pos).trim(), b = s.body.slice(pos).trim();
            const next = st.steps.map((x) => ({ ...x }));
            next.splice(i, 1, { title: s.title, body: a }, { title: '', body: b });
            setSteps(next);
          } }, '여기서 나누기'),
          h('button', { class: 'btn sm', disabled: i === 0, onclick: () => {
            const next = st.steps.map((x) => ({ ...x }));
            next[i - 1].body = (next[i - 1].body + ' ' + next[i].body).trim();
            next.splice(i, 1);
            setSteps(next, `${i + 1}단계를 위 단계에 합쳤습니다`);
          } }, '위와 합치기'),
          iconBtn('x', `${i + 1}단계 지우기`, () => {
            if (st.steps.length === 1) { toast('단계가 하나뿐이라 지울 수 없습니다. 처음부터 다시 쓰려면 「원고 전체를 다시 붙여넣기」를 누르세요.'); return; }
            const next = st.steps.filter((_, j) => j !== i).map((x) => ({ ...x }));
            setSteps(next, '단계를 지웠습니다');
          })),
        h('div', { class: 'field' }, h('div', { class: 'lbl-row' }, h('label', { class: 'lbl' }, '단계 제목'), counter(tIn, 40, 30)), tIn),
        h('div', { class: 'field' }, h('div', { class: 'lbl-row' }, h('label', { class: 'lbl' }, '말할 내용'), cnt), bIn)));
    });
    return h('div', {},
      h('div', { class: 'steps-head' }, h('b', {}, '단계'), h('span', { class: 'tag' }, `${st.steps.length}/${MAX_STEPS} 단계`)),
      h('details', { class: 'notice', style: { marginBottom: '10px' } }, h('summary', { style: { cursor: 'pointer', fontWeight: 600 } }, '단계 제목과 말할 내용은 영상에서 어떻게 쓰이나요?'),
        h('ul', { style: { margin: '8px 0 0', paddingLeft: '18px' } },
          h('li', {}, '단계 제목은 영상 위쪽 단계 배지에 나옵니다. 아바타가 읽지 않습니다. 비워 두면 「1단계」처럼 번호만 나옵니다.'),
          h('li', {}, '말할 내용은 아바타가 읽습니다. 하단 자막은 실제로 말한 시점에 맞춰 나옵니다.'),
          h('li', {}, '문장 끝에는 꼭 마침표를 넣어 주세요. 자막이 문장 단위로 자연스럽게 나뉩니다.'))),
      wrap,
      h('button', { class: 'btn', style: { width: '100%', marginTop: '10px' }, disabled: st.steps.length >= MAX_STEPS, onclick: () => { st.steps.push({ title: '', body: '' }); draw(); } },
        st.steps.length >= MAX_STEPS ? '단계는 4개까지 만들 수 있습니다' : '+ 단계 추가'),
      h('div', { class: 'row', style: { marginTop: '10px' } },
        h('button', { class: 'btn sm ghost', onclick: () => { st.paste = st.steps.map((s) => (s.title ? s.title + '\n' : '') + s.body).join('\n\n'); st.undo = st.steps; st.steps = []; st.mode = 'paste'; draw(); } }, '원고 전체를 다시 붙여넣기'),
        h('button', { class: 'btn sm ghost', onclick: loadSrt }, 'SRT 파일로 올리기')));
  }

  function aiView() {
    const topic = h('input', { class: 'input', maxlength: 80, placeholder: '예: 백내장 수술 후 일주일 관리' });
    const memo = h('textarea', { class: 'input', rows: 4, maxlength: 400, placeholder: '예: 눈을 비비지 않기, 세안은 3일 뒤부터, 안약은 하루 4번' });
    let n = 3;
    const nSeg = h('div', { class: 'seg' });
    const drawN = () => put(nSeg, ...[1, 2, 3, 4].map((k) => h('button', { type: 'button', class: k === n ? 'on' : '', onclick: () => { n = k; drawN(); } }, `${k}단계`)));
    drawN();
    const btn = h('button', { class: 'btn primary', style: { width: '100%' } }, 'AI 제안 받기');
    btn.onclick = async () => {
      if (!topic.value.trim()) { toast('안내 주제를 적어 주세요.'); return; }
      btn.disabled = true; btn.textContent = '제안을 만드는 중… (최대 1분)';
      try {
        const r = await api('POST', '/api/ai-draft', { topic: topic.value, memo: memo.value, steps: n, language: st.language });
        if (st.steps.length && !await confirmBox({ title: '원고를 AI 제안으로 바꿀까요?', message: '편집기의 단계가 AI 제안으로 바뀝니다. 바꾼 뒤 「되돌리기」로 지금 원고를 다시 불러올 수 있습니다.', okLabel: '바꾸기' })) return;
        st.source = 'ai'; st.tab = 'paste';
        if (!st.title.trim()) { st.title = topic.value.trim().slice(0, 60); titleIn.value = st.title; }
        setSteps(r.steps, 'AI 제안을 채웠습니다. 저장 전에 의료진이 내용을 꼭 확인하고 고쳐 주세요.');
      } catch (e) { fail(e); } finally { btn.disabled = false; btn.textContent = 'AI 제안 받기'; }
    };
    if (!aiOn) return h('div', { class: 'notice' }, 'AI 제안을 쓰려면 운영자가 설정 > Claude AI 연결에서 API 키를 등록해야 합니다. (선택 기능)');
    return h('div', { class: 'paste-box stack' },
      h('div', {}, h('b', {}, 'AI 제안 받기'), h('p', { class: 'small muted', style: { margin: '4px 0 0' } }, '안내 주제를 적으면 AI 가 단계별 원고 초안을 제안합니다. 제안은 편집기에 채워질 뿐 저장되지 않으니, 내용을 확인하고 고친 뒤 저장해 주세요.')),
      h('div', { class: 'notice warn' }, '환자 이름·연락처·주민등록번호 같은 개인정보는 넣지 마세요. 입력한 내용은 Anthropic 의 Claude API 로 전달됩니다.'),
      h('div', {}, h('label', { class: 'lbl' }, '안내 주제'), topic),
      h('div', {}, h('label', { class: 'lbl' }, '참고 메모 (선택)'), memo),
      h('div', {}, h('label', { class: 'lbl' }, '단계 수'), nSeg), btn);
  }

  async function loadSrt() {
    const f = await pickFile('.srt');
    if (!f) return;
    const fd = new FormData(); fd.append('file', f);
    try {
      const r = await api('POST', '/api/srt/parse', fd);
      setSteps([{ title: '', body: r.text }], `자막 ${r.recognized}개를 1단계 원고로 넣었습니다${r.punctuated ? ` (문장 끝 마침표 ${r.punctuated}개 추가)` : ''}. 나누려면 커서를 두고 「여기서 나누기」를 누르세요.`);
    } catch (e) { fail(e); }
  }
  async function loadBackup() {
    const f = await pickFile('.json');
    if (!f) return;
    try {
      const d = JSON.parse(await f.text());
      if (!d || !Array.isArray(d.steps)) throw new Error('백업 파일 형식이 아닙니다. 「백업」으로 내려받은 .json 파일을 골라 주세요.');
      st.title = String(d.title || '').slice(0, 60); titleIn.value = st.title;
      if (langs.some((l) => l.code === d.language)) st.language = d.language;
      st.source = 'backup';
      setSteps(d.steps.slice(0, MAX_STEPS).map((s) => ({ title: String(s.title || ''), body: String(s.body || '') })), '백업 파일에서 제목·언어·단계를 불러왔습니다.');
    } catch (e) { fail(e); }
  }

  function draw() {
    put(left, 
      h('div', { class: 'field' }, h('div', { class: 'lbl-row' }, h('label', { class: 'lbl' }, '스크립트 제목'), counter(titleIn, 60, 37)), titleIn),
      h('div', { class: 'field' }, h('label', { class: 'lbl' }, '언어'),
        h('div', { class: 'chips' }, langs.map((l) => h('button', { type: 'button', class: 'chip' + (st.language === l.code ? ' on' : ''), onclick: () => { st.language = l.code; draw(); } }, l.label)))),
      h('div', { class: 'seg full', style: { margin: '16px 0 12px' } },
        h('button', { type: 'button', class: st.tab === 'paste' ? 'on' : '', onclick: () => { st.tab = 'paste'; draw(); } }, '원고 붙여넣기'),
        h('button', { type: 'button', class: st.tab === 'ai' ? 'on' : '', onclick: () => { st.tab = 'ai'; draw(); } }, 'AI 제안')),
      st.tab === 'ai' ? aiView() : (st.mode === 'paste' ? pasteView() : stepsView()),
      st.tab === 'paste' && st.mode === 'paste' ? h('button', { class: 'btn sm ghost', style: { marginTop: '8px' }, onclick: loadSrt }, 'SRT 파일로 올리기') : null);
    check();
  }

  saveBtn.onclick = async () => {
    saveBtn.disabled = true; saveBtn.textContent = '저장하고 있습니다…';
    const payload = { title: st.title, language: st.language, steps: st.steps.map((s) => ({ title: s.title.trim(), body: s.body.trim() })), source: st.source };
    try {
      if (existing) await api('PUT', `/api/scripts/${existing.id}`, payload);
      else await api('POST', '/api/scripts', payload);
      m.close();
      toast(existing ? '스크립트를 고쳤습니다.' : '스크립트를 저장했습니다.', { action: { label: '영상 만들기로 가기', fn: () => go('create') } });
      onSaved && onSaved();
    } catch (e) { fail(e); saveBtn.textContent = '스크립트 저장'; check(); }
  };
  draw();
}
