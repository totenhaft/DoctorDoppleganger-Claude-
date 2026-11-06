/* 안내문구 설정 · 설정 · 계정 관리 · 사용 가이드 */
'use strict';

/* ================= 안내문구 설정 (환자 공유 페이지) ================= */
const SHARE_EXAMPLES = {
  '수술 후 안내': '수술 후 관리 방법을 안내해 드립니다.\n영상을 끝까지 보시고, 통증이나 충혈이 심해지면 바로 병원으로 연락해 주세요.',
  '진료 전 안내': '진료 전에 알아 두시면 좋은 내용을 안내해 드립니다.\n예약 시간 10분 전까지 도착해 주세요.',
  '복약 안내': '처방받은 약을 드시는 방법을 안내해 드립니다.\n정해진 시간과 양을 지켜 주세요.',
  '검사 안내': '검사 과정을 미리 안내해 드립니다.\n검사 당일에는 렌즈를 빼고 오시면 됩니다.',
};

App.pages.share = {
  title: '안내문구 설정',
  async render(main) {
    if (!isOperator()) { add(main, pageHead('안내문구 설정'), h('div', { class: 'notice' }, '운영자만 바꿀 수 있습니다.')); return; }
    const r = await api('GET', '/api/share-page');
    const saved = { ...r.page };
    const cur = { ...r.page };
    const heading = h('input', { class: 'input', maxlength: 60 });
    const message = h('textarea', { class: 'input', rows: 6, maxlength: 500 });
    const notice = h('textarea', { class: 'input', rows: 4, maxlength: 320 });
    const frame = h('iframe', { class: 'share-frame', title: '환자 화면 미리보기', sandbox: '' });
    const dirtyTag = h('span', { class: 'tag warn hidden' }, '저장 전');
    const saveBtn = h('button', { class: 'btn primary' }, '저장');
    const fill = () => { heading.value = cur.heading; message.value = cur.message; notice.value = cur.ai_notice; };
    fill();
    let t = null;
    const update = () => {
      cur.heading = heading.value; cur.message = message.value; cur.ai_notice = notice.value;
      const dirty = JSON.stringify(cur) !== JSON.stringify(saved);
      dirtyTag.classList.toggle('hidden', !dirty); saveBtn.disabled = !dirty;
      clearTimeout(t);
      t = setTimeout(async () => {
        try { const res = await api('POST', '/api/share-page/preview', cur, { raw: true }); frame.srcdoc = (await res.text()).replace('src="/api/logo"', `src="${location.origin}/api/logo"`); } catch { /* 무시 */ }
      }, 250);
    };
    [heading, message, notice].forEach((el) => el.addEventListener('input', update));
    saveBtn.onclick = async () => {
      try { await api('PUT', '/api/share-page', cur); Object.assign(saved, cur); update(); toast('저장했습니다. 이미 보낸 링크에도 바로 반영됩니다.'); } catch (e) { fail(e); }
    };
    add(main, pageHead('안내문구 설정', '환자가 공유 링크로 열었을 때 영상 위아래에 보이는 문구를 바꾸고 미리 봅니다.'),
      h('div', { class: 'share-grid' },
        h('div', { class: 'card' },
          h('div', { class: 'field' }, h('div', { class: 'lbl-row' }, h('label', { class: 'lbl' }, '상단 문구'), counter(heading, 60)), heading, h('div', { class: 'hint' }, '처음에는 병원 이름이 들어 있습니다.')),
          h('div', { class: 'field' }, h('label', { class: 'lbl' }, '예시 문구'),
            h('div', { class: 'chips' }, Object.entries(SHARE_EXAMPLES).map(([k, v]) => h('button', { class: 'chip', onclick: () => { message.value = v; update(); } }, k)))),
          h('div', { class: 'field' }, h('div', { class: 'lbl-row' }, h('label', { class: 'lbl' }, '안내 본문'), counter(message, 500)), message,
            h('div', { class: 'hint' }, '영상 아래에 나옵니다. 줄바꿈은 그대로 보이고, 꺾쇠 괄호(< >)는 쓸 수 없습니다.')),
          h('div', { class: 'field' }, h('div', { class: 'lbl-row' }, h('label', { class: 'lbl' }, 'AI 고지 문구'), counter(notice, 320)), notice,
            h('div', { class: 'hint' }, '영상 바로 아래에 항상 나옵니다. 「AI」나 「인공지능」이 들어가야 저장됩니다.')),
          h('div', { class: 'notice', style: { marginTop: '12px' } }, '인공지능 기본법은 생성형 AI 로 만든 결과물에 그 사실을 알리도록 정하고 있습니다. 그래서 AI 고지는 늘 영상 아래에 보입니다.'),
          h('div', { class: 'row', style: { justifyContent: 'flex-end', marginTop: '14px' } },
            h('button', { class: 'btn', onclick: () => { Object.assign(cur, r.defaults); fill(); update(); } }, '초기화'), saveBtn)),
        h('div', { class: 'card' }, h('div', { class: 'row between', style: { marginBottom: '10px' } }, h('b', {}, '미리보기'), h('div', { class: 'row' }, dirtyTag, h('span', { class: 'tag' }, '환자 화면과 같음'))), frame)));
    update();
  },
};

