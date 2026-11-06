/* 생성 이력 화면 */
'use strict';

App.pages.history = {
  title: '생성 이력',
  state: { q: '', lang: '', page: 0 },
  async render(main) {
    const S = this.state;
    const box = h('div', {});
    const search = h('input', { class: 'input', placeholder: '제목으로 검색', value: S.q });
    const langSel = h('select', { class: 'input', style: { width: 'auto' } }, h('option', { value: '' }, '모든 언어'),
      App.settings.settings.languages.map((l) => h('option', { value: l.code, selected: S.lang === l.code }, l.label)));
    search.addEventListener('input', () => { S.q = search.value; S.page = 0; draw(); });
    langSel.addEventListener('change', () => { S.lang = langSel.value; S.page = 0; draw(); });
    const countEl = h('b', { class: 'mono' });
    add(main, pageHead('생성 이력', '만든 영상을 다시 보고, 환자용 링크를 만들고, 꾸미기를 바꿀 수 있습니다.'),
      h('div', { class: 'card', style: { marginBottom: '16px' } }, h('div', { class: 'row' }, h('div', { class: 'grow' }, search), h('span', { class: 'small muted' }, '영상 '), countEl, langSel)),
      box);

    let videos = [], serverNow = Date.now() / 1000, clientAt = Date.now() / 1000;
    async function load() {
      try {
        const r = await api('GET', '/api/videos');
        videos = r.videos; serverNow = r.now; clientAt = Date.now() / 1000;
        draw();
      } catch (e) { /* 다음 차례에 다시 */ }
    }
    const nowT = () => serverNow + (Date.now() / 1000 - clientAt);

    function statusCell(v) {
      if (v.status === 'done') return h('span', { class: 'tag ok' }, '완성');
      if (v.status === 'queued') return h('div', {}, h('span', { class: 'tag' }, v.queue_pos ? `대기 ${v.queue_pos}번째` : '대기 중'), v.message ? h('div', { class: 'small muted' }, v.message) : null);
      if (v.status === 'failed') return h('div', {}, h('span', { class: 'tag bad' }, '실패'),
        v.has_raw ? h('div', { class: 'small muted' }, '아바타 영상은 저장돼 있습니다') : null,
        h('button', { class: 'btn ghost sm', style: { padding: '2px 0' }, onclick: () => modal({ title: '실패 이유', body: h('pre', { style: { whiteSpace: 'pre-wrap', margin: 0, fontSize: '13px' } }, v.error || '이유를 받지 못했습니다.') }) }, '이유 보기'));
      const el = Math.max(0, nowT() - (v.started_at || v.created_at));
      return h('div', {},
        h('div', { class: 'row', style: { gap: '6px' } }, h('span', { class: 'tag brand' }, `만드는 중 ${v.stage}/3`), h('span', { class: 'small muted mono' }, fmtDur(el))),
        h('div', { class: 'progress' + (v.stage === 1 ? ' indet' : ''), style: { marginTop: '6px' } }, h('i', { style: { width: `${(v.stage / 3) * 100}%` } })),
        v.message ? h('div', { class: 'small muted', style: { maxWidth: '240px' } }, v.message) : null);
    }

    function actions(v) {
      const a = [];
      if (v.status === 'done') {
        a.push(iconBtn('play', '열기 (재생)', () => playModal(v)));
        a.push(h('a', { class: 'icon-btn', href: `/api/videos/${v.id}/file`, target: '_blank', title: '새 창에서 열기', 'aria-label': '새 창에서 열기' }, icon('ext')));
        a.push(iconBtn('link', '환자용 공유 링크', () => shareModal(v, load)));
        a.push(h('a', { class: 'icon-btn', href: `/api/videos/${v.id}/file?download=1`, title: '내려받기 (mp4)', 'aria-label': '내려받기' }, icon('down')));
        a.push(iconBtn('layers', '꾸미기 바꾸기 (아바타 비용 없음)', () => go(`create?recompose=${v.id}`), { disabled: !v.has_raw }));
        a.push(iconBtn('edit', '대사 고쳐 다시 만들기', () => remakeModal(v, load)));
      }
      if (v.status === 'failed') {
        a.push(h('button', { class: 'btn sm', onclick: async () => {
          if (!v.has_raw && !v.demo && !await confirmBox({ title: '처음부터 다시 시도', message: '아바타 영상부터 다시 만듭니다. HeyGen 비용이 다시 들 수 있습니다.', okLabel: '다시 시도' })) return;
          try { await api('POST', `/api/videos/${v.id}/retry`); toast('다시 시도합니다.'); load(); } catch (e) { fail(e); }
        } }, v.has_raw ? '꾸미기만 다시 시도' : '다시 시도'));
        if (v.has_raw) a.push(iconBtn('layers', '꾸미기 바꾸기', () => go(`create?recompose=${v.id}`)));
      }
      if (v.status === 'queued') {
        a.push(h('button', { class: 'btn sm', onclick: async () => {
          if (!await confirmBox({ title: '대기 취소', message: '대기열에서 빼면 이 영상은 만들어지지 않습니다. 아직 보내지 않아 비용은 나가지 않습니다.', okLabel: '대기 취소', danger: true })) return;
          try { await api('POST', `/api/videos/${v.id}/cancel`); toast('대기를 취소했습니다.'); load(); } catch (e) { fail(e); }
        } }, '대기 취소'));
      }
      if (v.has_raw && v.status !== 'queued') a.push(h('a', { class: 'btn sm ghost', href: `/api/videos/${v.id}/file?kind=raw`, target: '_blank', title: '자막·로고를 입히기 전 아바타 영상' }, '원본'));
      if (!['avatar', 'timing', 'compose'].includes(v.status)) {
        a.push(iconBtn('trash', '삭제', async () => {
          if (!await confirmTyped({ title: '영상 삭제', message: `「${v.title}」을(를) 생성 이력과 PC 에서 지웁니다. 공유 링크도 더 이상 열리지 않습니다. 되돌릴 수 없습니다.`, word: '삭제' })) return;
          try { await api('DELETE', `/api/videos/${v.id}`); toast('삭제했습니다.'); load(); } catch (e) { fail(e); }
        }, { danger: true }));
      }
      return h('div', { class: 'actions' }, a);
    }

    function draw() {
      const list = videos.filter((v) => (!S.lang || v.language === S.lang) && (!S.q || v.title.toLowerCase().includes(S.q.toLowerCase())));
      countEl.textContent = `${list.length}건`;
      const pages = Math.max(1, Math.ceil(list.length / 10));
      S.page = Math.min(S.page, pages - 1);
      const shown = list.slice(S.page * 10, S.page * 10 + 10);
      put(box, h('div', { class: 'card' },
        shown.length ? h('table', { class: 'table responsive' },
          h('thead', {}, h('tr', {}, ['미리보기', '제목', '언어', '길이', '상태', '만든 시각', '관리'].map((t) => h('th', {}, t)))),
          h('tbody', {}, shown.map((v) => h('tr', {},
            h('td', { 'data-l': '미리보기' }, v.thumb ? h('img', { class: 'thumb' + (v.aspect === '9:16' ? ' portrait' : ''), src: v.thumb, alt: '', loading: 'lazy' }) : h('div', { class: 'thumb-empty' }, '미리보기 없음')),
            h('td', { class: 'title-cell' }, v.title,
              h('div', { class: 'sub row', style: { gap: '4px' } },
                v.parent_id ? h('span', { class: 'tag' }, '꾸미기 바꿈') : null,
                v.demo ? h('span', { class: 'tag ok' }, '연습') : null,
                !v.reviewed ? h('span', { class: 'tag warn' }, '검수 전 번역') : null,
                v.share_enabled ? h('span', { class: 'tag brand' }, '공유 중') : null,
                h('span', {}, `${v.avatar_name || ''} · ${v.aspect}`))),
            h('td', { 'data-l': '언어' }, langLabel(v.language)),
            h('td', { 'data-l': '길이', class: 'mono' }, v.duration ? fmtDur(v.duration) : '—'),
            h('td', { 'data-l': '상태' }, statusCell(v)),
            h('td', { 'data-l': '만든 시각', class: 'mono small muted' }, fmtDate(v.created_at)),
            h('td', { 'data-l': '관리' }, actions(v)))))) :
          h('div', { class: 'empty' }, h('b', {}, videos.length ? '조건에 맞는 영상이 없습니다.' : '아직 만든 영상이 없습니다.'),
            videos.length ? '검색어를 바꾸거나 언어를 「모든 언어」로 바꿔 보세요.' : h('span', {}, '「영상 만들기」에서 스크립트와 아바타를 고르고 한 번 누르면 됩니다. ', h('a', { href: '#/create' }, '영상 만들기로'))),
        pages > 1 ? h('div', { class: 'pager' },
          h('button', { class: 'btn sm', disabled: S.page === 0, onclick: () => { S.page--; draw(); } }, '이전'),
          h('span', {}, `${S.page + 1} / ${pages}`),
          h('button', { class: 'btn sm', disabled: S.page >= pages - 1, onclick: () => { S.page++; draw(); } }, '다음')) : null));
    }
    await load();
    // 만드는 중인 영상이 있으면 몇 초마다 새로 읽기
    App.timers.push(setInterval(() => {
      if (videos.some((v) => ['queued', 'avatar', 'timing', 'compose'].includes(v.status))) load();
      else draw();
    }, 4000));
  },
};

