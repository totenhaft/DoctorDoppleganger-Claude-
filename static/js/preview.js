/* 자막 표시 설정 편집기 + 실제 영상과 같은 틀의 미리보기 */
'use strict';

/* ---------- 미리보기 ----------
   서버(compose.py)와 같은 1920×1080(세로는 1080×1920) 좌표로 그린 뒤 화면 크기에 맞춰 축소합니다. */
const _loadedFonts = new Set();
function ensureFont(file) {
  if (!file || file === 'default' || _loadedFonts.has(file)) return;
  _loadedFonts.add(file);
  const f = new FontFace('dd-' + file.replace(/\W/g, '_'), `url(/api/fonts/${encodeURIComponent(file)})`);
  f.load().then((ff) => document.fonts.add(ff)).catch(() => {});
}
function fontFamily(st) {
  if (st.font && st.font !== 'default') { ensureFont(st.font); return `"dd-${st.font.replace(/\W/g, '_')}", "Pretendard Variable", "Malgun Gothic", sans-serif`; }
  return '"Pretendard Variable", Pretendard, "Malgun Gothic", sans-serif';
}
function hexA(hex, op) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
  const v = m ? m[1] : '000000';
  return `rgba(${parseInt(v.slice(0, 2), 16)},${parseInt(v.slice(2, 4), 16)},${parseInt(v.slice(4, 6), 16)},${(op ?? 100) / 100})`;
}
function sampleCaption(text, st, portrait) {
  const mx = st.caption_mode === 'manual' ? Math.min(+st.max_chars || 25, portrait ? 26 : 99) : (portrait ? 16 : 28);
  if (!text) return '말할 내용이 여기에 자막으로 나옵니다.';
  if (text.length <= mx) return text;
  let cur = '';
  for (const w of text.split(' ')) {
    const c = (cur + ' ' + w).trim();
    if (c.length > mx && cur) break;
    cur = c;
  }
  return cur || text.slice(0, mx);
}

