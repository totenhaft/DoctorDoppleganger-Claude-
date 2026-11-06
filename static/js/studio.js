/* 아바타·목소리 화면 — 원장님 얼굴(영상·사진)과 목소리(녹음)를 이 PC 에 등록합니다. */
'use strict';

const AV_STATUS = {
  uploading: ['올리는 중', ''], pending: ['준비 대기', ''], preparing: ['입모양 준비 중', 'brand'],
  ready: ['사용 가능', 'ok'], unprepared: ['입모양 준비 안 됨', 'warn'], failed: ['준비 실패', 'bad'], demo: ['연습 · 무료', 'ok'],
};

function engineNotice(eng) {
  if (eng && eng.tts_ready && eng.lipsync_ready) return null;
  const miss = [];
  if (!eng || !eng.tts_ready) miss.push('목소리 엔진');
  if (!eng || !eng.lipsync_ready) miss.push('입모양 엔진');
  return h('div', { class: 'notice warn', style: { marginBottom: '16px' } },
    h('b', {}, `${miss.join('·')}이 아직 준비되지 않았습니다. `),
    '지금은 「직접 녹음」과 「입모양 없이」로 만들 수 있습니다. 설치하려면 프로그램 폴더의 ', h('b', {}, 'install_engines.bat'),
    ' 을 실행한 뒤 ', isOperator() ? h('a', { href: '#/settings' }, '설정 → 영상 엔진') : '설정 → 영상 엔진', '에서 「다시 확인」을 누르세요.');
}

/* ---------- 녹음기 (브라우저 마이크) ---------- */
function recorder({ onDone, maxSec = 120, label = '녹음 시작' }) {
  const box = h('div', { class: 'row' });
  let mr = null, chunks = [], t0 = 0, timer = null, stream = null;
  const draw = (state, extra) => {
    if (state === 'idle') {
      put(box, h('button', { type: 'button', class: 'btn', onclick: start }, h('span', { style: { color: 'var(--bad)' } }, '●'), label), extra);
    } else if (state === 'rec') {
      const sec = h('b', { class: 'mono' }, '0:00');
      put(box, h('button', { type: 'button', class: 'btn danger', onclick: stop }, '■ 멈추기'), h('span', { class: 'tag bad' }, '녹음 중'), sec);
      timer = setInterval(() => {
        const s = (Date.now() - t0) / 1000;
        sec.textContent = fmtDur(s);
        if (s >= maxSec) stop();
      }, 250);
    }
  };
  async function start() {
    if (!navigator.mediaDevices || !window.MediaRecorder) { toast('이 브라우저는 녹음을 지원하지 않습니다. 크롬이나 엣지를 쓰거나 파일을 올려 주세요.', { bad: true }); return; }
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: true, autoGainControl: true } }); }
    catch (e) { toast('마이크를 쓸 수 없습니다. 브라우저 주소창 왼쪽에서 마이크 권한을 허용해 주세요. (이 PC 에서 열었을 때만 녹음할 수 있습니다)', { bad: true, ms: 8000 }); return; }
    chunks = [];
    mr = new MediaRecorder(stream);
    mr.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    mr.onstop = () => {
      clearInterval(timer);
      stream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(chunks, { type: mr.mimeType || 'audio/webm' });
      const secs = (Date.now() - t0) / 1000;
      const url = URL.createObjectURL(blob);
      draw('idle', h('span', { class: 'row' }, h('audio', { src: url, controls: true, style: { height: '36px' } }), h('span', { class: 'small muted' }, `${fmtDur(secs)}`)));
      box.querySelector('button').lastChild.textContent = '다시 녹음';
      onDone(new File([blob], 'recording.webm', { type: blob.type }), secs);
    };
    t0 = Date.now();
    mr.start();
    draw('rec');
  }
  function stop() { if (mr && mr.state === 'recording') mr.stop(); }
  draw('idle');
  return box;
}