/* ================= 설정 ================= */
App.pages.settings = {
  title: '설정',
  async render(main) {
    await App.reloadSettings();
    const S = App.settings;
    const op = isOperator();
    const saved = JSON.parse(JSON.stringify(S.settings));
    const cur = JSON.parse(JSON.stringify(S.settings));
    const savebar = h('div', { class: 'savebar' });
    const dis = !op;

    function markDirty() {
      const dirty = JSON.stringify(cur) !== JSON.stringify(saved);
      put(savebar, 
        h('span', { class: 'small muted grow' }, dirty ? '저장하지 않은 변경이 있습니다.' : '브랜딩·자막 기본값·언어·엔진 설정은 아래 버튼으로 함께 저장됩니다. 로고·글꼴·Claude 키는 누르는 즉시 저장됩니다.'),
        h('button', { class: 'btn', disabled: !dirty, onclick: () => App.render() }, '되돌리기'),
        h('button', { class: 'btn primary', disabled: !dirty || !op, onclick: async () => {
          try {
            await api('PUT', '/api/settings', { org_name: cur.org_name, org_name_i18n: cur.org_name_i18n, org_desc: cur.org_desc, languages: cur.languages, default_language: cur.default_language, caption_style: cur.caption_style, tts_model: cur.tts_model, tts_precision: cur.tts_precision, lipsync_batch: cur.lipsync_batch, claude_model: cur.claude_model, public_base_url: cur.public_base_url });
            toast('설정을 저장했습니다.'); await App.reloadSettings(); App.render();
          } catch (e) { fail(e); }
        } }, '설정 저장'));
    }
    const bind = (el, key, sub) => { el.addEventListener('input', () => { if (sub) cur[key][sub] = el.value; else cur[key] = el.value; markDirty(); }); return el; };

    /* --- 영상 엔진 (이 PC 의 그래픽카드로 목소리·입모양을 만듦) --- */
    function engineCard() {
      const e = S.engine || {};
      const okTag = (ok, yes, no) => h('span', { class: 'tag ' + (ok ? 'ok' : 'warn') }, ok ? yes : no);
      // 버튼 묶음으로 고르는 설정 (key: 설정 이름, opts: [[값, 글자], ...])
      const pick = (key, opts) => h('div', { class: 'seg' }, opts.map(([v, l]) =>
        h('button', { type: 'button', disabled: dis, class: String(cur[key]) === String(v) ? 'on' : '', onclick: (ev) => {
          cur[key] = v; markDirty(); [...ev.target.parentNode.children].forEach((b) => b.classList.toggle('on', b === ev.target));
        } }, l)));
      const have = e.tts_models || [];
      const big = (e.vram_gb || 0) >= 12;
      const modelSeg = pick('tts_model', [['auto', '자동'], ['0.6B', '가벼움 0.6B'], ['1.7B', '고품질 1.7B']]);
      const precSeg = pick('tts_precision', [['auto', '자동'], ['float32', '정확'], ['float16', '빠름']]);
      const batchSeg = pick('lipsync_batch', [[0, '자동'], [4, '4장'], [8, '8장'], [16, '16장']]);
      return h('div', { class: 'card' },
        h('div', { class: 'row between' }, h('h2', {}, '영상 엔진 (이 PC 에서 직접 만들기)'),
          h('button', { class: 'btn sm', onclick: async (ev) => {
            ev.target.disabled = true; ev.target.textContent = '확인 중… (최대 1분)';
            try { await api('GET', '/api/engine?refresh=1'); await App.reloadSettings(); App.render(); } catch (er) { fail(er); ev.target.disabled = false; }
          } }, icon('refresh'), '다시 확인')),
        h('p', { class: 'desc' }, '외부 서비스 없이 이 PC 의 그래픽카드로 원장님 목소리(Qwen3-TTS)와 입모양(MuseTalk 1.5)을 만듭니다.'),
        h('dl', { class: 'kv' },
          h('dt', {}, '설치'), h('dd', {}, okTag(e.installed, '설치됨', '설치 안 됨')),
          h('dt', {}, '그래픽카드'), h('dd', {}, e.cuda ? `${e.gpu || 'NVIDIA'} · ${e.vram_gb || '?'}GB` : h('span', { class: 'tag warn' }, e.installed ? '못 찾음 (드라이버 확인)' : '—')),
          h('dt', {}, '목소리 엔진'), h('dd', {}, okTag(e.tts_ready, '준비됨', '준비 안 됨')),
          h('dt', {}, '입모양 엔진'), h('dd', {}, okTag(e.lipsync_ready, '준비됨', '준비 안 됨'))),
        !e.installed || !e.tts_ready || !e.lipsync_ready ? h('div', { class: 'notice warn' },
          h('b', {}, '설치 방법: '), '프로그램 폴더의 ', h('b', {}, 'install_engines.bat'), ' 을 더블클릭합니다. 약 10GB 를 내려받고 20~60분 걸립니다. 끝나면 이 화면에서 「다시 확인」을 누르세요.',
          e.errors && e.errors.length ? h('details', { style: { marginTop: '8px' } }, h('summary', { style: { cursor: 'pointer' } }, '자세한 상태'),
            h('pre', { style: { whiteSpace: 'pre-wrap', fontSize: '12px', margin: '6px 0 0' } }, e.errors.join('\n'))) : null) : null,
        e.installed && !e.cuda ? h('div', { class: 'notice bad', style: { marginTop: '8px' } }, '그래픽카드(CUDA)를 쓰지 못하고 있습니다. NVIDIA 드라이버를 최신으로 설치한 뒤 PC 를 다시 켜 주세요. 그래픽카드 없이도 돌아가지만 영상 하나에 몇 시간 걸릴 수 있습니다.') : null,
        h('div', { class: 'stack', style: { marginTop: '14px' } },
          h('div', {}, h('label', { class: 'lbl' }, '목소리 모델'), modelSeg,
            h('div', { class: 'hint' }, `자동: 그래픽카드 메모리 12GB 이상(RTX 4080 등)이면 고품질 1.7B, 아니면 0.6B. 설치된 모델: ${have.length ? have.join(', ') : '없음'}`,
              big && e.installed && !have.includes('1.7B') ? ' · 고품질 모델을 쓰려면 명령창에서 python engines\\install.py --tts 1.7B 를 실행하세요.' : '')),
          h('div', {}, h('label', { class: 'lbl' }, '목소리 정밀도'), precSeg,
            h('div', { class: 'hint' }, `자동: ${e.bf16 ? '이 그래픽카드는 bfloat16 을 지원해 빠르고 정확하게 돌립니다.' : 'bfloat16 을 지원하면 bf16, 아니면 float32.'} 목소리가 깨지면 「정확」, 메모리 부족 오류가 나면 「빠름」.`)),
          h('div', {}, h('label', { class: 'lbl' }, '입모양 한 번에 처리할 장수'), batchSeg,
            h('div', { class: 'hint' }, '자동: 12GB 이상이면 16장, 아니면 8장. 메모리 부족 오류가 나면 4장으로 줄이세요.'))),
        !S.ffmpeg ? h('div', { class: 'notice bad', style: { marginTop: '12px' } }, 'ffmpeg 를 찾지 못했습니다. 음성·영상 처리에 꼭 필요합니다. README 의 「ffmpeg 설치」를 따라 설치한 뒤 프로그램을 다시 켜 주세요.') : null);
    }

    /* --- Claude --- */
    function claudeCard() {
      const keyIn = h('input', { class: 'input', type: 'password', autocomplete: 'off', placeholder: 'sk-ant-…', disabled: dis });
      const model = bind(h('input', { class: 'input', value: cur.claude_model, disabled: dis }), 'claude_model');
      return h('div', { class: 'card' },
        h('div', { class: 'row between' }, h('h2', {}, 'Claude AI 연결 (선택)'), S.claude.configured ? h('span', { class: 'tag ok' }, '등록됨') : h('span', { class: 'tag' }, '등록 안 됨')),
        h('p', { class: 'desc' }, '등록하면 「AI 제안」(원고 초안)과 「번역」을 쓸 수 있습니다. 쓰지 않아도 나머지 기능은 모두 됩니다.'),
        h('div', { class: 'row', style: { flexWrap: 'nowrap' } }, keyIn,
          h('button', { class: 'btn primary', disabled: dis, onclick: async () => {
            try { await api('POST', '/api/connection/claude', { api_key: keyIn.value }); toast(keyIn.value ? 'Claude API 키를 저장했습니다.' : 'Claude API 키를 지웠습니다.'); App.render(); } catch (e) { fail(e); }
          } }, '저장')),
        h('div', { class: 'hint' }, 'console.anthropic.com 에서 발급합니다. 비워 두고 저장하면 키를 지웁니다. 원고에 환자 개인정보는 넣지 마세요.'),
        h('div', { class: 'field', style: { marginTop: '12px' } }, h('label', { class: 'lbl' }, '모델 이름'), model, h('div', { class: 'hint' }, '보통은 바꾸지 않아도 됩니다.')));
    }

    /* --- 브랜딩 --- */
    function brandCard() {
      const name = bind(h('input', { class: 'input', value: cur.org_name, maxlength: 40, disabled: dis }), 'org_name');
      const desc = bind(h('textarea', { class: 'input', rows: 2, maxlength: 300, disabled: dis, placeholder: '예: 원장 아바타 기반 진료안내 영상' }), 'org_desc');
      desc.value = cur.org_desc || '';
      const others = cur.languages.filter((l) => !l.code.startsWith('ko'));
      const logo = S.logo;
      const defSel = h('select', { class: 'input', style: { width: 'auto' }, disabled: dis, onchange: () => { cur.default_language = defSel.value; markDirty(); } },
        cur.languages.map((l) => h('option', { value: l.code, selected: l.code === cur.default_language }, `${l.label} · ${l.code}`)));
      return h('div', { class: 'card' },
        h('h2', {}, '브랜딩'), h('p', { class: 'desc' }, '병원명은 완성 영상 왼쪽 위에 나옵니다.'),
        h('div', { class: 'field' }, h('div', { class: 'lbl-row' }, h('label', { class: 'lbl' }, '병원명'), counter(name, 40, 33)), name),
        others.length ? h('div', { class: 'field' }, h('label', { class: 'lbl' }, '번역 영상에 쓸 병원명 표기'),
          h('div', { class: 'stack' }, others.map((l) => {
            const inp = h('input', { class: 'input', value: (cur.org_name_i18n || {})[l.code] || '', placeholder: cur.org_name, disabled: dis });
            inp.addEventListener('input', () => { cur.org_name_i18n = { ...(cur.org_name_i18n || {}), [l.code]: inp.value }; markDirty(); });
            return h('div', { class: 'row', style: { flexWrap: 'nowrap' } }, h('span', { class: 'small', style: { width: '110px' } }, l.label), inp);
          }))) : null,
        h('div', { class: 'field' }, h('label', { class: 'lbl' }, '병원 로고 (영상 아래쪽)'),
          h('div', { class: 'logo-box' },
            h('div', { class: 'img' }, logo ? h('img', { src: logo.url, alt: '병원 로고' }) : h('span', { class: 'small', style: { color: '#CBD5E1' } }, '로고 없음')),
            h('div', { class: 'stack grow' },
              logo ? h('div', { class: 'small muted' }, `${logo.width}×${logo.height}px · ${logo.kb}KB`) : null,
              h('div', { class: 'row' },
                h('button', { class: 'btn sm', disabled: dis, onclick: async () => {
                  const f = await pickFile('image/png'); if (!f) return;
                  const fd = new FormData(); fd.append('file', f);
                  try { await api('POST', '/api/logo', fd); toast('로고를 올렸습니다.'); App.render(); } catch (e) { fail(e); }
                } }, logo ? '로고 바꾸기' : '로고 올리기'),
                logo ? h('button', { class: 'btn sm danger', disabled: dis, onclick: async () => { try { await api('DELETE', '/api/logo'); toast('로고를 뺐습니다.'); App.render(); } catch (e) { fail(e); } } }, '로고 빼기') : null),
              h('div', { class: 'hint', style: { margin: 0 } }, 'PNG · 512KB 이하 · 가로·세로 2048px 이하. 투명 배경을 권합니다. 올리면 바로 적용됩니다.')))),
        h('div', { class: 'field' }, h('label', { class: 'lbl' }, '병원 설명'), desc),
        h('div', { class: 'field' }, h('label', { class: 'lbl' }, '기본언어'), defSel, h('div', { class: 'hint' }, '새 스크립트를 등록할 때 처음 골라져 있는 언어입니다.')));
    }

    /* --- 공유 링크 주소 --- */
    function shareUrlCard() {
      const inp = bind(h('input', { class: 'input', value: cur.public_base_url, placeholder: '예: https://video.yonseisol.com', disabled: dis }), 'public_base_url');
      return h('div', { class: 'card' },
        h('h2', {}, '공유 링크 주소'),
        h('p', { class: 'desc' }, '환자에게 보내는 링크의 앞부분입니다. 비워 두면 지금 접속한 주소(이 PC 에서만 열리는 주소)를 씁니다.'),
        inp, h('div', { class: 'hint' }, '환자 휴대폰에서 열리게 하는 방법은 README 의 「환자에게 링크 보내기」를 참고하세요.'));
    }

    /* --- 자막 기본값 --- */
    function captionCard() {
      const pvBox = h('div', {});
      let stepI = 0;
      const sampleSteps = [{ title: '점안 전 준비', body: '안녕하세요, 원장입니다. 인공눈물 넣는 방법을 안내해 드리겠습니다.' }, { title: '넣는 방법', body: '아래 눈꺼풀을 살짝 당기고 한 방울 넣어 주세요.' }];
      const drawPv = () => put(pvBox, h('div', { class: 'pv-wrap' }, renderPreview({ aspect: 'landscape', style: cur.caption_style, steps: sampleSteps, stepIndex: stepI, orgName: cur.org_name, title: '인공눈물 점안 방법 안내', logoUrl: S.logo && S.logo.url })),
        stepLegend(sampleSteps, stepI, (i) => { stepI = i; drawPv(); }));
      const ed = styleEditor({ style: cur.caption_style, base: S.default_style, baseLabel: '처음 설정값', fonts: S.fonts, hasLogo: !!S.logo, onChange: (s) => { cur.caption_style = s; markDirty(); drawPv(); } });
      drawPv();
      return h('div', { class: 'card' },
        h('h2', {}, '병원 기본 자막 설정'),
        h('p', { class: 'desc' }, '영상 만들기의 「자막 표시 설정」과 같은 구성입니다. 여기서 정한 값이 기본이 되고, 영상마다 바꿀 수 있습니다.'),
        h('div', { class: 'two', style: { alignItems: 'start' } }, ed.el, h('div', { class: 'sticky' }, pvBox)));
    }

    /* --- 글꼴 --- */
    function fontCard() {
      const agree = h('input', { type: 'checkbox', disabled: dis });
      return h('div', { class: 'card' },
        h('h2', {}, '글꼴 업로드'),
        h('p', { class: 'desc' }, '병원이 가진 글꼴 파일(.ttf·.otf)을 올려 자막에 쓸 수 있습니다. 올리면 바로 저장됩니다.'),
        h('label', { class: 'row', style: { alignItems: 'flex-start', flexWrap: 'nowrap', fontSize: '13px' } }, agree,
          h('span', {}, '올리는 글꼴을 영상 제작에 사용할 권리가 있는지 확인했습니다. 글꼴은 저작권 보호를 받으며, 제작사 약관이 영상 사용을 제한할 수 있습니다. (무료 글꼴 예: Pretendard, 본고딕, 나눔고딕)')),
        h('div', { style: { marginTop: '10px' } }, h('button', { class: 'btn sm', disabled: dis, onclick: async () => {
          if (!agree.checked) { toast('먼저 권리 확인 칸에 체크해 주세요.'); return; }
          const f = await pickFile('.ttf,.otf'); if (!f) return;
          const fd = new FormData(); fd.append('file', f); fd.append('consent', 'yes');
          try { await api('POST', '/api/fonts', fd); toast('글꼴을 올렸습니다.'); App.render(); } catch (e) { fail(e); }
        } }, '글꼴 파일 올리기')),
        S.fonts.length ? h('div', { style: { marginTop: '12px' } }, S.fonts.map((f) => h('div', { class: 'lang-row' }, h('b', { class: 'grow' }, f.name), h('span', { class: 'code' }, f.file),
          h('button', { class: 'btn sm danger', disabled: dis, onclick: async () => {
            if (!await confirmBox({ title: '글꼴 사용 중지', message: `${f.name} 글꼴을 지웁니다. 이 글꼴을 쓰던 자막 설정은 기본 글꼴로 나옵니다.`, okLabel: '사용 중지', danger: true })) return;
            try { await api('DELETE', `/api/fonts/${encodeURIComponent(f.file)}`); App.render(); } catch (e) { fail(e); }
          } }, '사용 중지')))) : h('p', { class: 'small muted' }, '올린 글꼴이 없습니다. 기본 글꼴(윈도우: 맑은 고딕)을 씁니다.'));
    }

    /* --- 언어 --- */
    function langCard() {
      const list = h('div', {});
      const draw = () => put(list, ...cur.languages.map((l) => h('div', { class: 'lang-row' },
        h('b', {}, l.label), h('span', { class: 'code' }, l.code),
        !(S.language_presets.find((p) => p.code === l.code) || {}).tts ? h('span', { class: 'tag warn', title: '목소리 엔진이 이 언어를 지원하지 않아 직접 녹음만 쓸 수 있습니다' }, '직접 녹음만') : null,
        h('span', { class: 'grow' }),
        l.code === cur.default_language ? h('span', { class: 'tag brand' }, '기본언어') :
          h('button', { class: 'btn sm', disabled: dis, onclick: () => { cur.default_language = l.code; markDirty(); draw(); } }, '기본으로 지정'),
        h('button', { class: 'btn sm', disabled: dis || l.code === cur.default_language, title: l.code === cur.default_language ? '기본언어는 뺄 수 없습니다' : '', onclick: () => { cur.languages = cur.languages.filter((x) => x.code !== l.code); markDirty(); draw(); } }, '빼기'))));
      draw();
      const sel = h('select', { class: 'input', style: { width: 'auto' }, disabled: dis }, h('option', { value: '' }, '언어 고르기'),
        S.language_presets.filter((p) => !cur.languages.some((l) => l.code === p.code)).map((p) => h('option', { value: p.code }, `${p.label} · ${p.code}`)));
      const custom = h('input', { class: 'input', placeholder: '직접 입력 (예: vi-VN)', style: { width: '180px' }, disabled: dis });
      return h('div', { class: 'card' },
        h('h2', {}, '다국어 사용 설정'), h('p', { class: 'desc' }, '스크립트 등록 때 고를 수 있는 언어입니다. 외국인 환자 안내 영상을 만들 때 씁니다.'),
        list,
        h('div', { class: 'row', style: { marginTop: '12px' } }, sel, custom, h('button', { class: 'btn sm', disabled: dis, onclick: () => {
          const code = (sel.value || custom.value).trim();
          if (!code) { toast('추가할 언어를 골라 주세요.'); return; }
          if (!/^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$/.test(code)) { toast('언어 코드는 BCP-47 꼴이어야 합니다. 예: vi-VN'); return; }
          if (cur.languages.some((l) => l.code === code)) { toast('이미 목록에 있는 언어입니다.'); return; }
          const p = S.language_presets.find((x) => x.code === code);
          cur.languages = [...cur.languages, { code, label: p ? p.label : code }];
          markDirty(); App.pages.settings._redrawLang();
        } }, '+ 추가')));
    }
    let langEl = langCard();
    App.pages.settings._redrawLang = () => { const n = langCard(); langEl.replaceWith(n); langEl = n; };

    add(main, pageHead('설정', '영상 엔진 상태와 병원 정보, 자막 기본값을 관리합니다.'),
      !op ? h('div', { class: 'notice', style: { maxWidth: '920px', marginBottom: '16px' } }, '담당자 계정은 설정을 볼 수만 있습니다. 바꾸려면 운영자에게 요청하세요.') : null,
      h('div', { class: 'settings-grid' }, engineCard(), brandCard(), captionCard(), fontCard(), langEl, shareUrlCard(), claudeCard()),
      savebar);
    markDirty();
  },
};