function playModal(v) {
  modal({ title: v.title, size: v.aspect === '9:16' ? 'mid' : 'wide', body: h('div', { class: 'video-modal' },
    h('video', { src: `/api/videos/${v.id}/file`, controls: true, autoplay: true, playsinline: true })) });
}

async function shareModal(v, reload) {
  const body = h('div', { class: 'stack' });
  const m = modal({ title: `${v.title} · 공유 링크`, size: 'mid', body });
  async function draw(url, enabled) {
    const inp = h('input', { class: 'input mono', readonly: true, value: url || '', onclick: (e) => e.target.select() });
    const local = url && /\/\/(127\.0\.0\.1|localhost)/.test(url);
    put(body, 
      h('p', { style: { margin: 0 } }, '로그인 없이 열리는 시청 링크입니다. 받은 사람은 이 영상만 볼 수 있고, 링크는 끄기 전까지 계속 열립니다.'),
      enabled ? h('div', { class: 'stack' },
        h('div', { class: 'row', style: { flexWrap: 'nowrap' } }, inp, h('button', { class: 'btn primary', onclick: async () => {
          if (await copyText(url)) toast('복사했습니다. 문자나 메신저에 붙여 넣으세요.'); else { inp.select(); toast('자동 복사가 막혔습니다. 선택된 주소를 Ctrl+C 로 복사해 주세요.'); }
        } }, '링크 복사')),
        local ? h('div', { class: 'notice warn' }, '지금 주소는 이 PC 에서만 열립니다. 환자 휴대폰에서 열리게 하려면 README 의 「환자에게 링크 보내기」를 따라 공개 주소를 만든 뒤, 설정 > 공유 링크 주소에 넣어 주세요.') : null,
        !v.reviewed ? h('div', { class: 'notice warn' }, '이 영상은 검수 전 기계번역 원고로 만들었습니다. 환자에게 보내기 전에 검수하세요.') : null,
        h('div', { class: 'notice' }, '이 주소를 가진 사람은 누구나 영상을 볼 수 있습니다. 보낼 번호를 한 번 더 확인해 주세요.'),
        h('div', { class: 'row' },
          h('a', { class: 'btn', href: url, target: '_blank' }, '환자 화면 열어 보기'),
          isOperator() ? h('a', { class: 'btn ghost', href: '#/share', onclick: () => m.close() }, '안내문구 설정 열기') : null,
          h('span', { class: 'grow' }),
          h('button', { class: 'btn danger', onclick: async () => {
            if (!await confirmBox({ title: '링크 끄기', message: '끄면 이 링크를 받은 사람은 더 이상 영상을 볼 수 없습니다. 다시 켜면 같은 주소가 다시 열립니다.', okLabel: '링크 끄기', danger: true })) return;
            try { await api('POST', `/api/videos/${v.id}/share`, { enabled: false }); toast('링크를 껐습니다.'); draw(null, false); reload(); } catch (e) { fail(e); }
          } }, '링크 끄기'))) :
        h('div', { class: 'row' }, h('button', { class: 'btn primary', onclick: async () => {
          if (!v.reviewed && !await confirmBox({ title: '검수 전 원고', message: '이 영상은 검수 전 기계번역 원고로 만들었습니다. 환자에게 보내기 전에 검수하세요.\n그래도 링크를 만들까요?', okLabel: '링크 만들기', danger: true })) return;
          try { const r = await api('POST', `/api/videos/${v.id}/share`, { enabled: true }); draw(r.url, true); reload(); } catch (e) { fail(e); }
        } }, '공유 링크 만들기')));
  }
  draw(v.share_url, v.share_enabled);
}

