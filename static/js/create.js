/* 영상 만들기 화면 (+ 꾸미기 바꾸기) */
'use strict';

const VOICE_MODES = [
  ['clone', '등록한 목소리로 읽기'],
  ['recording', '직접 녹음'],
  ['silent', '소리 없이 (연습)'],
];

App.pages.create = {
  title: '영상 만들기',
  async render(main, query) {
    const recomposeId = query.get('recompose');
    const S = App.settings;
    const base = S.settings.caption_style;
    const logoUrl = S.logo ? S.logo.url : null;
    const [scriptsRes, feats, avRes, vcRes] = await Promise.all([
      api('GET', '/api/scripts'), api('GET', '/api/features'), api('GET', '/api/avatars'), api('GET', '/api/voices')]);
    const scripts = scriptsRes.scripts;
    const eng = feats.engine || {};
    const avatars = avRes.items.filter((a) => !['failed', 'uploading'].includes(a.status));
    const voices = vcRes.items;

    const st = {
      title: '', scriptId: null, avatar: null, style: { ...base }, stepIndex: 0, recompose: null,
      mode: voices.length && eng.tts_ready ? 'clone' : 'recording', voiceId: voices[0] ? voices[0].id : null,
      recs: {}, lipsync: true,
    };

    if (recomposeId) {
      const v = await api('GET', `/api/videos/${recomposeId}`);
      st.recompose = v;
      st.title = v.title;
      st.style = { ...base, ...v.style };
      st.avatar = { id: v.avatar_id, name: v.avatar_name, preview_image: v.avatar_preview, orientation: v.aspect === '9:16' ? 'portrait' : 'landscape' };
    } else {
      if (scripts.length) {
        const pre = +query.get('script');
        const s0 = scripts.find((s) => s.id === pre) || scripts[0];
        st.scriptId = s0.id; st.title = s0.title;
      }
      st.avatar = avatars.find((a) => !a.demo) || avatars[0] || null;
    }
    const curScript = () => scripts.find((s) => s.id === st.scriptId);
    const curSteps = () => (st.recompose ? st.recompose.steps : (curScript() || {}).steps || []);
    const ttsLang = (code) => (S.language_presets.find((p) => p.code === code) || {}).tts;

    /* ---- 1. 제목 ---- */
    const titleIn = h('input', { class: 'input', value: st.title, maxlength: 60, placeholder: '영상 제목을 입력하세요' });
    titleIn.addEventListener('input', () => { st.title = titleIn.value; drawPreview(); check(); });

    /* ---- 2. 스크립트 ---- */
    const scriptBox = h('div', {});
    const scriptSearch = h('input', { class: 'input', placeholder: `제목으로 찾기 (${scripts.length}개)`, style: { marginBottom: '10px' } });
    scriptSearch.addEventListener('input', () => drawScripts());
    function drawScripts() {
      const q = scriptSearch.value.trim().toLowerCase();
      const list = scripts.filter((s) => !q || s.title.toLowerCase().includes(q));
      put(scriptBox, !scripts.length ?
        h('div', { class: 'empty' }, h('b', {}, '저장한 스크립트가 없습니다.'), '원고를 붙여넣어 먼저 저장해 주세요.',
          h('div', { style: { marginTop: '10px' } }, h('button', { class: 'btn primary sm', onclick: () => go('script?new=1') }, '스크립트 등록으로 이동'))) :
        h('div', { class: 'script-pick' }, list.length ? list.map((s) => h('button', { type: 'button', class: 'pick' + (s.id === st.scriptId ? ' on' : ''), onclick: () => {
          const wasAuto = !st.title || scripts.some((x) => x.title === st.title);
          st.scriptId = s.id; st.stepIndex = 0; st.recs = {};
          if (wasAuto) { st.title = s.title; titleIn.value = s.title; }
          drawScripts(); drawVoice(); drawPreview(); check();
        } },
        h('span', { class: 'radio' }),
        h('span', { class: 'grow' }, h('b', {}, s.title), h('span', { class: 'small faint' }, ' · ', fmtDate(s.created_at).slice(0, 10)),
          h('div', { class: 'meta' }, h('span', { class: 'tag' }, langLabel(s.language)), h('span', { class: 'tag' }, `${s.chars}자`),
            h('span', { class: 'tag' }, `단계 ${s.steps.length}`), h('span', { class: 'tag' }, `약 ${fmtDurKo(s.est_seconds)}`),
            !s.reviewed ? h('span', { class: 'tag warn' }, '검수 전 번역') : null)))) :
          h('div', { class: 'empty' }, `「${q}」 제목의 스크립트가 없습니다.`)));
    }

    /* ---- 3. 아바타 ---- */
    const avatarBox = h('div', {});
    function drawAvatars() {
      if (st.recompose) {
        put(avatarBox, h('div', { class: 'notice' }, `꾸미기 바꾸기는 이미 만든 음성·입모양 영상(${st.avatar.name || '아바타'})을 그대로 씁니다. 자막·로고만 다시 입혀 몇 분이면 끝납니다.`));
        return;
      }
      put(avatarBox,
        !avatars.some((a) => !a.demo) ? h('div', { class: 'notice', style: { marginBottom: '10px' } }, '아직 등록한 원장님 아바타가 없습니다. ',
          h('a', { href: '#/studio' }, '[아바타·목소리]에서 등록하기'), ' — 그 전에는 연습용 아바타로 시험할 수 있습니다.') : null,
        h('div', { class: 'avatar-grid' }, avatars.map((a) => {
          const [label, cls] = AV_STATUS[a.status] || [a.status, ''];
          return h('button', { type: 'button', class: 'av' + (st.avatar && st.avatar.id === a.id ? ' on' : ''), title: a.name, onclick: () => {
            st.avatar = a; drawAvatars(); drawLip(); drawPreview(); check();
          } },
          h('div', { class: 'img', style: { backgroundImage: a.preview_image ? `url("${a.preview_image}")` : null } }, h('span', { class: 'o tag ' + cls }, label)),
          h('div', { class: 'nm' }, a.name),
          h('div', { class: 'mt' }, a.kind === 'photo' ? '사진' : '영상', ' · ', a.orientation === 'portrait' ? '9:16' : '16:9'));
        })));
    }

    /* ---- 4. 목소리 ---- */
    const voiceBox = h('div', {});
    function drawVoice() {
      if (st.recompose) { put(voiceBox); return; }
      const sc = curScript();
      const steps = curSteps();
      const langOk = sc && ttsLang(sc.language);
      let body;
      if (st.mode === 'clone') {
        if (!eng.tts_ready) body = h('div', { class: 'notice warn' }, '목소리 엔진이 아직 설치되지 않았습니다. 설정 → 영상 엔진을 확인하거나 「직접 녹음」을 써 주세요.');
        else if (!voices.length) body = h('div', { class: 'notice' }, '등록한 목소리가 없습니다. ', h('a', { href: '#/studio' }, '[아바타·목소리]에서 15~30초 녹음해 등록'), '해 주세요.');
        else if (sc && !langOk) body = h('div', { class: 'notice warn' }, `${langLabel(sc.language)} 는 목소리 엔진이 지원하지 않는 언어입니다. 「직접 녹음」을 써 주세요.`);
        else {
          body = h('div', {},
            h('select', { class: 'input', onchange: (e) => { st.voiceId = +e.target.value; } },
              voices.map((v) => h('option', { value: v.id, selected: v.id === st.voiceId }, `${v.name} · ${langLabel(v.language)} · ${v.seconds}초 녹음`))),
            h('div', { class: 'hint' }, '등록한 녹음과 같은 목소리로 원고를 한 문장씩 읽습니다. 숫자·영어 약어는 소리 나는 대로 한글로 적으면 더 정확합니다 (예: 5분 → 오 분).'));
        }
      } else if (st.mode === 'recording') {
        body = h('div', { class: 'stack' },
          h('div', { class: 'hint', style: { marginTop: 0 } }, '단계마다 원장님이 직접 읽은 녹음을 올리거나 여기서 녹음합니다. 가장 자연스러운 목소리가 나옵니다.'),
          steps.map((s, i) => {
            const rec = st.recs[i];
            const statusEl = h('span', { class: 'tag ' + (rec ? 'ok' : '') }, rec ? `✓ ${rec.seconds}초` : '녹음 없음');
            const upload = async (file) => {
              put(statusEl, '올리는 중…'); statusEl.className = 'tag';
              const fd = new FormData(); fd.append('file', file);
              try { const r = await api('POST', '/api/recordings', fd); st.recs[i] = r; put(statusEl, `✓ ${r.seconds}초`); statusEl.className = 'tag ok'; check(); }
              catch (e) { fail(e); delete st.recs[i]; put(statusEl, '녹음 없음'); check(); }
            };
            const fileIn = h('input', { type: 'file', accept: 'audio/*,video/*', style: { display: 'none' }, onchange: () => fileIn.files[0] && upload(fileIn.files[0]) });
            return h('div', { class: 'opt' },
              h('div', { class: 'row between' }, h('b', { style: { color: stepColor(i) } }, `${i + 1}단계 ${s.title || ''}`), statusEl),
              h('p', { class: 'small', style: { margin: '6px 0 10px', color: 'var(--ink-2)', lineHeight: 1.7 } }, s.body),
              h('div', { class: 'row' }, recorder({ onDone: (f) => upload(f), label: '녹음' }), h('button', { type: 'button', class: 'btn sm ghost', onclick: () => fileIn.click() }, '파일 올리기'), fileIn));
          }));
      } else {
        body = h('div', { class: 'notice' }, '소리 없는 연습 영상을 만듭니다. 자막·배지·로고가 어떻게 보이는지 확인하는 용도이며, 말하는 시간은 글자 수로 짐작합니다.');
      }
      put(voiceBox,
        h('div', { class: 'seg', style: { marginBottom: '12px' } }, VOICE_MODES.map(([v, l]) =>
          h('button', { type: 'button', class: st.mode === v ? 'on' : '', onclick: () => { st.mode = v; drawVoice(); drawLip(); check(); } }, l))),
        body);
    }

    /* ---- 입모양 ---- */
    const lipBox = h('div', {});
    function lipReason() {
      if (st.recompose) return '꾸미기 바꾸기는 이미 만든 입모양을 그대로 씁니다.';
      if (!st.avatar) return '아바타를 골라 주세요.';
      if (st.avatar.demo) return '연습용 아바타는 입모양이 없습니다.';
      if (st.mode === 'silent') return '소리가 없으면 입모양을 맞출 수 없습니다.';
      if (!eng.lipsync_ready) return '입모양 엔진이 아직 설치되지 않았습니다 (설정 → 영상 엔진).';
      if (st.avatar.status === 'unprepared') return '이 아바타는 입모양 준비가 안 됐습니다. [아바타·목소리]에서 「입모양 준비」를 눌러 주세요.';
      return '';
    }
    function drawLip() {
      const why = lipReason();
      const can = !why;
      const on = can && st.lipsync;
      const inp = h('input', { type: 'checkbox', checked: on, disabled: !can, onchange: () => { st.lipsync = inp.checked; check(); } });
      const busy = can && ['pending', 'preparing'].includes(st.avatar.status);
      put(lipBox, h('div', { class: 'toggle-row' },
        h('div', {}, h('div', { class: 't' }, '입모양 맞추기'),
          h('div', { class: 'd' }, can ? (busy ? '아바타 입모양 준비가 끝나면 이어서 만들어집니다.' : '원장님 입이 음성에 맞춰 움직입니다. 끄면 아바타 영상을 그대로 반복합니다.') : why)),
        h('label', { class: 'switch' }, inp, h('span'))));
    }

    /* ---- 미리보기 · 자막 설정 · 만들기 ---- */
    const pvBox = h('div', {});
    function drawPreview() {
      const steps = curSteps();
      const portrait = st.avatar && st.avatar.orientation === 'portrait';
      put(pvBox,
        h('div', { class: 'row between', style: { marginBottom: '8px' } },
          h('div', { class: 'row' }, h('b', {}, '미리보기'), h('span', { class: 'tag brand' }, `화면비율 자동적용: ${portrait ? '세로 9:16' : '가로 16:9'}`)),
          h('button', { class: 'btn sm', onclick: bigPreview }, '⤢ 크게 보기')),
        h('div', { class: 'pv-wrap' }, renderPreview({
          aspect: portrait ? 'portrait' : 'landscape', image: st.avatar && st.avatar.preview_image, style: st.style, steps,
          stepIndex: st.stepIndex, orgName: S.settings.org_name, title: st.title, logoUrl })),
        stepLegend(steps, st.stepIndex, (i) => { st.stepIndex = i; drawPreview(); }),
        h('p', { class: 'small faint', style: { margin: '6px 0 0' } }, '완성되면 이렇게 보입니다. 단계 막대를 누르면 그 단계 배지를 볼 수 있습니다.'));
    }
    function bigPreview() {
      const portrait = st.avatar && st.avatar.orientation === 'portrait';
      const pv = renderPreview({ aspect: portrait ? 'portrait' : 'landscape', image: st.avatar && st.avatar.preview_image, style: st.style, steps: curSteps(), stepIndex: st.stepIndex, orgName: S.settings.org_name, title: st.title, logoUrl });
      if (portrait) pv.style.height = '78vh';
      modal({ title: '크게 보기', size: 'wide', body: h('div', { class: 'pv-wrap' }, pv) });
    }

    const editor = styleEditor({ style: st.style, base, fonts: S.fonts, hasLogo: !!S.logo, onChange: (s) => { st.style = s; drawPreview(); } });

    const makeBtn = h('button', { class: 'btn primary xl' });
    const reason = h('div', { class: 'make-reason' });
    function check() {
      let why = '';
      const sc = curScript();
      const steps = curSteps();
      const recSecs = Object.values(st.recs).reduce((n, r) => n + (r.seconds || 0), 0);
      const est = !st.recompose && st.mode === 'recording' && recSecs ? recSecs + steps.length * 0.7 + 1 : (sc ? sc.est_seconds : 0);
      if (!st.title.trim()) why = '영상 제목을 입력하세요.';
      else if (!st.recompose && !sc) why = '스크립트를 골라 주세요.';
      else if (!st.avatar) why = '아바타를 골라 주세요.';
      else if (!feats.ffmpeg) why = 'ffmpeg 가 설치되어 있지 않습니다. README 의 설치 안내를 따라 주세요.';
      else if (!st.recompose && st.mode === 'clone' && (!eng.tts_ready || !voices.length || !ttsLang(sc.language))) why = '목소리를 쓸 수 없습니다. 위 4번 안내를 확인해 주세요.';
      else if (!st.recompose && st.mode === 'recording' && steps.some((_, i) => !st.recs[i])) why = `단계마다 녹음을 올려 주세요 (${Object.keys(st.recs).length}/${steps.length}).`;
      else if (!st.recompose && st.mode !== 'recording' && est > S.max_seconds) why = `원고가 너무 깁니다. 예상 길이 ${fmtDurKo(est)} · 최대 ${fmtDurKo(S.max_seconds)}`;
      makeBtn.disabled = !!why;
      makeBtn.textContent = st.recompose ? '꾸미기 다시 입히기' : '영상 만들기';
      const lip = !lipReason() && st.lipsync;
      const note = st.recompose ? '보통 1~3분' :
        st.mode === 'silent' ? '연습 영상 · 몇십 초' :
          lip ? `예상 길이 약 ${fmtDurKo(est)} · 입모양까지 맞추면 영상 1분에 보통 5~15분 걸립니다 (그래픽카드에 따라 다름)` :
            `예상 길이 약 ${fmtDurKo(est)} · 입모양 없이 · 몇 분`;
      put(reason, why ? h('span', { style: { color: 'var(--bad)' } }, why) : h('span', {}, note, h('br'), '모든 처리는 이 PC 안에서 합니다. 창을 닫아도 프로그램이 켜져 있으면 계속 만들어집니다.'));
    }
    makeBtn.onclick = async () => {
      makeBtn.disabled = true;
      try {
        let r;
        if (st.recompose) {
          r = await api('POST', `/api/videos/${st.recompose.id}/recompose`, { title: st.title, style: st.style });
        } else {
          const sc = curScript();
          const payload = {
            title: st.title, script_id: sc.id, avatar_id: st.avatar.id, voice_mode: st.mode, voice_id: st.voiceId,
            recordings: curSteps().map((_, i) => (st.recs[i] || {}).id), lipsync: !lipReason() && st.lipsync, style: st.style,
          };
          if (!sc.reviewed) {
            if (!await confirmBox({ title: '검수 전 번역 원고', message: '이 스크립트는 기계번역이고 검수 전입니다. 환자에게 나가는 영상은 검수 후 만드세요.\n그래도 만들까요?', okLabel: '그래도 만들기', danger: true })) { check(); return; }
            payload.confirm_unreviewed = true;
          }
          r = await api('POST', '/api/videos', payload);
        }
        progressModal(r.id);
      } catch (e) { fail(e); check(); }
    };

    add(main,
      pageHead(st.recompose ? '꾸미기 바꾸기' : '영상 만들기',
        st.recompose ? '음성과 입모양 영상은 그대로 두고 자막·로고·배치만 다시 입힙니다. 원래 영상은 생성 이력에 그대로 남습니다.' :
          '스크립트·아바타·목소리를 고르고 한 번 누르면 자막과 로고까지 입힌 완성본이 나옵니다. 모든 처리는 이 PC 안에서 합니다.'),
      h('div', { class: 'create-grid' },
        h('div', {},
          h('div', { class: 'card' }, h('h2', {}, h('span', { class: 'num' }, 1), '영상 제목'),
            h('div', { class: 'lbl-row', style: { marginTop: '8px' } }, h('span', { class: 'small muted' }, '처음에는 고른 스크립트 제목이 들어갑니다.'), counter(titleIn, 60, 37)), titleIn),
          !st.recompose ? h('div', { class: 'card' },
            h('div', { class: 'row between' }, h('h2', {}, h('span', { class: 'num' }, 2), '스크립트'), h('a', { href: '#/script?new=1', class: 'small' }, '+ 새 스크립트 등록')),
            h('p', { class: 'desc' }, '미리 저장해 둔 원고 중 하나를 고릅니다.'), scriptSearch, scriptBox) : null,
          h('div', { class: 'card' },
            h('div', { class: 'row between' }, h('h2', {}, h('span', { class: 'num' }, st.recompose ? 2 : 3), '아바타'), h('a', { href: '#/studio', class: 'small' }, '+ 아바타 등록')),
            h('p', { class: 'desc' }, '가로로 찍은 아바타는 가로 16:9, 세로는 세로 9:16 영상이 됩니다.'), avatarBox,
            h('div', { style: { marginTop: '12px' } }, lipBox)),
          !st.recompose ? h('div', { class: 'card' },
            h('div', { class: 'row between' }, h('h2', {}, h('span', { class: 'num' }, 4), '목소리'), h('a', { href: '#/studio', class: 'small' }, '+ 목소리 등록')),
            voiceBox) : null),
        h('div', { class: 'sticky' },
          h('div', { class: 'card' }, pvBox,
            h('details', { class: 'fold' }, h('summary', {}, '자막 표시 설정 추가 편집하기'),
              h('p', { class: 'small muted', style: { margin: '8px 0 0' } }, '이 영상에만 적용됩니다. 완성 뒤에도 「꾸미기 바꾸기」로 바꿀 수 있습니다.'), editor.el),
            h('div', { style: { marginTop: '16px' } }, makeBtn, reason)))));

    drawScripts(); drawAvatars(); drawVoice(); drawLip(); drawPreview(); check();
  },
};