/* ================= 계정 관리 ================= */
function tempPassword() {
  const a = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789';
  const r = crypto.getRandomValues(new Uint32Array(12));
  let s = Array.from(r, (x) => a[x % a.length]).join('');
  return s.slice(0, 10) + '7k';
}

App.pages.accounts = {
  title: '계정 관리',
  async render(main) {
    if (!isOperator()) { add(main, pageHead('계정 관리'), h('div', { class: 'notice' }, '계정 관리는 운영자만 볼 수 있습니다.')); return; }
    const r = await api('GET', '/api/accounts');
    const STATUS = { pending: ['첫 로그인 전', 'warn'], active: ['사용 중', 'ok'], disabled: ['비활성', ''] };
    const act = async (u, body, msg) => { try { await api('PATCH', `/api/accounts/${encodeURIComponent(u)}`, body); toast(msg); App.render(); } catch (e) { fail(e); } };

    const rows = r.accounts.map((a) => {
      const [label, cls] = a.locked ? ['로그인 잠김', 'bad'] : STATUS[a.status] || [a.status, ''];
      const roleSel = h('select', { class: 'input', style: { width: 'auto', padding: '5px 8px' }, onchange: async () => {
        if (!await confirmBox({ title: '역할 바꾸기', message: `${a.username} 의 역할을 ${roleSel.value === 'operator' ? '운영자' : '담당자'}(으)로 바꿉니다. 그 계정은 다시 로그인해야 합니다.`, okLabel: '바꾸기' })) { roleSel.value = a.role; return; }
        act(a.username, { action: 'role', role: roleSel.value }, '역할을 바꿨습니다.');
      } }, h('option', { value: 'operator', selected: a.role === 'operator' }, '운영자'), h('option', { value: 'staff', selected: a.role === 'staff' }, '담당자'));
      return h('tr', {},
        h('td', { class: 'title-cell' }, a.username, a.username === r.me ? h('span', { class: 'tag brand', style: { marginLeft: '6px' } }, '나') : null),
        h('td', { 'data-l': '역할' }, roleSel),
        h('td', { 'data-l': '상태' }, h('span', { class: 'tag ' + cls }, label)),
        h('td', { 'data-l': '만든 날' }, h('span', { class: 'small muted mono' }, fmtDate(a.created_at).slice(0, 10))),
        h('td', { 'data-l': '관리' }, h('div', { class: 'actions' },
          h('button', { class: 'btn sm', onclick: () => resetModal(a.username) }, '비밀번호 재설정'),
          a.locked ? h('button', { class: 'btn sm', onclick: () => act(a.username, { action: 'unlock' }, '잠금을 풀었습니다.') }, '잠금 해제') : null,
          a.username !== r.me ? (a.status === 'disabled' ?
            h('button', { class: 'btn sm', onclick: () => act(a.username, { action: 'enable' }, '다시 사용할 수 있게 했습니다.') }, '다시 사용') :
            h('button', { class: 'btn sm danger', onclick: async () => { if (await confirmBox({ title: '계정 비활성', message: `${a.username} 을(를) 비활성합니다. 그 계정의 로그인은 모두 끊깁니다.`, okLabel: '비활성', danger: true })) act(a.username, { action: 'disable' }, '비활성했습니다.'); } }, '비활성')) : null)));
    });

    const uIn = h('input', { class: 'input', placeholder: '예: nurse-kim' });
    const pIn = h('input', { class: 'input mono', value: tempPassword() });
    const roleIn = h('select', { class: 'input' }, h('option', { value: 'staff' }, '담당자'), h('option', { value: 'operator' }, '운영자'));
    add(main, pageHead('계정 관리', '같은 병원 직원 계정을 초대하고, 역할을 바꾸고, 비밀번호를 재설정합니다.'),
      h('div', { class: 'card' }, h('h2', {}, '계정 목록'),
        h('table', { class: 'table responsive' }, h('thead', {}, h('tr', {}, ['아이디', '역할', '상태', '만든 날', '관리'].map((t) => h('th', {}, t)))), h('tbody', {}, rows))),
      h('div', { class: 'card' }, h('h2', {}, '계정 초대'),
        h('p', { class: 'desc' }, '운영자는 설정·계정까지 관리하고, 담당자는 원고 등록·영상 만들기·이력만 씁니다.'),
        h('div', { class: 'two' },
          h('div', {}, h('label', { class: 'lbl' }, '아이디'), uIn, h('div', { class: 'hint' }, '영문 소문자·숫자와 . _ @ + - 만, 3자 이상')),
          h('div', {}, h('label', { class: 'lbl' }, '역할'), roleIn)),
        h('div', { class: 'field' }, h('label', { class: 'lbl' }, '임시 비밀번호'),
          h('div', { class: 'row', style: { flexWrap: 'nowrap' } }, pIn, h('button', { class: 'btn', onclick: () => { pIn.value = tempPassword(); } }, '새로 만들기')),
          h('div', { class: 'hint' }, '직접 전해 주세요. 받은 사람은 첫 로그인에서 새 비밀번호를 정합니다.')),
        h('div', { style: { marginTop: '12px' } }, h('button', { class: 'btn primary', onclick: async () => {
          try { await api('POST', '/api/accounts', { username: uIn.value, password: pIn.value, role: roleIn.value }); toast('초대했습니다. 임시 비밀번호를 직접 전해 주세요.'); App.render(); } catch (e) { fail(e); }
        } }, '초대'))));
  },
};

