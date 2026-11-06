/* 영상 만들기 화면 (+ 꾸미기 바꾸기) */
'use strict';

App.pages.create = {
  title: '영상 만들기',
  async render(main, query) {
    const recomposeId = query.get('recompose');
    const S = App.settings;
    const base = S.settings.caption_style;
    const logoUrl = S.logo ? S.logo.url : null;
    const [scriptsRes, feats] = await Promise.all([api('GET', '/api/scripts'), api('GET', '/api/features')]);
    const scripts = scriptsRes.scripts;

    const st = {
      title: '', scriptId: null, avatar: null, voiceId: '', style: { ...base }, stepIndex: 0,
      bg: { type: 'none', value: '#E8EEF7', url: '' }, own: 'private', recompose: null,
    };

    if (recomposeId) {
      const v = await api('GET', `/api/videos/${recomposeId}`);
      st.recompose = v;
      st.title = v.title;
      st.style = { ...base, ...v.style };
      st.avatar = { id: v.avatar_id, name: v.avatar_name, preview_image: v.avatar_preview, orientation: v.aspect === '9:16' ? 'portrait' : 'landscape' };
    } else if (scripts.length) {
      const pre = +query.get('script');
      const s0 = scripts.find((s) => s.id === pre) || scripts[0];
      st.scriptId = s0.id; st.title = s0.title;
    }
    const curScript = () => scripts.find((s) => s.id === st.scriptId);
    const curSteps = () => (st.recompose ? st.recompose.steps : (curScript() || {}).steps || []);

    /* ---- 왼쪽: 제목 · 스크립트 · 아바타 ---- */
    const titleIn = h('input', { class: 'input', value: st.title, maxlength: 60, placeholder: '영상 제목을 입력하세요' });
    titleIn.addEventListener('input', () => { st.title = titleIn.value; drawPreview(); check(); });

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
          st.scriptId = s.id; st.stepIndex = 0;
          if (wasAuto) { st.title = s.title; titleIn.value = s.title; }
          drawScripts(); drawPreview(); check();
        } },
        h('span', { class: 'radio' }),
        h('span', { class: 'grow' }, h('b', {}, s.title), h('span', { class: 'small faint' }, ' · ', fmtDate(s.created_at).slice(0, 10)),
          h('div', { class: 'meta' }, h('span', { class: 'tag' }, langLabel(s.language)), h('span', { class: 'tag' }, `${s.chars}자`),
            h('span', { class: 'tag' }, `단계 ${s.steps.length}`), h('span', { class: 'tag' }, `약 ${fmtDurKo(s.est_seconds)}`),
            !s.reviewed ? h('span', { class: 'tag warn' }, '검수 전 번역') : null)))) :
          h('div', { class: 'empty' }, `「${q}」 제목의 스크립트가 없습니다.`)));
    }

    const avatarBox = h('div', {});
    let avatars = [], nextToken = null, avErr = null, connected = feats.heygen, loadingAv = false;
    async function loadAvatars(more) {
      loadingAv = true; drawAvatars();
      try {
        const r = await api('GET', `/api/avatars?ownership=${st.own}${more && nextToken ? '&token=' + encodeURIComponent(nextToken) : ''}`);
        avatars = more ? avatars.concat(r.items) : r.items;
        nextToken = r.next_token; avErr = r.error; connected = r.connected;
        if (!st.avatar && avatars.length) {
          const firstReal = avatars.find((a) => !a.demo) || avatars[0];
          st.avatar = firstReal; drawPreview();
        }
      } catch (e) { avErr = e.message; }
      loadingAv = false; drawAvatars(); check();
    }
    function drawAvatars() {
      if (st.recompose) {
        put(avatarBox, h('div', { class: 'notice' }, `꾸미기 바꾸기는 이미 만든 아바타 영상(${st.avatar.name || '아바타'})을 그대로 씁니다. HeyGen 비용이 다시 들지 않습니다.`));
        return;
      }
      put(avatarBox, 
        h('div', { class: 'row between', style: { marginBottom: '10px' } },
          h('div', { class: 'seg' },
            h('button', { type: 'button', class: st.own === 'private' ? 'on' : '', onclick: () => { st.own = 'private'; loadAvatars(); } }, '우리 병원'),
            h('button', { type: 'button', class: st.own === 'public' ? 'on' : '', disabled: !connected, onclick: () => { st.own = 'public'; loadAvatars(); } }, '공개 아바타')),
          h('button', { class: 'btn sm', onclick: () => loadAvatars() }, icon('refresh'), '목록 새로고침')),
        !connected ? h('div', { class: 'notice', style: { marginBottom: '10px' } }, 'HeyGen 연결 전에는 연습용 아바타만 쓸 수 있습니다(비용 없음). ',
          isOperator() ? h('a', { href: '#/settings' }, '설정에서 연결하기') : '운영자에게 HeyGen 연결을 요청하세요.') : null,
        avErr ? h('div', { class: 'notice bad', style: { marginBottom: '10px' } }, '아바타 목록을 불러오지 못했습니다 — ', avErr) : null,
        loadingAv && !avatars.length ? h('div', { class: 'muted' }, '아바타 목록을 불러오는 중…') : null,
        h('div', { class: 'avatar-grid' }, avatars.map((a) => h('button', { type: 'button', class: 'av' + (st.avatar && st.avatar.id === a.id ? ' on' : ''), title: a.name, onclick: () => {
          st.avatar = a; st.voiceId = ''; drawAvatars(); drawExtra(); drawPreview(); check();
        } },
        h('div', { class: 'img', style: { backgroundImage: a.preview_image ? `url("${a.preview_image}")` : null } },
          h('span', { class: 'o tag ' + (a.demo ? 'ok' : '') }, a.demo ? '연습 · 무료' : (a.orientation === 'portrait' ? '세로형' : '가로형'))),
        h('div', { class: 'nm' }, a.name),
        h('div', { class: 'mt' }, a.demo ? '비용 없음' : (a.mine ? '우리 병원' : '공개'), ' · ', a.orientation === 'portrait' ? '9:16' : '16:9')))),
        nextToken ? h('button', { class: 'btn sm', style: { marginTop: '10px', width: '100%' }, disabled: loadingAv, onclick: () => loadAvatars(true) }, loadingAv ? '불러오는 중…' : '더보기') : null,
        avatars.length === 0 && !loadingAv && connected && st.own === 'private' ? h('p', { class: 'small muted' }, 'HeyGen 계정에 만든 아바타가 없습니다. HeyGen 에서 원장님 아바타를 만든 뒤 「목록 새로고침」을 눌러 주세요.') : null);
    }

    /* 목소리·배경 */
    const extraBox = h('div', {});
    let voices = null;
    function drawExtra() {
      if (st.recompose || !st.avatar || st.avatar.demo) { put(extraBox, ); return; }
      const sel = h('select', { class: 'input', onchange: () => { st.voiceId = sel.value; } },
        h('option', { value: '' }, '아바타 기본 목소리' + (st.avatar.default_voice_id ? '' : ' (없으면 언어에 맞는 목소리)')),
        (voices || []).map((v) => h('option', { value: v.id, selected: st.voiceId === v.id }, `${v.mine ? '★ ' : ''}${v.name} · ${v.language || ''}${v.gender ? ' · ' + v.gender : ''}`)));
      const isPhoto = st.avatar.type === 'photo_avatar';
      put(extraBox, h('div', { class: 'card' },
        h('h2', {}, h('span', { class: 'num' }, 4), '목소리 · 배경 (선택)'),
        h('p', { class: 'desc' }, '건드리지 않으면 아바타 기본 목소리와 원래 배경을 씁니다.'),
        h('div', { class: 'field' }, h('label', { class: 'lbl' }, '목소리'), sel,
          voices === null ? h('button', { class: 'btn sm ghost', style: { marginTop: '6px' }, onclick: async () => {
            try { const sc = curScript(); voices = (await api('GET', `/api/voices?language=${sc ? sc.language : ''}`)).items; drawExtra(); } catch (e) { fail(e); }
          } }, '다른 목소리 목록 불러오기') : null),
        h('div', { class: 'field' }, h('label', { class: 'lbl' }, '배경'),
          isPhoto ? h('div', {},
            h('div', { class: 'seg' }, [['none', '원래 배경'], ['color', '단색'], ['image', '이미지 주소']].map(([v, l]) =>
              h('button', { type: 'button', class: st.bg.type === v ? 'on' : '', onclick: () => { st.bg.type = v; drawExtra(); drawPreview(); } }, l))),
            st.bg.type === 'color' ? h('div', { class: 'row', style: { marginTop: '8px' } }, h('input', { type: 'color', value: st.bg.value, oninput: (e) => { st.bg.value = e.target.value; drawPreview(); } }), h('span', { class: 'small muted' }, st.bg.value)) : null,
            st.bg.type === 'image' ? h('input', { class: 'input', style: { marginTop: '8px' }, placeholder: 'https://… (공개된 이미지 주소)', value: st.bg.url, oninput: (e) => { st.bg.url = e.target.value; } }) : null) :
            h('p', { class: 'small muted', style: { margin: 0 } }, '배경은 포토 아바타를 골랐을 때만 바꿀 수 있습니다. 다른 아바타는 원래 장면을 그대로 씁니다.'))));
    }

    /* ---- 오른쪽: 미리보기 · 자막 설정 · 만들기 ---- */
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
      const est = sc ? sc.est_seconds : 0;
      if (!st.title.trim()) why = '영상 제목을 입력하세요.';
      else if (!st.recompose && !sc) why = '스크립트를 골라 주세요.';
      else if (!st.avatar) why = loadingAv ? '아바타 목록을 불러오는 중입니다.' : '아바타를 골라 주세요.';
      else if (!st.recompose && !st.avatar.demo && !connected) why = 'HeyGen 연결이 필요합니다 — 설정에서 API 키를 등록해 주세요.';
      else if (!feats.ffmpeg) why = 'ffmpeg 가 설치되어 있지 않습니다. README 의 설치 안내를 따라 주세요.';
      else if (!st.recompose && est > S.max_seconds) why = `원고가 너무 깁니다. 예상 길이 ${fmtDurKo(est)} · 최대 ${fmtDurKo(S.max_seconds)}`;
      makeBtn.disabled = !!why;
      makeBtn.textContent = st.recompose ? '꾸미기 다시 입히기' : '영상 만들기';
      const cost = st.recompose ? '아바타 비용은 다시 들지 않습니다 · 보통 1~3분' :
        (st.avatar && st.avatar.demo ? '연습 모드 · HeyGen 비용 없음 · 몇십 초' : `HeyGen 비용이 듭니다 · 예상 길이 약 ${fmtDurKo(est)} · 보통 5~10분`);
      put(reason, why ? h('span', { style: { color: 'var(--bad)' } }, why) : h('span', {}, cost, h('br'), '창을 닫아도 프로그램이 켜져 있으면 계속 만들어집니다.'));
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
            title: st.title, script_id: sc.id, avatar_id: st.avatar.id, avatar_name: st.avatar.name, avatar_preview: st.avatar.preview_image,
            orientation: st.avatar.orientation, voice_id: st.voiceId || st.avatar.default_voice_id || null, style: st.style,
            background: st.bg.type === 'color' ? { type: 'color', value: st.bg.value } : (st.bg.type === 'image' && st.bg.url ? { type: 'image', url: st.bg.url } : null),
          };
          if (!sc.reviewed) {
            if (!await confirmBox({ title: '검수 전 번역 원고', message: '이 스크립트는 기계번역이고 검수 전입니다. 환자에게 나가는 영상은 검수 후 만드세요.\n그래도 만들까요?', okLabel: '그래도 만들기', danger: true })) { check(); return; }
            payload.confirm_unreviewed = true;
          }
          if (!st.avatar.demo && !await confirmBox({ title: 'HeyGen 으로 영상 만들기', message: `HeyGen 비용이 듭니다 (예상 길이 약 ${fmtDurKo(sc.est_seconds)}).\n같은 영상이 두 번 결제되지 않도록 한 번만 눌러 주세요.`, okLabel: '만들기' })) { check(); return; }
          r = await api('POST', '/api/videos', payload);
        }
        progressModal(r.id);
      } catch (e) { fail(e); check(); }
    };

    add(main, 
      pageHead(st.recompose ? '꾸미기 바꾸기' : '영상 만들기',
        st.recompose ? '아바타 영상은 그대로 두고 자막·로고·배치만 다시 입힙니다. 원래 영상은 생성 이력에 그대로 남습니다.' :
          '스크립트와 아바타를 고르고 한 번 누르면 자막과 로고까지 입힌 완성본이 나옵니다.'),
      h('div', { class: 'create-grid' },
        h('div', {},
          h('div', { class: 'card' }, h('h2', {}, h('span', { class: 'num' }, 1), '영상 제목'),
            h('div', { class: 'lbl-row', style: { marginTop: '8px' } }, h('span', { class: 'small muted' }, '처음에는 고른 스크립트 제목이 들어갑니다.'), counter(titleIn, 60, 37)), titleIn),
          !st.recompose ? h('div', { class: 'card' },
            h('div', { class: 'row between' }, h('h2', {}, h('span', { class: 'num' }, 2), '스크립트'), h('a', { href: '#/script?new=1', class: 'small' }, '+ 새 스크립트 등록')),
            h('p', { class: 'desc' }, '미리 저장해 둔 원고 중 하나를 고릅니다.'), scriptSearch, scriptBox) : null,
          h('div', { class: 'card' },
            h('div', { class: 'row between' }, h('h2', {}, h('span', { class: 'num' }, st.recompose ? 2 : 3), '아바타'), h('span', { class: 'small muted' }, '목소리는 아바타 기본 목소리')),
            h('p', { class: 'desc' }, '가로형 아바타는 가로 16:9, 세로형은 세로 9:16 으로 자동 적용됩니다.'), avatarBox),
          extraBox),
        h('div', { class: 'sticky' },
          h('div', { class: 'card' }, pvBox,
            h('details', { class: 'fold' }, h('summary', {}, '자막 표시 설정 추가 편집하기'),
              h('p', { class: 'small muted', style: { margin: '8px 0 0' } }, '이 영상에만 적용됩니다. 완성 뒤에도 「꾸미기 바꾸기」로 바꿀 수 있습니다.'), editor.el),
            h('div', { style: { marginTop: '16px' } }, makeBtn, reason)))));

    drawScripts(); drawAvatars(); drawExtra(); drawPreview(); check();
    if (!st.recompose) loadAvatars();
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
    ['아바타 영상 만들기', 'HeyGen 이 아바타가 말하는 영상을 만듭니다 · 보통 5~10분 (연습 모드는 몇 초)'],
    ['말하는 시점 맞추기', '문장마다 자막과 단계가 바뀌는 순간을 찾습니다 · 몇 초'],
    ['꾸미기 입히기', '자막과 로고를 얹고 소리를 붙입니다 · 보통 1~3분'],
  ];
  async function tick() {
    let v;
    try { v = await api('GET', `/api/videos/${vid}`); } catch (e) { return; }
    const stage = v.status === 'done' ? 4 : v.stage;
    put(body, 
      h('div', { class: 'stage-list' }, STG.map(([t, d], i) => h('div', { class: 'stage' + (stage > i + 1 ? ' done' : stage === i + 1 ? ' now' : '') },
        h('span', { class: 'b' }, stage > i + 1 ? '✓' : i + 1), h('div', {}, h('div', { class: 't' }, t), h('div', { class: 'd' }, d))))),
      v.status === 'queued' ? h('div', { class: 'notice' }, v.queue_pos ? `대기열 ${v.queue_pos}번째입니다. 앞선 영상이 끝나면 차례로 만들어집니다.` : '곧 시작합니다.') : null,
      v.message && v.status !== 'done' ? h('p', { class: 'small muted' }, v.message) : null,
      v.status === 'failed' ? h('div', { class: 'notice bad' }, '만들지 못했습니다: ', v.error) : null,
      v.status === 'done' ? h('div', { class: 'stack' }, h('div', { class: 'notice ok' }, '완성됐습니다!'),
        h('video', { src: `/api/videos/${vid}/file`, controls: true, style: { width: '100%', maxHeight: '50vh', background: '#000', borderRadius: '10px' } })) : null);
    if (['done', 'failed', 'cancelled'].includes(v.status)) clearInterval(timer);
  }
  tick();
  timer = setInterval(tick, 3000);
}