App.pages.studio = {
  title: '아바타·목소리',
  async render(main) {
    const [avs, vcs] = await Promise.all([api('GET', '/api/avatars'), api('GET', '/api/voices')]);
    const eng = avs.engine;
    const avatars = avs.items.filter((a) => !a.demo);
    add(main, pageHead('아바타·목소리', '원장님 얼굴(영상 또는 사진)과 목소리를 한 번 등록해 두면 영상마다 골라 씁니다. 모든 파일은 이 PC 에만 저장됩니다.'),
      engineNotice(eng),
      h('div', { class: 'card' },
        h('div', { class: 'row between' }, h('h2', {}, '아바타 (원장님 얼굴)'), h('button', { class: 'btn primary', onclick: () => avatarModal(eng) }, '+ 아바타 등록')),
        h('p', { class: 'desc' }, '정면에서 찍은 15~20초 영상이 가장 자연스럽습니다. 사진 한 장도 되지만 고개가 움직이지 않습니다.'),
        avatars.length ? h('div', { class: 'avatar-grid', style: { gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))' } }, avatars.map((a) => avatarCard(a, eng))) :
          h('div', { class: 'empty' }, h('b', {}, '아직 등록한 아바타가 없습니다.'), '「+ 아바타 등록」으로 원장님 영상을 올려 주세요. 그 전에는 연습용 아바타로 시험할 수 있습니다.')),
      h('div', { class: 'card' },
        h('div', { class: 'row between' }, h('h2', {}, '목소리 (원장님 목소리)'), h('button', { class: 'btn primary', onclick: () => voiceModal(eng) }, '+ 목소리 등록')),
        h('p', { class: 'desc' }, '정해진 문장을 15~30초 읽어 녹음하면, 목소리 엔진이 그 목소리로 원고를 읽습니다.'),
        vcs.items.length ? h('div', {}, vcs.items.map((v) => voiceRow(v, eng))) :
          h('div', { class: 'empty' }, h('b', {}, '아직 등록한 목소리가 없습니다.'), '목소리를 등록하지 않아도 영상마다 「직접 녹음」으로 만들 수 있습니다.')));
    if (avatars.some((a) => ['uploading', 'pending', 'preparing'].includes(a.status))) {
      App.timers.push(setInterval(async () => {
        try {
          const r = await api('GET', '/api/avatars');
          const now = r.items.filter((a) => !a.demo);
          if (JSON.stringify(now.map((a) => [a.status, a.progress])) !== JSON.stringify(avatars.map((a) => [a.status, a.progress]))) App.render();
        } catch { /* 무시 */ }
      }, 3000));
    }
  },
};

function avatarCard(a, eng) {
  const [label, cls] = AV_STATUS[a.status] || [a.status, ''];
  const busy = ['uploading', 'pending', 'preparing'].includes(a.status);
  return h('div', { class: 'av', style: { cursor: 'default' } },
    h('div', { class: 'img', style: { aspectRatio: a.orientation === 'portrait' ? '3/4' : '16/10', backgroundImage: a.preview_image ? `url("${a.preview_image}")` : null } },
      h('span', { class: 'o tag ' + cls }, label)),
    h('div', { class: 'nm', style: { fontSize: '14px' } }, a.name),
    h('div', { class: 'mt' }, a.kind === 'photo' ? '사진' : '영상', ' · ', a.orientation === 'portrait' ? '세로 9:16' : '가로 16:9', a.width ? ` · ${a.width}×${a.height}` : ''),
    busy ? h('div', { style: { marginTop: '6px' } },
      h('div', { class: 'progress' + (a.progress ? '' : ' indet'), style: { width: '100%' } }, h('i', { style: { width: `${Math.round((a.progress || 0) * 100)}%` } })),
      h('div', { class: 'small muted', style: { marginTop: '4px' } }, a.message || '')) : null,
    a.status === 'unprepared' ? h('div', { class: 'small muted', style: { marginTop: '6px' } }, a.message) : null,
    a.status === 'failed' ? h('div', { class: 'small', style: { color: 'var(--bad)', marginTop: '6px', whiteSpace: 'pre-line' } }, (a.error || '').slice(0, 200)) : null,
    h('div', { class: 'actions', style: { marginTop: '8px' } },
      a.kind === 'video' ? h('a', { class: 'icon-btn', href: `/api/avatars/${a.id}/source`, target: '_blank', title: '원본 보기', 'aria-label': '원본 보기' }, icon('play')) : null,
      iconBtn('edit', '이름 바꾸기', async () => {
        const name = prompt('새 이름', a.name);
        if (!name) return;
        try { await api('PATCH', `/api/avatars/${a.id}`, { name }); App.render(); } catch (e) { fail(e); }
      }),
      ['unprepared', 'failed', 'ready'].includes(a.status) ? h('button', { class: 'btn sm', disabled: !eng.lipsync_ready, title: eng.lipsync_ready ? '' : '입모양 엔진 설치 후 쓸 수 있습니다', onclick: async () => {
        try { await api('POST', `/api/avatars/${a.id}/prepare`); toast('입모양 준비를 시작합니다. 20초 영상 기준 몇 분 걸립니다.'); App.render(); } catch (e) { fail(e); }
      } }, a.status === 'ready' ? '다시 준비' : '입모양 준비') : null,
      iconBtn('trash', '삭제', async () => {
        if (!await confirmTyped({ title: '아바타 삭제', message: `「${a.name}」과 준비 자료를 이 PC 에서 지웁니다. 이미 만든 영상은 그대로 남습니다.`, word: '삭제' })) return;
        try { await api('DELETE', `/api/avatars/${a.id}`); toast('삭제했습니다.'); App.render(); } catch (e) { fail(e); }
      }, { danger: true, disabled: a.status === 'preparing' })));
}

function avatarModal(eng) {
  const name = h('input', { class: 'input', maxlength: 40, placeholder: '예: 원장님 진료실 가로' });
  const fileIn = h('input', { type: 'file', accept: 'video/*,image/*', class: 'input' });
  const agree = h('input', { type: 'checkbox' });
  const btn = h('button', { class: 'btn primary' }, '올리기');
  const m = modal({ title: '아바타 등록', size: 'mid', body: h('div', { class: 'stack' },
    h('div', { class: 'notice' }, h('b', {}, '이렇게 찍어 주세요 (휴대폰도 충분합니다)'),
      h('ul', { style: { margin: '6px 0 0', paddingLeft: '18px' } },
        h('li', {}, '정면, 가슴 위까지. 얼굴이 화면 높이의 1/3 이상 되게'),
        h('li', {}, '삼각대나 거치대로 고정하고, 밝고 고른 조명 (역광·안경 반사 피하기)'),
        h('li', {}, '15~20초 동안 고개를 크게 움직이지 말고, 입은 가볍게 다물거나 조용히 말하듯이'),
        h('li', {}, '가로로 찍으면 가로(16:9) 영상, 세로로 찍으면 세로(9:16) 영상이 만들어집니다'),
        h('li', {}, '앞 20초만 씁니다. 사진(jpg·png)도 되지만 고개가 움직이지 않습니다'))),
    h('div', {}, h('label', { class: 'lbl' }, '이름'), name),
    h('div', {}, h('label', { class: 'lbl' }, '영상 또는 사진 파일'), fileIn),
    h('label', { class: 'row', style: { alignItems: 'flex-start', flexWrap: 'nowrap', fontSize: '13px' } }, agree,
      h('span', {}, '원장님 본인 얼굴이거나, 얼굴 주인에게 AI 아바타로 쓰는 것에 대한 동의를 받았습니다.')),
    !eng.lipsync_ready ? h('div', { class: 'small muted' }, '입모양 엔진이 아직 없어 지금은 원본만 저장합니다. 엔진을 설치한 뒤 「입모양 준비」를 누르면 됩니다.') : null),
  foot: [h('button', { class: 'btn', onclick: () => m.close() }, '취소'), btn] });
  btn.onclick = async () => {
    const f = fileIn.files[0];
    if (!name.value.trim()) { toast('이름을 입력해 주세요.'); return; }
    if (!f) { toast('파일을 골라 주세요.'); return; }
    if (!agree.checked) { toast('동의 확인 칸에 체크해 주세요.'); return; }
    const fd = new FormData(); fd.append('name', name.value); fd.append('consent', 'yes'); fd.append('file', f);
    btn.disabled = true; btn.textContent = '올리고 다듬는 중…';
    try { await api('POST', '/api/avatars', fd); m.close(); toast('아바타를 올렸습니다.' + (eng.lipsync_ready ? ' 입모양 준비를 시작합니다.' : '')); App.render(); }
    catch (e) { fail(e); btn.disabled = false; btn.textContent = '올리기'; }
  };
}

function voiceRow(v, eng) {
  return h('div', { class: 'lang-row', style: { flexWrap: 'wrap' } },
    h('div', { class: 'grow' }, h('b', {}, v.name), h('span', { class: 'code', style: { marginLeft: '8px' } }, `${langLabel(v.language)} · ${v.seconds}초`),
      h('div', { class: 'small muted', style: { marginTop: '2px' } }, `읽은 문장: ${v.ref_text.slice(0, 60)}${v.ref_text.length > 60 ? '…' : ''}`)),
    h('audio', { src: v.audio, controls: true, preload: 'none', style: { height: '34px' } }),
    h('button', { class: 'btn sm', disabled: !eng.tts_ready, title: eng.tts_ready ? '' : '목소리 엔진 설치 후 쓸 수 있습니다', onclick: () => voiceTest(v) }, '시험 듣기'),
    iconBtn('trash', '삭제', async () => {
      if (!await confirmTyped({ title: '목소리 삭제', message: `「${v.name}」 녹음을 이 PC 에서 지웁니다. 이미 만든 영상은 그대로 남습니다.`, word: '삭제' })) return;
      try { await api('DELETE', `/api/voices/${v.id}`); toast('삭제했습니다.'); App.render(); } catch (e) { fail(e); }
    }, { danger: true }));
}

function voiceTest(v) {
  const ta = h('textarea', { class: 'input', rows: 3 }); ta.value = '안녕하세요. 오늘 진료는 편안하셨나요? 처방해 드린 안약은 하루 네 번 넣어 주세요.';
  const out = h('div', {});
  const btn = h('button', { class: 'btn primary' }, '읽어 보기');
  btn.onclick = async () => {
    btn.disabled = true; btn.textContent = '만드는 중… (30초~1분)';
    put(out, h('div', { class: 'progress indet', style: { width: '100%' } }, h('i')));
    try { const r = await api('POST', `/api/voices/${v.id}/test`, { text: ta.value }); put(out, h('audio', { src: r.audio, controls: true, autoplay: true, style: { width: '100%' } })); }
    catch (e) { put(out); fail(e); }
    btn.disabled = false; btn.textContent = '읽어 보기';
  };
  modal({ title: `${v.name} · 시험 듣기`, size: 'mid', body: h('div', { class: 'stack' },
    h('p', { class: 'small muted', style: { margin: 0 } }, '목소리 모델을 불러오느라 처음 한 번은 시간이 걸립니다. 영상을 만드는 중에는 쓸 수 없습니다.'), ta, btn, out) });
}

function voiceModal(eng) {
  const S = App.settings.settings;
  const presets = App.settings.language_presets;
  const langs = S.languages.filter((l) => (presets.find((p) => p.code === l.code) || {}).tts);
  const name = h('input', { class: 'input', maxlength: 40, value: '원장님 목소리' });
  const lang = h('select', { class: 'input' }, langs.map((l) => h('option', { value: l.code, selected: l.code === S.default_language }, l.label)));
  const passage = h('textarea', { class: 'input', rows: 5, style: { fontSize: '17px', lineHeight: '1.8' } });
  passage.value = `안녕하세요. ${S.org_name} 원장입니다. 오늘은 눈 건강을 지키는 생활 습관을 안내해 드리겠습니다. 스마트폰이나 컴퓨터를 오래 보실 때는 한 시간에 한 번씩 먼 곳을 바라보며 눈을 쉬게 해 주세요. 눈이 뻑뻑하거나 충혈이 계속되면 참지 마시고 병원에 들러 주세요. 감사합니다.`;
  let file = null;
  const status = h('div', { class: 'small muted' }, '아직 녹음하지 않았습니다.');
  const setFile = (f, secs) => { file = f; status.textContent = secs ? `녹음 ${fmtDur(secs)} 준비됨 ${secs < 10 ? '· 10초 이상이 좋습니다' : ''}` : `파일: ${f.name}`; };
  const upIn = h('input', { type: 'file', accept: 'audio/*,video/*', class: 'input', onchange: () => { if (upIn.files[0]) setFile(upIn.files[0]); } });
  const agree = h('input', { type: 'checkbox' });
  const btn = h('button', { class: 'btn primary' }, '목소리 저장');
  const m = modal({ title: '목소리 등록', size: 'mid', body: h('div', { class: 'stack' },
    !eng.tts_ready ? h('div', { class: 'notice warn' }, '목소리 엔진이 아직 설치되지 않았습니다. 녹음은 지금 저장해 두고, 엔진을 설치한 뒤 바로 쓸 수 있습니다.') : null,
    h('div', { class: 'two' }, h('div', {}, h('label', { class: 'lbl' }, '이름'), name), h('div', {}, h('label', { class: 'lbl' }, '언어'), lang)),
    h('div', {}, h('label', { class: 'lbl' }, '아래 문장을 평소 진료하실 때 말투로 또박또박 읽어 주세요'), passage,
      h('div', { class: 'hint' }, '다른 문장을 읽어도 됩니다. 단, 이 칸에는 실제로 읽은 내용과 똑같이 적어 주세요. 그래야 목소리가 잘 닮습니다.')),
    h('div', { class: 'notice' }, '조용한 방에서, 마이크(휴대폰)와 20~30cm 거리에서 15~30초 녹음해 주세요. 에어컨·음악 소리가 들어가면 그 잡음까지 따라 합니다.'),
    h('div', { class: 'opt' }, h('div', { class: 't' }, '여기서 바로 녹음'), recorder({ onDone: setFile, maxSec: 60 })),
    h('div', { class: 'opt' }, h('div', { class: 't' }, '또는 녹음 파일 올리기 (mp3·m4a·wav 등)'), upIn),
    status,
    h('label', { class: 'row', style: { alignItems: 'flex-start', flexWrap: 'nowrap', fontSize: '13px' } }, agree,
      h('span', {}, '원장님 본인 목소리이거나, 목소리 주인에게 AI 음성으로 쓰는 것에 대한 동의를 받았습니다.'))),
  foot: [h('button', { class: 'btn', onclick: () => m.close() }, '취소'), btn] });
  btn.onclick = async () => {
    if (!file) { toast('먼저 녹음하거나 파일을 올려 주세요.'); return; }
    if (!agree.checked) { toast('동의 확인 칸에 체크해 주세요.'); return; }
    const fd = new FormData();
    fd.append('name', name.value); fd.append('language', lang.value); fd.append('ref_text', passage.value); fd.append('consent', 'yes'); fd.append('file', file);
    btn.disabled = true; btn.textContent = '저장 중…';
    try { const r = await api('POST', '/api/voices', fd); m.close(); toast(`목소리를 저장했습니다 (${r.seconds}초).`); App.render(); }
    catch (e) { fail(e); btn.disabled = false; btn.textContent = '목소리 저장'; }
  };
}