function renderPreview(o) {
  const portrait = o.aspect === 'portrait';
  const W = portrait ? 1080 : 1920, H = portrait ? 1920 : 1080;
  const st = o.style;
  const outer = h('div', { class: 'pv ' + (portrait ? 'portrait' : 'landscape') });
  if (o.image) outer.style.backgroundImage = `url("${o.image}")`;
  const inner = h('div', { style: { left: 0, top: 0, width: W + 'px', height: H + 'px', transformOrigin: '0 0' } });
  outer.append(inner);
  const fit = () => { const k = outer.clientWidth / W; if (k > 0) inner.style.transform = `scale(${k})`; };
  new ResizeObserver(fit).observe(outer);
  requestAnimationFrame(fit);

  const ff = fontFamily(st);
  const top = 40 + (+st.badge_offset || 0) / 100 * H;
  const place = (el, pos, y) => {
    el.style.top = y + 'px';
    if (pos === 'left') el.style.left = '40px';
    else if (pos === 'right') el.style.right = '40px';
    else { el.style.left = '50%'; el.style.transform = 'translateX(-50%)'; }
    inner.append(el);
  };
  const pillCss = { position: 'absolute', display: 'inline-flex', alignItems: 'center', gap: '12px', padding: '12px 22px', borderRadius: '999px', fontSize: '30px', lineHeight: '1.45', whiteSpace: 'nowrap', fontFamily: ff };
  const steps = o.steps && o.steps.length ? o.steps : [{ title: '단계 제목', body: '' }];
  const si = Math.min(o.stepIndex || 0, steps.length - 1);
  const showTitle = st.show_title && (o.orgName || o.title);
  const stacked = showTitle && st.show_step_title && (st.title_pos === st.step_pos || portrait);
  if (showTitle) {
    const t = h('div', { style: { ...pillCss, background: 'rgba(15,23,42,.75)', color: '#fff', maxWidth: (portrait ? 0.9 : 0.6) * W + 'px', overflow: 'hidden' } },
      h('span', { style: { width: '14px', height: '14px', borderRadius: '50%', background: '#60A5FA', flex: 'none' } }),
      o.orgName ? h('b', { style: { color: '#BAD6FF' } }, o.orgName) : null,
      o.title ? h('span', { style: { overflow: 'hidden', textOverflow: 'ellipsis' } }, o.title) : null);
    place(t, st.title_pos, top);
  }
  if (st.show_step_title) {
    const s = steps[si];
    const b = h('div', { style: { ...pillCss, background: stepColor(si), color: '#fff', fontWeight: 700 } },
      `${si + 1}단계` + (s.title ? ` · ${s.title}` : ''));
    place(b, stacked ? st.title_pos : st.step_pos, stacked ? top + 67 + 14 : top);
  }
  const hasLogo = st.show_logo && o.logoUrl;
  if (hasLogo) {
    const lg = h('img', { src: o.logoUrl, style: { position: 'absolute', bottom: '40px', height: '56px', maxWidth: 0.3 * W + 'px', objectFit: 'contain' } });
    if (st.logo_pos === 'left') lg.style.left = '40px'; else lg.style.right = '40px';
    inner.append(lg);
  }
  const bottom = (hasLogo ? 110 : 70) + (+st.caption_offset || 0) / 100 * H;
  const firstSentence = splitSentences(steps[si].body)[0] || '';
  if (st.speech_caption !== false) {
    const sw = +st.stroke_width || 0;
    let shadow = 'none';
    if (st.shadow) {
      const a = (+st.shadow_angle || 0) * Math.PI / 180, d = +st.shadow_distance || 0;
      shadow = `${(Math.cos(a) * d).toFixed(1)}px ${(Math.sin(a) * d).toFixed(1)}px ${+st.shadow_blur || 0}px ${hexA(st.shadow_color, st.shadow_opacity)}`;
    }
    const cap = h('div', { style: {
      position: 'absolute', bottom: bottom + 'px', maxWidth: 0.86 * W + 'px', fontFamily: ff,
      fontSize: (+st.font_size || 54) + 'px', fontWeight: st.font_weight || 700, lineHeight: st.line_height || 1.25,
      color: st.color, opacity: (st.opacity ?? 100) / 100, textAlign: st.caption_align || 'center',
      WebkitTextStroke: sw ? `${sw * 2}px ${st.stroke_color}` : '0', paintOrder: 'stroke fill', textShadow: shadow,
      background: st.box ? hexA(st.box_color, st.box_opacity) : 'transparent', padding: st.box ? '14px 28px' : '8px 12px',
      borderRadius: '14px', wordBreak: 'keep-all',
    } }, sampleCaption(firstSentence, st, portrait));
    if (st.caption_align === 'left') cap.style.left = '28px';
    else if (st.caption_align === 'right') cap.style.right = '28px';
    else { cap.style.left = '50%'; cap.style.transform = 'translateX(-50%)'; cap.style.width = 'max-content'; }
    inner.append(cap);
  } else if (st.step_caption) {
    const box = h('div', { style: {
      position: 'absolute', bottom: bottom + 'px', maxWidth: 0.86 * W + 'px', background: 'rgba(255,255,255,.93)', color: '#111827',
      borderRadius: '16px', padding: '18px 30px 18px 40px', borderLeft: `10px solid ${stepColor(si)}`, fontFamily: ff,
      fontSize: (+st.font_size || 54) * 0.9 + 'px', fontWeight: 700, lineHeight: 1.2, wordBreak: 'keep-all',
    } }, firstSentence || '단계 자막');
    if (st.caption_align === 'left') box.style.left = '40px'; else if (st.caption_align === 'right') box.style.right = '40px';
    else { box.style.left = '50%'; box.style.transform = 'translateX(-50%)'; box.style.width = 'max-content'; }
    inner.append(box);
  }
  return outer;
}

function stepLegend(steps, current, onPick) {
  const list = steps && steps.length ? steps : [];
  return h('div', {},
    h('div', { class: 'pv-steps' }, list.map((s, i) => h('button', { class: i === current ? 'on' : '', style: { background: stepColor(i) }, title: `${i + 1}단계 미리보기`, onclick: () => onPick(i) }))),
    h('div', { class: 'pv-legend' }, list.map((s, i) => h('span', { style: { '--c': stepColor(i) } }, `${i + 1}단계 ${s.title || ''}`))));
}