/* 만드는 중 진행 상황 창 */
function progressModal(vid) {
  const body = h('div', {});
  let timer = null;
  const m = modal({ title: '영상을 만들고 있습니다', size: 'mid', body,
    foot: [h('span', { class: 'small muted grow' }, '이 창을 닫아도 만들기는 계속됩니다.'),
      h('button', { class: 'btn', onclick: () => m.close() }, '닫기'),
      h('button', { class: 'btn primary', onclick: () => { m.close(); go('history'); } }, '생성 이력으로')],
    onClose: () => clearInterval(timer) });
  const STG = [
    ['음성 만들기', '원장님 목소리로 원고를 읽거나, 직접 녹음한 파일을 정리합니다'],
    ['입모양 맞추기', '원장님 입이 음성에 맞게 움직이도록 영상을 다시 그립니다 (끄면 바로 넘어감)'],
    ['꾸미기 입히기', '병원명·단계 배지·자막·로고를 입힙니다 · 보통 1~3분'],
  ];
  async function tick() {
    let v;
    try { v = await api('GET', `/api/videos/${vid}`); } catch (e) { return; }
    const stage = v.status === 'done' ? 4 : v.stage;
    put(body,
      h('div', { class: 'stage-list' }, STG.map(([t, d], i) => h('div', { class: 'stage' + (stage > i + 1 ? ' done' : stage === i + 1 ? ' now' : '') },
        h('span', { class: 'b' }, stage > i + 1 ? '✓' : i + 1),
        h('div', { class: 'grow' }, h('div', { class: 't' }, t), h('div', { class: 'd' }, d),
          stage === i + 1 && v.progress != null ? h('div', { class: 'progress', style: { width: '100%', marginTop: '6px' } }, h('i', { style: { width: `${Math.round(v.progress * 100)}%` } })) : null)))),
      v.status === 'queued' ? h('div', { class: 'notice' }, v.queue_pos ? `대기열 ${v.queue_pos}번째입니다. 앞선 작업이 끝나면 차례로 만들어집니다.` : '곧 시작합니다.') : null,
      v.message && v.status !== 'done' ? h('p', { class: 'small muted' }, v.message) : null,
      v.status === 'failed' ? h('div', { class: 'notice bad', style: { whiteSpace: 'pre-line' } }, '만들지 못했습니다: ', v.error) : null,
      v.status === 'done' ? h('div', { class: 'stack' }, h('div', { class: 'notice ok' }, '완성됐습니다!'),
        h('video', { src: `/api/videos/${vid}/file`, controls: true, style: { width: '100%', maxHeight: '50vh', background: '#000', borderRadius: '10px' } })) : null);
    if (['done', 'failed', 'cancelled'].includes(v.status)) clearInterval(timer);
  }
  tick();
  timer = setInterval(tick, 2500);
}