function remakeModal(v, reload) {
  const steps = v.steps.map((s) => ({ ...s }));
  const box = h('div', { class: 'stack' },
    h('div', { class: 'notice warn' }, '같은 아바타·음성·화면·자막 설정으로 새 영상을 처음부터 만듭니다. ', v.demo ? '(연습 영상이라 비용은 없습니다)' : 'HeyGen 비용이 전체 길이만큼 다시 듭니다.', ' 원래 영상은 그대로 남습니다.'),
    steps.map((s, i) => {
      const ta = h('textarea', { class: 'input', rows: 3 }); ta.value = s.body;
      ta.addEventListener('input', () => { s.body = ta.value; });
      return h('div', {}, h('label', { class: 'lbl', style: { color: stepColor(i) } }, `${i + 1}단계 ${s.title || ''}`), ta);
    }));
  const m = modal({ title: `${v.title} · 대사 고쳐 다시 만들기`, size: 'mid', body: box,
    foot: [h('button', { class: 'btn', onclick: () => m.close() }, '취소'),
      h('button', { class: 'btn primary', onclick: async () => {
        try { await api('POST', `/api/videos/${v.id}/remake`, { steps }); m.close(); toast('새 영상을 대기열에 넣었습니다.'); reload(); } catch (e) { fail(e); }
      } }, '다시 만들기')] });
}