/* ---------- 자막 표시 설정 편집기 ----------
   styleEditor({ style, base, onChange, fonts, hasLogo }) → { el, get() } */
const STYLE_LABELS = {
  show_title: '전체제목 표시', show_step_title: '단계제목 표시', speech_caption: '말 자막', step_caption: '단계 자막',
  caption_mode: '하단 자막 표시방법', min_chars: '최소 글자', max_chars: '최대 글자', caption_align: '말 자막 정렬',
  title_pos: '전체제목 위치', step_pos: '단계제목 위치', show_logo: '병원 로고 표시', logo_pos: '로고 위치',
  caption_offset: '자막 세로 위치', badge_offset: '상단 세로 위치', font: '글꼴', font_size: '글자 크기',
  font_weight: '굵기', line_height: '행간', color: '글자색', opacity: '불투명도', stroke_width: '외곽선 굵기',
  stroke_color: '외곽선 색', shadow: '그림자', shadow_color: '그림자 색', shadow_opacity: '그림자 불투명도',
  shadow_angle: '그림자 각도', shadow_distance: '그림자 거리', shadow_blur: '그림자 흐림', box: '자막 박스',
  box_color: '박스 색', box_opacity: '박스 불투명도',
};

function styleEditor({ style, base, onChange, fonts = [], hasLogo = true, baseLabel = '병원 기본값' }) {
  const st = { ...style };
  let tab = 'show';
  const el = h('div', {});
  const emit = () => { onChange && onChange({ ...st }); foot(); };
  const set = (k, v, rerender = true) => { st[k] = v; emit(); if (rerender) draw(); };

  const toggle = (k, title, desc, disabled) => {
    const inp = h('input', { type: 'checkbox', checked: !!st[k], disabled, onchange: () => set(k, inp.checked) });
    return h('div', { class: 'toggle-row' }, h('div', {}, h('div', { class: 't' }, title), desc ? h('div', { class: 'd' }, desc) : null),
      h('label', { class: 'switch' }, inp, h('span')));
  };
  const seg = (k, opts) => h('div', { class: 'seg' }, opts.map(([v, label]) =>
    h('button', { type: 'button', class: String(st[k]) === String(v) ? 'on' : '', onclick: () => set(k, v) }, label)));
  const numStep = (k, step, min, max, suffix = '') => {
    const inp = h('input', { type: 'number', value: st[k], step, min, max, oninput: () => { const v = parseFloat(inp.value); if (!isNaN(v)) set(k, v, false); } });
    const bump = (d) => { const v = Math.max(min, Math.min(max, Math.round(((+st[k] || 0) + d) * 100) / 100)); inp.value = v; set(k, v, false); };
    return h('span', { class: 'row' }, h('span', { class: 'num-step' }, h('button', { type: 'button', onclick: () => bump(-step), 'aria-label': '줄이기' }, '−'), inp,
      h('button', { type: 'button', onclick: () => bump(step), 'aria-label': '키우기' }, '+')), suffix ? h('span', { class: 'muted small' }, suffix) : null);
  };
  const color = (k, presets) => {
    const hex = h('input', { class: 'input hex', value: st[k], maxlength: 7, oninput: () => { if (/^#[0-9a-f]{6}$/i.test(hex.value)) set(k, hex.value.toUpperCase(), false); } });
    const pick = h('input', { type: 'color', value: st[k], style: { width: '36px', height: '34px', border: 0, background: 'none', padding: 0 }, oninput: () => { hex.value = pick.value.toUpperCase(); set(k, hex.value, false); } });
    return h('div', { class: 'swatches' }, presets.map(([v, label]) =>
      h('button', { type: 'button', class: 'sw' + (st[k].toUpperCase() === v ? ' on' : ''), onclick: () => set(k, v) }, h('i', { style: { background: v } }), label)), pick, hex);
  };
  const opt = (title, desc, ...kids) => h('div', { class: 'opt' }, h('div', { class: 't' }, title), desc ? h('div', { class: 'd' }, desc) : null, ...kids);
  // 같은 자리를 고르면 두 제목이 자리를 바꿈
  const posSeg = (k, other) => h('div', { class: 'seg' }, [['left', '왼쪽'], ['center', '가운데'], ['right', '오른쪽']].map(([v, label]) =>
    h('button', { type: 'button', class: st[k] === v ? 'on' : '', onclick: () => { if (st[other] === v) st[other] = st[k]; set(k, v); } }, label)));

  const footEl = h('div', { class: 'style-foot' });
  function foot() {
    if (!base) { put(footEl, ); return; }
    const changed = Object.keys(STYLE_LABELS).filter((k) => String(st[k]) !== String(base[k]));
    put(footEl, 
      h('span', {}, changed.length ? `${changed.length}개 항목 변경됨 · ${changed.slice(0, 4).map((k) => STYLE_LABELS[k]).join(', ')}${changed.length > 4 ? ' 등' : ''}` : `${baseLabel} 그대로`),
      changed.length ? h('button', { type: 'button', class: 'btn sm', onclick: () => { Object.assign(st, base); emit(); draw(); } }, '기본값으로') : null);
  }

  function body() {
    if (tab === 'show') {
      return [
        toggle('show_step_title', '단계제목 표시', '단계 배지를 영상 위쪽에 표시합니다.'),
        toggle('show_title', '전체제목 표시', '병원명 · 영상 제목을 위쪽에 표시합니다.'),
        toggle('speech_caption', '말 자막 (하단 자막)', '아바타가 말하는 문장을 아래에 자막으로 보여 줍니다.'),
        !st.speech_caption ? toggle('step_caption', '단계 자막', '말 자막을 끈 경우, 단계마다 첫 문장을 아래 박스로 고정해 보여 줍니다.') : null,
        st.speech_caption ? opt('하단 자막 표시방법', '기본은 말과 맞춰 나눕니다(추천). 수동설정은 한 화면 글자 수를 정합니다.',
          seg('caption_mode', [['auto', '기본'], ['manual', `수동설정 (${st.min_chars}~${st.max_chars}자)`]]),
          st.caption_mode === 'manual' ? h('div', { class: 'row', style: { marginTop: '10px' } },
            h('span', { class: 'small muted' }, '최소'), numStep('min_chars', 1, 5, 30, '자'), h('span', { class: 'small muted' }, '최대'), numStep('max_chars', 1, 5, 30, '자')) : null,
          st.caption_mode === 'manual' ? h('div', { class: 'hint' }, '세로 영상은 한 화면 최대 26자로 맞춥니다. 길면 2줄로 나옵니다.') : null) : null,
        opt('말 자막 정렬', null, seg('caption_align', [['left', '왼쪽'], ['center', '가운데'], ['right', '오른쪽']])),
        opt('상단 배치', '같은 자리를 고르면 두 제목이 자리를 바꿉니다. 세로 영상은 위아래로 쌓입니다.',
          h('div', { class: 'row' }, h('span', { class: 'small muted', style: { width: '78px' } }, '전체제목'), posSeg('title_pos', 'step_pos')),
          h('div', { class: 'row', style: { marginTop: '8px' } }, h('span', { class: 'small muted', style: { width: '78px' } }, '단계제목'), posSeg('step_pos', 'title_pos'))),
        toggle('show_logo', '병원 로고 표시', hasLogo ? '영상 아래쪽에 로고를 넣습니다.' : '설정에서 로고를 올리면 켤 수 있습니다.', !hasLogo),
        st.show_logo && hasLogo ? opt('로고 위치', null, seg('logo_pos', [['left', '왼쪽 아래'], ['right', '오른쪽 아래']])) : null,
        opt('세부 위치 조절', '화면 높이에 대한 % 입니다.',
          h('div', { class: 'row' }, h('span', { class: 'small muted', style: { width: '120px' } }, '하단 자막 (위로 +)'), numStep('caption_offset', 1, -20, 60, '%')),
          h('div', { class: 'row', style: { marginTop: '8px' } }, h('span', { class: 'small muted', style: { width: '120px' } }, '상단 제목 (아래로 +)'), numStep('badge_offset', 1, -5, 60, '%'))),
      ];
    }
    if (tab === 'font') {
      return [
        opt('글꼴', '병원 글꼴은 설정 > 글꼴 업로드에서 올립니다. 미리보기 글꼴은 실제 영상과 조금 다를 수 있습니다.',
          h('select', { class: 'input', onchange: (e) => set('font', e.target.value) },
            h('option', { value: 'default', selected: st.font === 'default' }, '기본 (맑은 고딕)'),
            fonts.map((f) => h('option', { value: f.file, selected: st.font === f.file }, f.name)))),
        opt('글자 크기', '1080px 화면 기준 픽셀입니다.',
          seg('font_size', [[44, '작게'], [54, '보통'], [64, '크게'], [76, '아주 크게']]),
          h('div', { style: { marginTop: '8px' } }, numStep('font_size', 2, 20, 120, 'px'))),
        opt('굵기', st.font === 'default' ? '기본 글꼴은 보통·굵게 두 가지입니다.' : '올린 글꼴은 그 파일의 굵기로 나옵니다.',
          seg('font_weight', [[400, '보통'], [700, '굵게'], [800, '아주 굵게']])),
        opt('행간', '자막이 2줄일 때 줄 사이 간격입니다.', numStep('line_height', 0.05, 1, 2)),
      ];
    }
    if (tab === 'color') {
      return [
        opt('글자색', null, color('color', [['#FFFFFF', '흰색'], ['#FFE14D', '노랑'], ['#111111', '검정']])),
        opt('불투명도', '박스·외곽선까지 함께 흐려집니다.', seg('opacity', [[100, '선명하게'], [85, '조금 흐리게'], [70, '흐리게']]),
          h('div', { style: { marginTop: '8px' } }, numStep('opacity', 5, 10, 100, '%'))),
        opt('외곽선', '밝은 배경에서도 글씨가 잘 보이게 둘레를 그립니다.', seg('stroke_width', [[0, '없음'], [2, '얇게'], [3, '보통'], [5, '두껍게']]),
          h('div', { style: { margin: '8px 0' } }, numStep('stroke_width', 0.5, 0, 12, 'px')),
          color('stroke_color', [['#111111', '검정'], ['#1E2A44', '남색'], ['#FFFFFF', '흰색']])),
        toggle('shadow', '그림자', '글자 아래에 옅은 그림자를 넣습니다.'),
        st.shadow ? opt('그림자 세부', null,
          h('div', { class: 'two' },
            h('div', {}, h('div', { class: 'small muted' }, '각도(°)'), numStep('shadow_angle', 15, 0, 360)),
            h('div', {}, h('div', { class: 'small muted' }, '거리(px)'), numStep('shadow_distance', 1, 0, 30)),
            h('div', {}, h('div', { class: 'small muted' }, '흐림(px)'), numStep('shadow_blur', 1, 0, 30)),
            h('div', {}, h('div', { class: 'small muted' }, '불투명도(%)'), numStep('shadow_opacity', 5, 0, 100))),
          h('div', { style: { marginTop: '8px' } }, color('shadow_color', [['#000000', '검정'], ['#1E2A44', '남색']]))) : null,
      ];
    }
    return [
      toggle('box', '자막 박스 사용', '글자 뒤에 색 박스를 깔아 영상 배경과 상관없이 잘 읽히게 합니다.'),
      st.box ? opt('박스 색', null, color('box_color', [['#000000', '검정'], ['#1E2A44', '남색'], ['#FFFFFF', '흰색']])) : null,
      st.box ? opt('박스 불투명도', null, seg('box_opacity', [[40, '옅게'], [55, '보통'], [75, '진하게']]),
        h('div', { style: { marginTop: '8px' } }, numStep('box_opacity', 5, 0, 100, '%'))) : null,
    ];
  }
  function draw() {
    put(el, 
      h('div', { class: 'seg full style-tabs' }, [['show', '표시 항목'], ['font', '글자'], ['color', '색·외곽선'], ['box', '자막 박스']].map(([v, l]) =>
        h('button', { type: 'button', class: tab === v ? 'on' : '', onclick: () => { tab = v; draw(); } }, l))),
      h('div', {}, body()), footEl);
    foot();
  }
  draw();
  return { el, get: () => ({ ...st }) };
}