function resetModal(username) {
  const pIn = h('input', { class: 'input mono', value: tempPassword() });
  const m = modal({ title: `${username} 비밀번호 재설정`, body: h('div', { class: 'stack' },
    h('label', { class: 'lbl' }, '임시 비밀번호'), pIn,
    h('div', { class: 'hint' }, '직접 전해 주세요. 그 계정의 로그인은 모두 끊기고, 다음 로그인에서 새 비밀번호를 정합니다.')),
  foot: [h('button', { class: 'btn', onclick: () => m.close() }, '취소'), h('button', { class: 'btn primary', onclick: async () => {
    try { await api('POST', `/api/accounts/${encodeURIComponent(username)}/reset`, { password: pIn.value }); m.close(); toast(`${username} 의 비밀번호를 재설정했습니다.`); App.render(); } catch (e) { fail(e); }
  } }, '재설정')] });
}

/* ================= 사용 가이드 ================= */
App.pages.guide = {
  title: '사용 가이드',
  render(main) {
    const step = (n, title, items) => h('div', { class: 'card' }, h('h2', {}, h('span', { class: 'num' }, n), title), h('ul', {}, items.map((t) => h('li', {}, t))));
    add(main, pageHead('사용 가이드', '4단계를 차례로 따라 하면 영상이 완성됩니다.'),
      h('div', { class: 'guide-steps' },
        step(0, '처음 한 번: 준비', [
          '프로그램 폴더의 install_engines.bat 을 실행해 영상 엔진(목소리·입모양)을 설치합니다. 약 10GB, 20~60분. 설치가 끝나면 설정 → 영상 엔진에서 「다시 확인」.',
          '[아바타·목소리]에서 원장님이 정면에서 찍은 15~20초 영상을 올립니다. 입모양 준비가 자동으로 시작됩니다 (몇 분).',
          '같은 화면에서 정해진 문장을 15~30초 읽어 목소리를 등록하고 「시험 듣기」로 확인합니다.',
          '설정 → 브랜딩에서 병원명과 로고(PNG)를 올리고, 병원 기본 자막 설정을 정한 뒤 「설정 저장」을 누릅니다.',
          '엔진 설치 전에도 「연습용 아바타」와 「직접 녹음」 「소리 없이」로 화면과 자막을 시험할 수 있습니다.']),
        step(1, '스크립트 등록', [
          '「+ 신규 등록」을 누르고 원고를 붙여넣습니다. 빈 줄로 나눈 문단이 한 단계가 됩니다(최대 4단계).',
          '문단 첫 줄이 짧으면 단계 제목이 됩니다. 단계 제목은 영상 배지에만 나오고 읽지 않습니다.',
          '문장 끝에는 마침표를 꼭 넣어 주세요. 목소리 엔진은 문장 단위로 읽고, 자막도 문장 단위로 나뉩니다.',
          '숫자·영어 약어는 소리 나는 대로 적으면 더 정확하게 읽습니다 (예: 5mm → 오 밀리미터).']),
        step(2, '영상 만들기', [
          '스크립트·아바타·목소리를 고릅니다. 목소리는 「등록한 목소리로 읽기」, 「직접 녹음」, 「소리 없이(연습)」 중에서 고릅니다.',
          '「입모양 맞추기」를 켜면 원장님 입이 음성에 맞춰 움직입니다. 끄면 아바타 영상을 그대로 반복합니다.',
          '오른쪽 미리보기에서 병원명·단계 배지·자막·로고 위치를 확인하고, 필요하면 「자막 표시 설정」을 펼쳐 이 영상만 바꿉니다.',
          '「영상 만들기」를 누르면 끝입니다. 영상 1분에 보통 5~15분 걸리고, 브라우저를 닫아도 검은 명령창이 켜져 있으면 계속 만들어집니다.']),
        step(3, '생성 이력', [
          '완성된 영상을 재생하고, 내려받고(mp4), 환자용 공유 링크를 만듭니다.',
          '자막이 어색하면 「꾸미기 바꾸기」로 고칩니다. 음성·입모양은 그대로 두고 자막만 다시 입혀 몇 분이면 끝납니다.',
          '대사를 고치려면 「대사 고쳐 다시 만들기」를 누릅니다 (등록한 목소리로 만든 영상만).',
          '실패한 영상은 「이유 보기」로 까닭을 확인하고 「다시 시도」를 누르면 실패한 단계부터 이어서 합니다.']),
        step(4, '환자에게 보내기', [
          '공유 링크는 로그인 없이 그 영상만 볼 수 있는 주소입니다. 「링크 끄기」를 누르기 전까지 계속 열립니다.',
          '안내문구 설정에서 환자 화면의 상단 문구·안내 본문·AI 고지 문구를 정합니다.',
          '환자 휴대폰에서 열리게 하려면 이 PC 를 인터넷에 공개하는 설정이 필요합니다. README 의 「환자에게 링크 보내기」를 참고하세요. 어렵다면 mp4 를 내려받아 유튜브 「일부 공개」로 올리는 방법도 있습니다.',
          'SNS 홍보용으로 올릴 때는 의료광고 심의 대상인지 확인해 주세요.'])));
  },
};
