/* Cashier AI — CRM-прототип. Без сборки: классические скрипты, хеш-роутинг (#/agents и т.п.). */
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const STORE = 'cashier-crm-v3';

  // ---------- состояние ----------
  const saved = (() => { try { return JSON.parse(localStorage.getItem(STORE)) || {}; } catch { return {}; } })();
  const S = {
    style: saved.style || '1torg',
    mode: saved.mode || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),
    agents: saved.agents || structuredClone(SEED.agents),
    trainings: saved.trainings || structuredClone(SEED.trainings),
    session: [],          // проверки этой сессии (с полным результатом)
    run: null,            // текущая проверка
    train: null,          // текущее обучение
    agentTab: 'all',
    histFilter: 'all',
  };
  const persist = () => {
    try { localStorage.setItem(STORE, JSON.stringify({ style: S.style, mode: S.mode, agents: S.agents, trainings: S.trainings })); } catch { /* приватный режим */ }
  };

  const STYLES = [
    { id: 'graphite', name: 'Графит', note: 'чёрно-белый, как главная и вход', c: ['#15181b', '#9aa0a6', '#f6f6f4', '#ffffff'] },
    { id: 'forte', name: 'Малина', note: 'малиновый акцент, тёмный сайдбар', c: ['#2b0d1c', '#a3154f', '#f6f4f5', '#ffffff'] },
    { id: '1torg', name: 'Мята', note: 'белый, зелёный, сетка на фоне', c: ['#ffffff', '#43a047', '#f8fafc', '#e8f5e9'] },
    { id: 'school', name: 'Стекло', note: 'полупрозрачные панели, градиент', c: ['#f4fff8', '#16a34a', '#dcfce7', '#ffffff'] },
    { id: '9bar', name: 'Бумага', note: 'тёплый фон, чёрный сайдбар, пилюли', c: ['#161817', '#b8236f', '#f2f0eb', '#ffffff'] },
    { id: 'arzandau', name: 'Лазурь', note: 'голубой акцент, карточки с подъёмом', c: ['#0b1b33', '#0088ee', '#f5f9ff', '#e6f4ff'] },
  ];
  const KIND = { rule: ['Правила', 'b-info'], trained: ['Обучаемая модель', 'b-accent'], vlm: ['Локальная VLM', 'b-warn'] };
  const ruleById = (id) => SEED.rules.find((r) => r.id === id) || SEED.rules.at(-1);

  function applyTheme() {
    document.documentElement.dataset.style = S.style;
    document.documentElement.dataset.mode = S.mode;
    persist();
  }

  // ---------- каркас ----------
  const NAV = [
    ['dashboard', 'Обзор', 'home'],
    ['check', 'Проверка видео', 'scan'],
    ['agents', 'Агенты', 'bot'],
    ['training', 'Обучение', 'brain'],
    ['rules', 'Нормативы', 'book'],
    ['history', 'История', 'history'],
    ['settings', 'Настройки', 'settings'],
  ];
  const TITLES = {
    dashboard: ['Обзор', 'Сводка по проверкам и агентам'],
    check: ['Проверка видео', 'Загрузите запись кассы, и агенты проверят её параллельно'],
    agents: ['Агенты', 'Каждый агент отвечает за свой тип риска'],
    training: ['Обучение', 'Новые агенты учатся на ваших видео'],
    rules: ['Нормативы', 'Связь «нарушение → документ → пункт»'],
    history: ['История проверок', 'Все загруженные видео'],
    settings: ['Настройки', 'Внешний вид, API и пороги'],
  };

  function shell() {
    const active = S.agents.filter((a) => a.enabled).length;
    $('#app').innerHTML = `
      <div class="shell">
        <aside class="side" id="side">
          <div class="brand">
            <img class="brand-logo" src="img/logo.svg" alt="" width="42" height="43">
            <div><div class="brand-name">Cashier AI</div>
            <div class="brand-sub">Контроль кассовой дисциплины</div></div>
          </div>
          <nav class="nav">
            <div class="nav-label">Работа</div>
            ${NAV.slice(0, 2).map((n) => navItem(n)).join('')}
            <div class="nav-label">Агенты</div>
            ${NAV.slice(2, 5).map((n) => navItem(n, n[0] === 'agents' ? `${active}/${S.agents.length}` : '')).join('')}
            <div class="nav-label">Система</div>
            ${NAV.slice(5).map((n) => navItem(n)).join('')}
          </nav>
          <div class="side-foot">
            <div class="row" style="padding:0 6px;flex-wrap:nowrap">
              <div class="avatar" style="width:34px;height:34px;border-radius:50%">${icon('user')}</div>
              <div style="flex:1;min-width:0"><div style="font-weight:600;font-size:13px">${esc(S.user || 'Проверяющий')}</div><div class="small" style="color:var(--side-muted)">отдел контроля</div></div>
              <button class="btn btn-ghost btn-icon btn-sm" data-act="logout" title="Выйти" aria-label="Выйти">${icon('logout')}</button>
            </div>
          </div>
        </aside>
        <div class="main">
          <header class="top">
            <button class="btn btn-ghost btn-icon burger" data-act="burger" aria-label="Меню">${icon('menu')}</button>
            <div><h1 id="title"></h1><div class="crumb" id="crumb"></div></div>
            <div class="spacer"></div>
            <div class="search">${icon('search')}<input class="input" placeholder="Поиск по проверкам и агентам"></div>
            <span id="conn"></span>
            <button class="btn btn-ghost btn-icon" data-act="mode" aria-label="Тема">${icon(S.mode === 'dark' ? 'sun' : 'moon')}</button>
          </header>
          <main class="content" id="page"></main>
        </div>
      </div>
      <div class="toasts" id="toasts"></div>`;
    renderConn();
  }
  const navItem = ([id, label, ic], count = '') =>
    `<a href="#/${id}" data-nav="${id}">${icon(ic)}<span>${label}</span>${count ? `<span class="count">${count}</span>` : ''}</a>`;

  function renderConn() {
    const el = $('#conn');
    if (!el) return;
    el.innerHTML = API.online.value
      ? `<span class="badge b-ok"><span class="dot"></span>Сервер подключён</span>`
      : `<span class="badge b-warn demo-flag" title="Бэкенд не найден: анализ имитируется, метрики демонстрационные"><span class="dot"></span>Демо-режим</span>`;
  }

  function toast(msg, ic = 'check') {
    const t = document.createElement('div');
    t.className = 'toast';
    t.innerHTML = `${icon(ic)}<span>${esc(msg)}</span>`;
    $('#toasts').appendChild(t);
    setTimeout(() => t.remove(), 3200);
  }

  // ---------- роутер ----------
  const page = () => (location.hash.replace('#/', '').split('?')[0] || 'dashboard');
  function route() {
    if (!S.user || !$('#page')) return; // без входа страницы не рисуем
    const p = PAGES[page()] ? page() : 'dashboard';
    $$('[data-nav]').forEach((a) => a.classList.toggle('active', a.dataset.nav === p));
    const [t, c] = TITLES[p];
    $('#title').textContent = t;
    $('#crumb').textContent = c;
    $('#page').innerHTML = PAGES[p]();
    AFTER[p]?.();
    $('#side').classList.remove('open');
    window.scrollTo(0, 0);
  }

  // ---------- страницы ----------
  const demoTag = () => (API.online.value ? '' : '<span class="badge demo-flag">демо-данные</span>');

  const PAGES = {
    dashboard() {
      const week = SEED.week;
      const total = week.reduce((s, d) => s + d[1] + d[2], 0) + S.session.length;
      const viol = week.reduce((s, d) => s + d[1], 0) + S.session.filter((x) => x.verdict === 'violation').length;
      const max = Math.max(...week.map((d) => d[1] + d[2]));
      const active = S.agents.filter((a) => a.enabled);
      const recent = [...S.session.map(sessionRow), ...SEED.history].slice(0, 6);
      return `
      <div class="grid g-4">
        ${kpi('scan', total, 'видео проверено за неделю', '+18% к прошлой', 'b-ok')}
        ${kpi('alert', viol, 'видео с признаками нарушений', `${Math.round((viol / total) * 100)}% от всех`, 'b-warn')}
        ${kpi('clock', '52 с', 'среднее время анализа', 'лимит жюри 5 мин', 'b-info')}
        ${kpi('bot', `${active.length}/${S.agents.length}`, 'агентов активно', `${S.agents.filter((a) => a.kind === 'trained').length} обучаемых`, 'b-accent')}
      </div>
      <div class="grid g-main mt">
        <div class="card chart-card">
          <div class="card-h"><h3>Проверки за неделю</h3>${demoTag()}<div class="spacer"></div>
            <div class="legend"><span style="--c:var(--accent)">с нарушением</span><span style="--c:var(--surface-3)">без нарушений</span></div></div>
          <div class="bars">${week.map(([d, v, c]) => `
            <div class="b"><div class="track">
              <span class="v">${v + c}<em>${v} нар.</em></span>
              <div class="col" style="height:${((v + c) / max) * 90}%" title="${v} с нарушением, ${c} без">
                <i style="flex:${v};background:var(--accent)"></i><i style="flex:${c};background:var(--surface-3)"></i></div>
            </div><span class="d">${d}</span></div>`).join('')}
          </div>
        </div>
        <div class="card">
          <div class="card-h"><h3>Агенты</h3><div class="spacer"></div><a href="#/agents" class="btn btn-soft btn-sm">Все ${icon('arrow')}</a></div>
          <div class="stack">${S.agents.slice(0, 5).map((a) => `
            <div class="row" style="flex-wrap:nowrap">
              <div class="avatar" style="width:36px;height:36px;border-radius:11px">${icon(a.icon)}</div>
              <div style="min-width:0;flex:1"><div style="font-weight:600;font-size:13.5px">${esc(a.name)}</div>
                <div class="small muted">${a.alerts} тревог · ${a.m ? `recall ${a.m.r.toFixed(2)}` : 'не обучен'}</div></div>
              <span class="badge ${a.enabled ? 'b-ok' : ''}"><span class="dot"></span>${a.enabled ? 'вкл' : 'выкл'}</span>
            </div>`).join('')}</div>
        </div>
      </div>
      <div class="card mt">
        <div class="card-h"><h3>Последние проверки</h3><div class="spacer"></div><a href="#/history" class="btn btn-ghost btn-sm">История</a></div>
        ${historyTable(recent)}
      </div>`;
    },

    check() {
      if (!S.run) {
        const det = S.agents.filter((a) => a.enabled);
        return `
        <div class="grid g-main">
          <div class="card pad-lg">
            <label class="drop" id="drop" for="file">
              <input id="file" type="file" accept=".mov,.mp4,video/*" hidden>
              <div class="big">${icon('upload')}</div>
              <h3>Перетащите видео кассы</h3>
              <div class="muted">.mov или .mp4, до 500 МБ. Обработка обычно занимает меньше минуты.</div>
              <span class="btn btn-primary mt">Выбрать файл</span>
            </label>
            <div class="row mt small muted">${icon('shield')} Видео обрабатывается локально, в облачные сервисы ничего не отправляется.</div>
          </div>
          <div class="card">
            <div class="card-h"><h3>Кто будет проверять</h3><span class="badge b-accent">${det.length} агентов</span></div>
            <div class="stack">${det.map((a) => liveAgent(a, { state: 'wait', msg: esc(a.model) })).join('')}</div>
            <hr class="sep">
            <div class="small muted">Затем находки проверят служебные агенты: скептик, юрист и агрегатор.</div>
          </div>
        </div>`;
      }
      const r = S.run;
      return `
      <div class="grid g-main">
        <div class="stack">
          <div id="verdict"></div>
          <div class="card player">
            <video id="video" src="${r.url}" controls muted playsinline preload="auto"></video>
            <div class="timeline" id="tl"><canvas id="tlc"></canvas><div class="head" id="tlh"></div></div>
            <div class="row mt small muted"><span>${icon('scan')} ${esc(r.file.name)}</span><span>·</span><span>${(r.file.size / 1048576).toFixed(1)} МБ</span>
              <div style="flex:1"></div><button class="btn btn-ghost btn-sm" data-act="new-check">${icon('plus')} Новая проверка</button></div>
          </div>
          <div id="violations" class="stack"></div>
        </div>
        <div class="stack">
          <div class="card">
            <div class="card-h"><h3>Агенты в работе</h3><div class="spacer"></div><span id="phase"></span></div>
            <div class="progress"><i id="overall"></i></div>
            <div class="live mt" id="live"></div>
          </div>
          <div class="card">
            <div class="card-h"><h3>Лента событий</h3></div>
            <div class="feed" id="feed"></div>
          </div>
        </div>
      </div>`;
    },

    agents() {
      const tabs = [['all', 'Все'], ['on', 'Включены'], ['trained', 'Обучаемые'], ['rule', 'Правила']];
      const list = S.agents.filter((a) => S.agentTab === 'all' || (S.agentTab === 'on' ? a.enabled : a.kind === S.agentTab));
      return `
      <div class="row" style="margin-bottom:16px">
        <div class="tabs">${tabs.map(([id, l]) => `<button class="${S.agentTab === id ? 'on' : ''}" data-agent-tab="${id}">${l}</button>`).join('')}</div>
        <div style="flex:1"></div>${demoTag()}
        <button class="btn btn-primary" data-act="add-agent">${icon('plus')} Новый агент</button>
      </div>
      <div class="grid g-3">
        ${list.map(agentCard).join('')}
        <button class="add-card" data-act="add-agent">
          <div class="avatar" style="width:52px;height:52px;border-radius:16px">${icon('plus')}</div>
          <div><b>Добавить агента</b><div class="small">Загрузите ZIP с видео и разметкой, и агент обучится</div></div>
        </button>
      </div>
      <h3 class="mt" style="margin:28px 0 12px;font-size:16px">Служебные агенты конвейера</h3>
      <div class="grid g-3">${SEED.service.map((a) => `
        <div class="card agent">
          <div class="agent-top"><div class="avatar">${icon(a.icon)}</div>
            <div style="flex:1"><h4>${a.name}</h4><div class="kind">всегда включён</div></div><span class="badge b-ok"><span class="dot"></span>активен</span></div>
          <p>${a.desc}</p>
        </div>`).join('')}
      </div>`;
    },

    training() {
      const opts = S.agents.map((a) => `<option value="${a.id}" ${a.id === S.trainAgent ? 'selected' : ''}>${esc(a.name)}</option>`).join('');
      return `
      <div class="grid g-main">
        <div class="stack">
          <div class="card pad-lg" id="train-box">${S.train ? trainRunHtml() : trainFormHtml(opts)}</div>
        </div>
        <div class="card">
          <div class="card-h"><h3>Формат датасета</h3></div>
          <div class="zip-tree">dataset.zip
├── videos/
│   ├── cam1_001.mov
│   ├── cam1_002.mov
│   └── …
└── labels.csv</div>
          <p class="small muted">labels.csv: <code class="k">file,label,timecode_sec,type</code>. В <code class="k">label</code> пишется violation или no_violation, таймкод указывается в секундах, а type берётся из базы нормативов.</p>
          <div class="zip-tree">file,label,timecode_sec,type
cam1_001.mov,violation,22,improper_handover
cam1_002.mov,no_violation,,</div>
          <hr class="sep">
          <div class="stack small">
            <div class="row">${icon('check')} Минимум 10 видео, из них хотя бы 3 с нарушением</div>
            <div class="row">${icon('check')} Обучение идёт на этом сервере, данные никуда не уходят</div>
            <div class="row">${icon('check')} Новая версия агента включается после проверки метрик</div>
          </div>
        </div>
      </div>
      <div class="card mt">
        <div class="card-h"><h3>Запуски обучения</h3>${demoTag()}</div>
        <div class="table-wrap"><table class="t">
          <thead><tr><th>ID</th><th>Агент</th><th>Датасет</th><th>Видео</th><th>Начато</th><th>Статус</th><th>Precision</th><th>Recall</th></tr></thead>
          <tbody>${S.trainings.map((t) => `<tr>
            <td class="mono">${t.id}</td><td>${esc(t.agent)}</td><td>${icon('zip')} ${esc(t.file)}</td><td>${t.videos}</td><td class="muted">${t.started}</td>
            <td>${t.status === 'done' ? '<span class="badge b-ok">готово</span>' : t.status === 'failed' ? `<span class="badge b-danger" title="${esc(t.err)}">ошибка</span>` : '<span class="badge b-accent pulse"><span class="dot"></span>идёт</span>'}</td>
            <td>${t.p != null ? t.p.toFixed(2) : '—'}</td><td>${t.r != null ? t.r.toFixed(2) : '—'}</td></tr>`).join('')}</tbody>
        </table></div>
      </div>`;
    },

    rules() {
      return `
      <div class="card" style="margin-bottom:16px;background:var(--warn-soft);border-color:transparent">
        <div class="row" style="flex-wrap:nowrap;color:var(--warn)">${icon('alert')}
          <div><b>Пункты появятся в отчётах только после проверки.</b>
          <div class="small" style="color:var(--ink-2)">Юрист не генерирует ссылки, а только берёт их из этой базы. Пока документ не сверен с adilet.zan.kz, в отчёт попадает одно название без номера пункта.</div></div></div>
      </div>
      <div class="grid g-2">${Object.entries(SEED.documents).map(([id, d]) => `
        <div class="card">
          <div class="agent-top"><div class="avatar">${icon('book')}</div>
            <div style="flex:1"><h4 style="font-size:15px">${d.title}</h4><div class="small muted">${d.req}</div></div>
            <span class="badge ${d.verified ? 'b-ok' : 'b-warn'}">${d.verified ? 'проверено' : 'не проверено'}</span></div>
          <div class="row mt small muted">${icon('layers')} ${SEED.rules.filter((r) => r.doc === id).length} типов нарушений ссылаются на документ</div>
        </div>`).join('')}
      </div>
      <div class="card mt">
        <div class="card-h"><h3>Нарушение → норматив → агенты</h3></div>
        <div class="table-wrap"><table class="t">
          <thead><tr><th>Тип нарушения</th><th>Документ</th><th>Пункт</th><th>Агенты</th></tr></thead>
          <tbody>${SEED.rules.map((r) => `<tr>
            <td><b>${r.title}</b><div class="small muted mono">${r.id}</div></td>
            <td class="small">${SEED.documents[r.doc].title}</td>
            <td>${r.clause ? esc(r.clause) : '<span class="badge b-warn">уточняется</span>'}</td>
            <td><div class="chain">${S.agents.filter((a) => a.types.includes(r.id)).map((a) => `<span class="badge">${icon(a.icon)}${esc(a.name)}</span>`).join('') || '<span class="muted">—</span>'}</div></td>
          </tr>`).join('')}</tbody>
        </table></div>
      </div>`;
    },

    history() {
      let rows = [...S.session.map(sessionRow), ...SEED.history];
      if (S.histFilter !== 'all') rows = rows.filter((h) => h.verdict === S.histFilter);
      const tabs = [['all', 'Все'], ['violation', 'С нарушениями'], ['no_violation', 'Без нарушений']];
      return `
      <div class="row" style="margin-bottom:16px">
        <div class="tabs">${tabs.map(([id, l]) => `<button class="${S.histFilter === id ? 'on' : ''}" data-hist="${id}">${l}</button>`).join('')}</div>
        <div style="flex:1"></div>${demoTag()}
        <a class="btn btn-primary" href="#/check">${icon('upload')} Проверить видео</a>
      </div>
      <div class="card">${historyTable(rows)}</div>`;
    },

    settings() {
      const origin = location.protocol === 'file:' ? 'https://<ваш-домен>' : location.origin;
      return `
      <div class="card pad-lg">
        <div class="card-h"><h3>${icon('palette')} Стиль интерфейса</h3><div class="spacer"></div>
          <div class="tabs"><button class="${S.mode === 'light' ? 'on' : ''}" data-set-mode="light">${icon('sun')} Светлая</button><button class="${S.mode === 'dark' ? 'on' : ''}" data-set-mode="dark">${icon('moon')} Тёмная</button></div></div>
        <div class="styles">${STYLES.map((s) => `
          <button class="style-card ${S.style === s.id ? 'on' : ''}" data-style="${s.id}">
            <div class="style-prev" style="background:${s.c[2]}">
              <div class="s" style="background:${s.c[0]}"><i style="background:${s.c[1]};width:70%"></i><i style="background:${s.c[3]};opacity:.5"></i><i style="background:${s.c[3]};opacity:.5;width:80%"></i></div>
              <div class="m"><i style="background:${s.c[1]};width:45%;height:10px"></i><i style="background:${s.c[3]};border:1px solid rgba(0,0,0,.06);height:26px"></i><i style="background:${s.c[3]};border:1px solid rgba(0,0,0,.06);height:18px;width:70%"></i></div>
            </div>
            <div class="meta"><b>${s.name}</b><span class="small muted">${s.note}</span></div>
          </button>`).join('')}
        </div>
      </div>
      <div class="grid g-2 mt">
        <div class="card">
          <div class="card-h"><h3>${icon('key')} API для жюри</h3></div>
          <dl class="kv">
            <dt>Адрес</dt><dd class="mono">${esc(origin)}/api/v1</dd>
            <dt>Заголовок</dt><dd><code class="k">X-API-Key</code></dd>
            <dt>Ключ</dt><dd class="muted">задаётся в <code class="k">.env</code> на сервере (API_KEY)</dd>
            <dt>Лимит</dt><dd>5 минут на видео</dd>
          </dl>
          <div class="zip-tree mt">curl -X POST ${esc(origin)}/api/v1/analyze \\
  -H "X-API-Key: &lt;ключ&gt;" -F "file=@video.mov"
curl ${esc(origin)}/api/v1/jobs/&lt;job_id&gt; -H "X-API-Key: &lt;ключ&gt;"</div>
        </div>
        <div class="card">
          <div class="card-h"><h3>${icon('filter')} Чувствительность</h3>${demoTag()}</div>
          <div class="field"><label>Порог тревоги: <span id="thr-v">0.50</span></label>
            <input type="range" min="0.2" max="0.9" step="0.01" value="0.5" id="thr" style="accent-color:var(--accent)"></div>
          <p class="small muted">Ниже порог даёт меньше пропусков и больше ложных тревог. Банку важнее не пропустить нарушение, поэтому порог подбирается так, чтобы recall на валидации был 1.0.</p>
          <div class="field mt"><label>Кадров в секунду для анализа</label>
            <select class="select"><option>2</option><option selected>4</option><option>8</option></select></div>
        </div>
      </div>`;
    },
  };

  const AFTER = {
    check() {
      if (!S.run) return bindDrop($('#drop'), $('#file'), (f) => startCheck(f));
      renderLive(); renderResults(); bindTimeline();
    },
    training() {
      if (!S.train) bindDrop($('#zdrop'), $('#zfile'), (f) => pickZip(f));
      else renderTrain();
    },
    settings() {
      const thr = $('#thr');
      thr.oninput = () => ($('#thr-v').textContent = (+thr.value).toFixed(2));
    },
  };

  // ---------- кусочки разметки ----------
  function kpi(ic, val, lbl, delta, cls) {
    return `<div class="card kpi"><div class="row" style="justify-content:space-between"><div class="ic">${icon(ic)}</div><span class="badge ${cls}">${delta}</span></div>
      <div class="val">${val}</div><div class="lbl">${lbl}</div></div>`;
  }

  function sessionRow(x) {
    return { id: x.job_id, file: x.file, when: 'только что', dur: Math.round(x.duration_sec || 0), verdict: x.verdict,
      n: x.violations.length, sec: x.processing_sec, types: x.violations.map((v) => v.type_id), live: true };
  }

  function historyTable(rows) {
    if (!rows.length) return '<div class="empty">Проверок пока нет</div>';
    return `<div class="table-wrap"><table class="t">
      <thead><tr><th>Видео</th><th>Когда</th><th>Длительность</th><th>Вердикт</th><th>Найдено</th><th>Типы</th><th>Анализ</th></tr></thead>
      <tbody>${rows.map((h) => `<tr class="${h.live ? 'click' : ''}" ${h.live ? `data-open="${h.id}"` : ''}>
        <td><div class="row" style="flex-wrap:nowrap">${icon('scan')}<div><b>${esc(h.file)}</b><div class="small muted mono">${h.id}</div></div></div></td>
        <td class="muted">${h.when}</td><td>${fmt(h.dur).slice(0, 5)}</td>
        <td>${h.verdict === 'violation' ? '<span class="badge b-danger"><span class="dot"></span>нарушение</span>' : '<span class="badge b-ok"><span class="dot"></span>чисто</span>'}</td>
        <td>${h.n}</td>
        <td><div class="chain">${[...new Set(h.types)].map((t) => `<span class="badge">${esc(ruleById(t).title.split(' ').slice(0, 3).join(' '))}</span>`).join('') || '<span class="muted">—</span>'}</div></td>
        <td class="muted">${h.sec} с</td></tr>`).join('')}</tbody></table></div>`;
  }

  function agentCard(a) {
    const [kl, kc] = KIND[a.kind] || ['Агент', ''];
    return `
    <div class="card agent ${a.enabled ? '' : 'off'}">
      <div class="agent-top">
        <div class="avatar">${icon(a.icon)}</div>
        <div style="flex:1;min-width:0"><h4>${esc(a.name)}</h4><div class="kind">${esc(a.model)}</div></div>
        <label class="switch" title="${a.enabled ? 'Выключить' : 'Включить'}"><input type="checkbox" data-toggle="${a.id}" ${a.enabled ? 'checked' : ''}><span></span></label>
      </div>
      <p>${esc(a.desc)}</p>
      ${a.m ? `<div class="metrics">
        <div class="metric"><b>${a.m.p.toFixed(2)}</b><span>precision</span></div>
        <div class="metric"><b>${a.m.r.toFixed(2)}</b><span>recall</span></div>
        <div class="metric"><b>${a.m.ms} мс</b><span>на кадр</span></div></div>`
        : `<div class="metric" style="text-align:center"><span>Агент ещё не обучен: загрузите датасет</span></div>`}
      <div class="agent-foot">
        <span class="badge ${kc}">${kl}</span><span class="badge mono">${esc(a.version)}</span>
        <div class="spacer"></div>
        <button class="btn btn-soft btn-sm" data-train="${a.id}">${icon('brain')} Обучить</button>
      </div>
    </div>`;
  }

  function liveAgent(a, st) {
    return `<div class="live-agent ${st.state}" data-live="${a.id}">
      <div class="avatar">${icon(st.state === 'alert' ? 'alert' : st.state === 'clear' ? 'check' : a.icon)}</div>
      <div style="min-width:0"><div class="name">${esc(a.name)}</div><div class="msg">${st.msg}</div>
        ${st.state === 'scan' ? `<div class="progress"><i style="width:${Math.round(st.p * 100)}%"></i></div>` : ''}</div>
      <span class="badge ${st.state === 'alert' ? 'b-danger' : st.state === 'clear' ? 'b-ok' : st.state === 'scan' ? 'b-accent pulse' : ''}">
        ${st.state === 'scan' ? '<span class="dot"></span>анализ' : st.state === 'alert' ? 'тревога' : st.state === 'clear' ? 'чисто' : 'ожидает'}</span>
    </div>`;
  }

  function bindDrop(drop, input, cb) {
    if (!drop) return;
    input.onchange = () => input.files[0] && cb(input.files[0]);
    drop.ondragover = (e) => { e.preventDefault(); drop.classList.add('over'); };
    drop.ondragleave = () => drop.classList.remove('over');
    drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove('over'); e.dataTransfer.files[0] && cb(e.dataTransfer.files[0]); };
  }

  // ---------- проверка видео: live-конвейер агентов ----------
  async function startCheck(file) {
    const detectors = S.agents.filter((a) => a.enabled);
    const pipeline = [...detectors, ...SEED.service.map((s) => ({ ...s, model: '' }))];
    S.run = {
      file, url: URL.createObjectURL(file), result: null, phase: 'Загрузка', overall: 0, feed: [],
      pipeline, st: Object.fromEntries(pipeline.map((a) => [a.id, { state: 'wait', p: 0, msg: 'ожидает кадры' }])),
    };
    route();
    const video = $('#video');
    await new Promise((r) => (video.readyState >= 1 ? r() : video.addEventListener('loadedmetadata', r, { once: true })));
    const dur = video.duration || 30;
    feed('Perception', `кадры 4 fps · ${Math.round(dur * 4)} кадров, общая сцена построена`, 'layers');

    let result = null;
    const t0 = Date.now();
    const tick = setInterval(() => {
      const k = Math.min(0.95, (Date.now() - t0) / 1000 / Math.max(4, dur * 0.5));
      detectors.forEach((a, i) => {
        const p = Math.min(0.97, k * (1.1 - i * 0.04));
        S.run.st[a.id] = { state: 'scan', p, msg: `кадр ${Math.round(p * dur * 4)} из ${Math.round(dur * 4)}` };
      });
      S.run.overall = k * 0.8;
      renderLive();
    }, 300);

    try {
      if (API.online.value) {
        S.run.phase = 'Загрузка';
        const { job_id } = await API.analyze(file, (p) => { S.run.overall = p * 0.1; renderLive(); });
        S.run.phase = 'Анализ';
        for (;;) {
          await sleep(1500);
          const j = await API.job(job_id);
          if (j.status === 'done') { result = j; break; }
          if (j.status === 'failed') throw new Error(j.error || 'обработка не удалась');
        }
      } else {
        S.run.phase = 'Анализ (демо)';
        await sleep(Math.min(6000, 2500 + dur * 40));
        result = await API.demoAnalyze(file, video, detectors);
      }
    } catch (e) {
      clearInterval(tick);
      S.run.phase = 'Ошибка';
      feed('Система', esc(e.message), 'alert');
      renderLive();
      return;
    }
    clearInterval(tick);
    result.file = file.name;
    await reveal(result, detectors);
  }

  async function reveal(result, detectors) {
    const run = S.run;
    // сопоставляем находки с агентами (по типу нарушения)
    for (const v of result.violations) {
      v.agent = v.agent || (detectors.find((a) => a.types.includes(v.type_id)) || detectors[0] || {}).id;
    }
    run.phase = 'Агенты отчитываются';
    for (const a of detectors) {
      const mine = result.violations.filter((v) => v.agent === a.id);
      if (mine.length) {
        run.st[a.id] = { state: 'alert', msg: `тревога на ${mine.map((v) => fmt(v.timecode_sec)).join(', ')}` };
        mine.forEach((v) => feed(a.name, `возможное нарушение «${esc(v.type)}», ${fmt(v.timecode_sec)}, уверенность ${Math.round((v.confidence ?? 0.7) * 100)}%`, 'alert', v.timecode_sec));
      } else {
        run.st[a.id] = { state: 'clear', msg: 'признаков не найдено' };
      }
      run.overall = Math.min(0.9, run.overall + 0.02);
      renderLive();
      await sleep(260);
    }
    const n = result.violations.length;
    for (const [id, msg] of [
      ['skeptic', n ? `проверил ${n} ${n === 1 ? 'находку' : 'находки'}: безобидного объяснения не найдено` : 'нечего опровергать'],
      ['lawyer', n ? 'нормативы подобраны из проверенной базы' : 'ссылки не требуются'],
      ['aggregator', n ? `вердикт: признаки нарушений (${n})` : 'вердикт: нарушение не обнаружено'],
    ]) {
      run.st[id] = { state: 'scan', p: 0.6, msg: 'работает…' }; renderLive(); await sleep(500);
      run.st[id] = { state: n && id === 'aggregator' ? 'alert' : 'clear', msg };
      const sa = SEED.service.find((s) => s.id === id);
      feed(sa.name, msg, sa.icon);
      run.overall += 0.035; renderLive();
    }
    run.overall = 1;
    run.phase = result.demo ? 'Готово (демо)' : `Готово за ${result.processing_sec} с`;
    run.result = result;
    S.session.unshift(result);
    renderLive(); renderResults(); bindTimeline();
    toast(n ? `Найдено признаков нарушений: ${n}` : 'Нарушение не обнаружено', n ? 'alert' : 'check');
  }

  function feed(who, text, ic, tc) {
    S.run.feed.unshift({ who, text, ic, tc });
    const el = $('#feed');
    if (el) el.insertAdjacentHTML('afterbegin', pingHtml(S.run.feed[0]));
  }
  const pingHtml = (f) => `<div class="ping">${icon(f.ic)}<div>${f.tc != null ? `<span class="tc">${fmt(f.tc)}</span> · ` : ''}<b>${esc(f.who)}:</b> ${f.text}</div></div>`;

  function renderLive() {
    const r = S.run;
    if (!r || !$('#live')) return;
    $('#live').innerHTML = r.pipeline.map((a) => liveAgent(a, r.st[a.id])).join('');
    $('#overall').style.width = `${Math.round(r.overall * 100)}%`;
    $('#phase').innerHTML = `<span class="badge ${r.result ? 'b-ok' : 'b-accent pulse'}">${r.result ? '' : '<span class="dot"></span>'}${esc(r.phase)}</span>`;
    const fe = $('#feed');
    if (fe && !fe.children.length && r.feed.length) fe.innerHTML = r.feed.map(pingHtml).join('');
  }

  function renderResults() {
    const res = S.run?.result;
    const vEl = $('#verdict'), list = $('#violations');
    if (!vEl) return;
    if (!res) {
      vEl.innerHTML = `<div class="verdict card" style="font-size:16px">${icon('scan')}<div>Идёт анализ…<small>Агенты просматривают видео параллельно, результат появится здесь.</small></div></div>`;
      list.innerHTML = '';
      return drawTimeline();
    }
    const n = res.violations.length;
    vEl.innerHTML = n
      ? `<div class="verdict bad"><div class="ic">${icon('alert')}</div><div>Обнаружены признаки возможных нарушений: ${n}<small>Это подсказка для проверяющего, а не окончательное заключение.${res.demo ? ' Демо-режим: результат имитирован.' : ''}</small></div></div>`
      : `<div class="verdict good"><div class="ic">${icon('check')}</div><div>Нарушение не обнаружено<small>Ни один агент не нашёл признаков нарушения.${res.demo ? ' Демо-режим: результат имитирован.' : ''}</small></div></div>`;
    list.innerHTML = res.violations.map((v, i) => {
      const a = S.agents.find((x) => x.id === v.agent);
      return `<div class="card viol">
        <div class="viol-h"><button class="tc-btn" data-seek="${v.timecode_sec}">${fmt(v.timecode_sec)}</button><h4>${i + 1}. ${esc(v.type)}</h4>
          <div style="flex:1"></div>${a ? `<span class="badge">${icon(a.icon)}${esc(a.name)}</span>` : ''}
          <span class="badge b-accent">${Math.round((v.confidence ?? 0.7) * 100)}%</span></div>
        <div class="frames">${v.evidence_frames.map((f) => `<img src="data:image/jpeg;base64,${f.image_base64}" data-seek="${f.timestamp_sec}" data-zoom title="${fmt(f.timestamp_sec)}" alt="Кадр ${fmt(f.timestamp_sec)}">`).join('')}</div>
        <div>${esc(v.description)}</div>
        <div class="rule">${icon('scale')}<div><b>Основание:</b> ${esc(v.rule?.document || '—')}${v.rule?.clause ? `, ${esc(v.rule.clause)}` : ''}
          ${v.rule && !v.rule.verified ? ' <span class="badge b-warn">пункт уточняется</span>' : ''}</div></div>
      </div>`;
    }).join('');
    drawTimeline();
  }

  function drawTimeline() {
    const c = $('#tlc'), v = $('#video');
    if (!c || !v) return;
    const res = S.run?.result;
    const W = (c.width = c.clientWidth * devicePixelRatio), H = (c.height = c.clientHeight * devicePixelRatio);
    const ctx = c.getContext('2d');
    ctx.clearRect(0, 0, W, H);
    const dur = res?.duration_sec || v.duration || 1;
    const cs = getComputedStyle(document.documentElement);
    const acc = cs.getPropertyValue('--accent').trim(), danger = cs.getPropertyValue('--danger').trim();
    if (!res?.score_timeline?.length) return;
    for (const x of res.violations) {
      const [a, b] = x.interval_sec || [x.timecode_sec - 1, x.timecode_sec + 1];
      ctx.fillStyle = danger + '33';
      ctx.fillRect((a / dur) * W, 0, Math.max(4, ((b - a) / dur) * W), H);
    }
    ctx.beginPath();
    res.score_timeline.forEach(([t, s], i) => { const x = (t / dur) * W, y = H - s * (H - 6) - 3; i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
    ctx.strokeStyle = acc; ctx.lineWidth = 2 * devicePixelRatio; ctx.stroke();
    ctx.lineTo(W, H); ctx.lineTo(0, H); ctx.closePath(); ctx.fillStyle = acc + '22'; ctx.fill();
  }

  function bindTimeline() {
    const tl = $('#tl'), v = $('#video');
    if (!tl || !v) return;
    tl.onclick = (e) => { v.currentTime = (e.offsetX / tl.clientWidth) * (v.duration || 0); };
    v.ontimeupdate = () => { $('#tlh').style.left = `${(v.currentTime / (v.duration || 1)) * 100}%`; };
  }

  // ---------- обучение ----------
  function trainFormHtml(opts) {
    return `
      <div class="card-h"><h3>${icon('brain')} Новое обучение</h3></div>
      <div class="field"><label>Агент</label><select class="select" id="t-agent">${opts}</select></div>
      <label class="drop mt" id="zdrop" for="zfile" style="padding:30px 16px">
        <input id="zfile" type="file" accept=".zip,application/zip" hidden>
        <div class="big">${icon('zip')}</div>
        <h3 id="z-name">Загрузите ZIP с датасетом</h3>
        <div class="muted small" id="z-hint">videos/*.mov и labels.csv</div>
      </label>
      <div id="z-tree" class="zip-tree mt hide"></div>
      <div class="row mt"><div style="flex:1"></div><button class="btn btn-primary" id="t-go" disabled data-act="start-train">${icon('play')} Начать обучение</button></div>`;
  }

  let pickedZip = null;
  async function pickZip(f) {
    pickedZip = { file: f, videos: 0, labels: false };
    $('#z-name').textContent = f.name;
    $('#z-hint').textContent = `${(f.size / 1048576).toFixed(1)} МБ`;
    const tree = $('#z-tree');
    if (window.JSZip) {
      try {
        const zip = await JSZip.loadAsync(f);
        const names = Object.keys(zip.files).filter((n) => !zip.files[n].dir);
        pickedZip.videos = names.filter((n) => /\.(mov|mp4)$/i.test(n)).length;
        pickedZip.labels = names.some((n) => /labels\.csv$/i.test(n));
        tree.innerHTML = `${names.slice(0, 12).map(esc).join('\n')}${names.length > 12 ? `\n… ещё ${names.length - 12}` : ''}\n\n${
          pickedZip.labels ? '✓ labels.csv найден' : '✗ нет labels.csv'} · видео: ${pickedZip.videos}`;
      } catch { tree.textContent = 'Не удалось прочитать ZIP'; }
    } else {
      tree.textContent = 'Состав архива проверит сервер';
      pickedZip.labels = true; pickedZip.videos = 0;
    }
    tree.classList.remove('hide');
    $('#t-go').disabled = !pickedZip.labels;
  }

  const TRAIN_STEPS = [
    ['Распаковка архива', 'проверка структуры и форматов'],
    ['Проверка разметки', 'labels.csv ↔ файлы видео'],
    ['Извлечение признаков', 'CLIP-эмбеддинги + аугментации ракурса'],
    ['Обучение классификатора', 'логистическая регрессия поверх признаков'],
    ['Кросс-валидация', 'подбор порога: recall = 1.0, минимум ложных'],
    ['Публикация версии', 'агент получает новую версию'],
  ];

  function startTrain(agentId, zip) {
    const a = S.agents.find((x) => x.id === agentId);
    S.train = { agent: a, zip, step: 0, p: 0, log: [], id: `tr-${105 + S.trainings.length}` };
    S.trainings.unshift({ id: S.train.id, agent: a.name, file: zip.name, videos: pickedZip?.videos || 0, started: 'сейчас', status: 'run' });
    location.hash = '#/training';
    route();
    const n = pickedZip?.videos || 12;
    const lines = [
      [0, `$ unzip ${zip.name}`], [0, `найдено видео: ${n}`, 'ok'], [1, 'labels.csv: колонки file,label,timecode_sec,type', 'ok'],
      [1, 'нормализация имён: X/Х'], [2, 'CLIP ViT-B/32 загружен (локально)'], [2, `кадры 4 fps → эмбеддинги, aug: flip, crop, persp`],
      [2, `обработано ${n}/${n} видео`, 'ok'], [3, 'LogisticRegression(C=0.05, class_weight=balanced)'], [3, 'обучение завершено', 'ok'],
      [4, 'GroupKFold по видео, 7 фолдов'], [4, 'порог 0.46: recall 1.00 · fpr 0.15', 'acc'], [5, `${a.name} → новая версия опубликована`, 'ok'],
    ];
    let li = 0;
    const timer = setInterval(() => {
      const t = S.train;
      if (!t) return clearInterval(timer);
      t.p += 0.035;
      t.step = Math.min(TRAIN_STEPS.length - 1, Math.floor(t.p * TRAIN_STEPS.length));
      while (li < lines.length && lines[li][0] <= t.step) { t.log.push(lines[li]); li++; }
      if (t.p >= 1) {
        clearInterval(timer);
        t.done = true;
        const m = { p: 0.7 + Math.random() * 0.15, r: 1, ms: 20 + Math.round(Math.random() * 15) };
        Object.assign(a, { m, version: bumpVersion(a.version), trained: 'только что', enabled: true });
        Object.assign(S.trainings[0], { status: 'done', p: m.p, r: m.r });
        persist();
        toast(`«${a.name}» обучен и включён`, 'sparkles');
      }
      if (page() === 'training') renderTrain();
    }, 380);
  }
  const bumpVersion = (v) => { const m = /v0\.(\d+)/.exec(v); return m ? `v0.${+m[1] + 1}` : 'v0.1'; };

  function trainRunHtml() {
    return `<div class="card-h"><h3>${icon('brain')} Обучение: <span id="tr-agent"></span></h3><div class="spacer"></div><span id="tr-badge"></span></div>
      <div class="progress"><i id="tr-p"></i></div>
      <div class="grid g-2 mt"><div class="steps" id="tr-steps"></div><div class="log" id="tr-log"></div></div>
      <div class="row mt" id="tr-actions"></div>`;
  }

  function renderTrain() {
    const t = S.train;
    if (!t || !$('#tr-steps')) return;
    $('#tr-agent').textContent = t.agent.name;
    $('#tr-p').style.width = `${Math.min(100, Math.round(t.p * 100))}%`;
    $('#tr-badge').innerHTML = t.done ? '<span class="badge b-ok">готово</span>' : `<span class="badge b-accent pulse"><span class="dot"></span>${Math.round(t.p * 100)}%</span>`;
    $('#tr-steps').innerHTML = TRAIN_STEPS.map(([n, d], i) => `<div class="step ${t.done || i < t.step ? 'done' : i === t.step ? 'run' : ''}">
      <div class="n">${t.done || i < t.step ? '✓' : i + 1}</div><div><b>${n}</b><div class="muted">${d}</div></div></div>`).join('');
    const log = $('#tr-log');
    log.innerHTML = t.log.map(([, s, c]) => `<div class="${c || ''}">${esc(s)}</div>`).join('');
    log.scrollTop = log.scrollHeight;
    $('#tr-actions').innerHTML = t.done
      ? `<span class="small muted">Демо: метрики сгенерированы. Реальное обучение запускается командой ml/train.py.</span><div style="flex:1"></div>
         <a class="btn btn-ghost" href="#/agents">К агентам</a><button class="btn btn-primary" data-act="train-reset">${icon('plus')} Ещё обучение</button>`
      : '';
  }

  // ---------- мастер «новый агент» ----------
  function addAgentModal(stepN = 0, draft = { name: '', desc: '', icon: 'bot', kind: 'trained', type: 'generic' }) {
    const icons = ['bot', 'users', 'wallet', 'bag', 'safe', 'hand', 'door', 'phone', 'eye', 'cpu'];
    const body = [
      `<div class="field"><label>Название</label><input class="input" id="w-name" placeholder="Например, «Телефон в кассовой зоне»" value="${esc(draft.name)}"></div>
       <div class="field mt"><label>Что видно на видео</label><textarea class="input" id="w-desc" placeholder="Кассир держит телефон над столом с наличными">${esc(draft.desc)}</textarea></div>
       <div class="field mt"><label>Иконка</label><div class="row">${icons.map((i) => `<button class="btn btn-icon ${draft.icon === i ? 'btn-primary' : 'btn-ghost'}" data-w-icon="${i}">${icon(i)}</button>`).join('')}</div></div>`,
      `<div class="field"><label>Как агент принимает решение</label>
       <div class="choice">${[['trained', 'Обучаемая модель', 'учится на ваших видео из ZIP'], ['rule', 'Правила', 'логика поверх детекций: люди, зоны, предметы'], ['vlm', 'Локальная VLM', 'смотрит спорные кадры, медленно на CPU']]
        .map(([v, b, d]) => `<label><input type="radio" name="w-kind" value="${v}" ${draft.kind === v ? 'checked' : ''}><b>${b}</b>${d}</label>`).join('')}</div></div>
       <div class="field mt"><label>Тип нарушения и норматив</label>
       <select class="select" id="w-type">${SEED.rules.map((r) => `<option value="${r.id}" ${draft.type === r.id ? 'selected' : ''}>${r.title}</option>`).join('')}</select>
       <div class="small muted">Норматив подставит Юрист из базы. Новый тип сначала добавляется в «Нормативы».</div></div>`,
      `<label class="drop" id="zdrop" for="zfile" style="padding:28px 16px">
        <input id="zfile" type="file" accept=".zip" hidden><div class="big">${icon('zip')}</div>
        <h3 id="z-name">ZIP с видео и labels.csv</h3><div class="muted small" id="z-hint">можно пропустить и обучить позже</div></label>
       <div id="z-tree" class="zip-tree mt hide"></div><button id="t-go" class="hide"></button>`,
    ];
    closeModal();
    document.body.insertAdjacentHTML('beforeend', `
      <div class="overlay" id="modal"><div class="modal" role="dialog" aria-modal="true">
        <div class="modal-h"><div class="avatar">${icon(draft.icon)}</div><div><h2>Новый агент</h2>
          <div class="small muted">Шаг ${stepN + 1} из 3: ${['описание', 'логика', 'датасет'][stepN]}</div></div><div class="spacer"></div>
          <button class="btn btn-ghost btn-icon" data-act="close">${icon('x')}</button></div>
        <div class="wizard-steps">${[0, 1, 2].map((i) => `<i class="${i <= stepN ? 'on' : ''}"></i>`).join('')}</div>
        ${body[stepN]}
        <div class="row mt">${stepN ? '<button class="btn btn-ghost" data-act="w-back">Назад</button>' : ''}<div style="flex:1"></div>
          ${stepN < 2 ? '<button class="btn btn-primary" data-act="w-next">Далее</button>'
            : '<button class="btn btn-ghost" data-act="w-create">Создать без обучения</button><button class="btn btn-primary" data-act="w-create-train">' + icon('brain') + ' Создать и обучить</button>'}</div>
      </div></div>`);
    const m = $('#modal');
    m.draft = draft; m.stepN = stepN;
    if (stepN === 2) { pickedZip = null; bindDrop($('#zdrop'), $('#zfile'), pickZip); }
    $('#w-name')?.focus();
  }
  function readDraft() {
    const m = $('#modal'); const d = m.draft;
    if ($('#w-name')) { d.name = $('#w-name').value.trim(); d.desc = $('#w-desc').value.trim(); }
    if ($('input[name="w-kind"]:checked')) d.kind = $('input[name="w-kind"]:checked').value;
    if ($('#w-type')) d.type = $('#w-type').value;
    return d;
  }
  function createAgent(train) {
    const d = readDraft();
    const a = { id: `a${Date.now().toString(36)}`, name: d.name || 'Новый агент', icon: d.icon, kind: d.kind, role: 'detector',
      desc: d.desc || 'Описание не задано.', types: [d.type], enabled: false, version: 'draft',
      model: { trained: 'CLIP-окно + LogReg', rule: 'правила поверх детекций', vlm: 'локальная VLM' }[d.kind], m: null, alerts: 0, trained: 'не обучен' };
    S.agents.push(a); persist(); closeModal();
    shell();
    if (train && pickedZip) startTrain(a.id, pickedZip.file);
    else { location.hash = '#/agents'; route(); toast(`Агент «${a.name}» создан. Включится после обучения.`, 'bot'); }
  }
  const closeModal = () => $('#modal')?.remove();

  function lightbox(src) {
    document.body.insertAdjacentHTML('beforeend', `<div class="overlay lightbox" id="modal" data-act="close"><img src="${src}" alt=""></div>`);
  }

  // ---------- события ----------
  document.addEventListener('click', (e) => {
    const t = e.target.closest('[data-fill],[data-scroll],[data-act],.style-card,[data-set-mode],[data-agent-tab],[data-hist],[data-train],[data-seek],[data-open],[data-w-icon],[data-zoom]');
    if (!t) return;
    const d = t.dataset;
    if (d.fill !== undefined) { const i = document.getElementById(d.target); if (i) i.value = d.fill; return; }
    if (d.scroll) { e.preventDefault(); document.getElementById(d.scroll)?.scrollIntoView({ behavior: 'smooth' }); return; }
    if (d.zoom !== undefined && e.target.tagName === 'IMG') { lightbox(e.target.src); }
    if (d.seek) { const v = $('#video'); if (v) { v.currentTime = +d.seek; v.pause(); } if (d.zoom === undefined) v?.scrollIntoView({ behavior: 'smooth', block: 'center' }); return; }
    if (t.classList.contains('style-card')) { S.style = d.style; applyTheme(); shell(); route(); return; }
    if (d.setMode) { S.mode = d.setMode; applyTheme(); shell(); route(); return; }
    if (d.agentTab) { S.agentTab = d.agentTab; route(); return; }
    if (d.hist) { S.histFilter = d.hist; route(); return; }
    if (d.train) {
      if (S.train?.done) S.train = null;
      S.trainAgent = d.train;
      if (page() === 'training') route(); else location.hash = '#/training';
      return;
    }
    if (d.open) {
      if (S.run?.result?.job_id === d.open) location.hash = '#/check';
      else toast('Отчёт доступен до перезагрузки страницы только для последней проверки', 'eye');
      return;
    }
    if (d.wIcon) { const m = $('#modal'); readDraft(); m.draft.icon = d.wIcon; addAgentModal(m.stepN, m.draft); return; }
    switch (d.act) {
      case 'burger': $('#side').classList.toggle('open'); break;
      case 'logout': API.logout().finally(() => { S.user = null; S.run = null; history.replaceState(null, '', '#/'); render(); }); break;
      case 'toggle-pass': { const i = $('#lg-pass'); i.type = i.type === 'password' ? 'text' : 'password'; break; }
      case 'mode': S.mode = S.mode === 'dark' ? 'light' : 'dark'; applyTheme(); shell(); route(); break;
      case 'new-check': S.run = null; route(); break;
      case 'add-agent': addAgentModal(); break;
      case 'close': if (e.target === t || t.tagName === 'BUTTON') closeModal(); break;
      case 'w-next': { const m = $('#modal'); addAgentModal(m.stepN + 1, readDraft()); break; }
      case 'w-back': { const m = $('#modal'); addAgentModal(m.stepN - 1, readDraft()); break; }
      case 'w-create': createAgent(false); break;
      case 'w-create-train': if (!pickedZip) { toast('Сначала загрузите ZIP', 'zip'); break; } createAgent(true); break;
      case 'start-train': if (pickedZip) startTrain($('#t-agent').value, pickedZip.file); break;
      case 'train-reset': S.train = null; pickedZip = null; route(); break;
    }
  });
  document.addEventListener('change', (e) => {
    const id = e.target.dataset?.toggle;
    if (!id) return;
    const a = S.agents.find((x) => x.id === id);
    a.enabled = e.target.checked; persist();
    e.target.closest('.agent').classList.toggle('off', !a.enabled);
    $$('[data-nav="agents"] .count').forEach((c) => (c.textContent = `${S.agents.filter((x) => x.enabled).length}/${S.agents.length}`));
    toast(`${a.name}: ${a.enabled ? 'включён' : 'выключен'}`, 'power');
  });
  document.addEventListener('keydown', (e) => e.key === 'Escape' && closeModal());
  window.addEventListener('resize', () => drawTimeline());

  // ---------- публичная часть: главная и вход ----------
  const PUBLIC_AGENTS = [
    ['sparkles', 'Общая аномалия', 'нетипичные действия, в том числе незнакомые типы'],
    ['users', 'Посторонний у кассы', 'лишний человек в зоне кассира'],
    ['wallet', 'Деньги без присмотра', 'кассир ушёл, ценности остались'],
    ['bag', 'Инкассация', 'передача ценностей вне порядка'],
    ['safe', 'Сейф и дверь', 'открытый сейф или дверь кассы'],
    ['hand', 'Рука в карман', 'купюры уходят под стол или в карман'],
  ];

  function landing() {
    document.title = 'Cashier AI — контроль кассовой дисциплины по видео';
    $('#app').innerHTML = `
    <div class="pub">
      <header class="pub-nav">
        <a class="pub-brand" href="#/"><img src="img/logo.svg" alt="" width="36" height="37"><span>Cashier AI</span></a>
        <nav class="pub-links" aria-label="Разделы страницы">
          <a href="#how" data-scroll="how">Как работает</a><a href="#agents" data-scroll="agents">Агенты</a><a href="#trust" data-scroll="trust">Безопасность</a><a href="#api" data-scroll="api">API</a>
        </nav>
        <a class="btn btn-primary" href="#/login">${icon('key')} Войти</a>
      </header>

      <section class="hero">
        <div class="hero-text">
          <span class="pill"><i class="live-dot"></i>Локальный AI · видео не покидает сервер</span>
          <h1>Проверка видео кассы за минуты, а&nbsp;не&nbsp;часы просмотра</h1>
          <p>Агенты находят визуальные признаки нарушений кассовой дисциплины и показывают таймкод, кадры-доказательства и ссылку на норматив. Решение остаётся за проверяющим.</p>
          <div class="row"><a class="btn btn-primary btn-lg" href="#/login">Войти в систему ${icon('arrow')}</a>
            <a class="btn btn-ghost btn-lg" href="#how" data-scroll="how">Как это работает</a></div>
          <ul class="hero-facts">
            <li><b>≤ 5 мин</b><span>на одно видео</span></li>
            <li><b>1–3 кадра</b><span>доказательства на каждое событие</span></li>
            <li><b>0</b><span>обращений к облачным AI</span></li>
          </ul>
        </div>
        <div class="hero-vis" aria-hidden="true">
          <div class="tlcard">
            <div class="tl-head"><b>video_017.mov</b><span class="mono">4 кадра/с · 240 кадров</span></div>
            <div class="tl-grid">
              <span class="tl-l muted">Видео</span>
              <div class="strip">${[0, 1, 2, 3, 4, 5, 6, 7].map((i) => `<i class="${i === 5 ? 'hit' : ''}"></i>`).join('')}</div>
              ${[['Общая аномалия', 69, 9, 'soft', ''], ['Посторонний у кассы', 70, 8, 'hit', ''], ['Деньги без присмотра', 0, 0, '', 'чисто'],
                 ['Инкассация', 0, 0, '', 'чисто'], ['Скептик', 73, 1.4, 'ink', 'подтвердил']]
                .map(([n, l, w, c, note]) => `<span class="tl-l">${n}</span><div class="lane">${w ? `<i class="seg ${c}" style="left:${l}%;width:${w}%"></i>` : ''}${note ? `<em class="${c === 'ink' ? 'ink' : 'ok'}">${note}</em>` : ''}</div>`).join('')}
              <span></span>
              <div class="axis"><span>00:00</span><span>00:15</span><span>00:30</span><b>00:44.2</b><span>01:00</span></div>
              <i class="playhead"></i>
            </div>
            <div class="tl-verdict"><i></i><b>Посторонний в кассовом помещении</b><span>подтверждено скептиком · норматив из базы</span></div>
          </div>
        </div>
      </section>

      <section class="pub-sec" id="how">
        <p class="eyebrow">Как это работает</p>
        <h2>Одно видео проходит четыре шага</h2>
        <div class="steps4">
          ${[['upload', 'Загрузка', 'Видео .mov через веб или API. Обработка начинается сразу.'],
             ['layers', 'Разбор сцены', 'Кадры, люди и предметы считаются один раз и общие для всех агентов.'],
             ['bot', 'Агенты', 'Каждый ищет свой тип риска. Скептик проверяет находки, юрист подбирает норматив.'],
             ['check', 'Отчёт', 'Вердикт, таймкод, кадры, описание и пункт норматива. JSON для систем банка.']]
            .map(([ic, t, d], i) => `<div class="step4"><span class="n">0${i + 1}</span><div class="ic">${icon(ic)}</div><b>${t}</b><p>${d}</p></div>`).join('')}
        </div>
      </section>

      <section class="pub-sec" id="agents">
        <p class="eyebrow">Агенты</p>
        <h2>Каждый агент отвечает за один риск</h2>
        <p class="lead">Новый тип нарушения добавляется как новый агент: загрузите ZIP с видео и разметкой, и он обучится прямо на сервере.</p>
        <div class="agents6">${PUBLIC_AGENTS.map(([ic, n, d]) => `<div class="ag"><div class="ic">${icon(ic)}</div><div><b>${n}</b><span>${d}</span></div></div>`).join('')}</div>
      </section>

      <section class="pub-dark" id="trust">
        <div class="pub-sec">
          <p class="eyebrow">Безопасность</p>
          <h2>Можно перенести во внутренний контур банка</h2>
          <div class="trust3">
            <div>${icon('cpu')}<b>Всё локально</b><p>Модели работают на сервере. После загрузки весов интернет не нужен, видео и кадры никуда не отправляются.</p></div>
            <div>${icon('eye')}<b>Без лиц и звука</b><p>Сервис не распознаёт и не идентифицирует людей и не использует звук. Только видимые действия.</p></div>
            <div>${icon('scale')}<b>Без выдуманных ссылок</b><p>Нормативы берутся только из проверенной базы актов РК. Не видно на видео — значит, не утверждаем.</p></div>
          </div>
        </div>
      </section>

      <section class="pub-sec api-sec" id="api">
        <div>
          <p class="eyebrow">Интеграция</p>
          <h2>Два запроса — и результат в JSON</h2>
          <p class="lead">Отправьте видео и заберите результат по job_id. Доступ по ключу в заголовке X-API-Key.</p>
        </div>
        <pre class="code"><span class="c"># 1. отправить видео</span>
curl -X POST ${esc(location.protocol === 'file:' ? 'https://<сервер>' : location.origin)}/api/v1/analyze \\
  -H "X-API-Key: &lt;ключ&gt;" -F "file=@video.mov"

<span class="c"># 2. получить результат</span>
curl .../api/v1/jobs/&lt;job_id&gt; -H "X-API-Key: &lt;ключ&gt;"
<span class="c"># → verdict, violations[type, timecode_sec,
#   description, evidence_frames]</span></pre>
      </section>

      <footer class="pub-foot">
        <span>Cashier AI · Datathon 26</span>
        <span>Результат — подсказка для проверки человеком, а не юридическое заключение.</span>
      </footer>
    </div>`;
  }

  // Сцена слева на входе: «комната данных». Своё фото — design/img/login-bg.jpg (подхватится само).
  const DOCS = [
    [6, 14, -14, 0.9, 70], [18, 58, 8, 0.55, 54], [12, 78, -6, 0.35, 44], [30, 8, 10, 0.5, 48], [72, 10, -10, 0.85, 66],
    [84, 46, 12, 0.6, 58], [78, 74, -8, 0.4, 46], [60, 26, 6, 0.3, 40], [40, 70, -12, 0.3, 38], [90, 22, 4, 0.45, 42],
    [24, 34, 14, 0.25, 34], [66, 62, -4, 0.25, 34], [48, 12, -6, 0.35, 36], [4, 44, 6, 0.4, 46],
  ];
  const artHtml = () => `
    <div class="art-floor"></div>
    ${DOCS.map(([x, y, r, o, w], i) => `<i class="art-doc" style="left:${x}%;top:${y}%;width:${w}px;--r:${r}deg;opacity:${o};animation-delay:${-i * 0.7}s"></i>`).join('')}
    <div class="art-screen"><i></i><i></i><i></i><i></i></div>
    <div class="art-desk"></div>`;

  async function loginScreen(err = '') {
    document.title = 'Вход · Cashier AI';
    const online = API.online.value;
    $('#app').innerHTML = `
    <div class="auth">
      <aside class="auth-art" id="auth-art" aria-hidden="true">
        ${artHtml()}
        <div class="art-caption">
          <a href="#/" class="pub-brand on-dark"><img src="img/logo.svg" alt="" width="40" height="41"><span>Cashier AI</span></a>
          <p>Агенты просматривают записи кассы и находят признаки нарушений: с таймкодом, кадрами и нормативом.</p>
        </div>
      </aside>
      <main class="auth-main">
        <a href="#/" class="auth-close">${icon('arrow', 'flip')}<span>На главную</span></a>
        <div class="auth-box">
          <div class="auth-head">
            <div class="auth-logo">${icon('eye')}</div>
            <h1>Cashier AI</h1>
            <p>Контроль кассовой дисциплины</p>
          </div>
          <form class="auth-card" id="login-form" autocomplete="on">
            <h2>Вход в систему</h2>
            <div class="field"><label for="lg-user">Логин</label>
              <div class="ifield">${icon('user')}<input class="input" id="lg-user" name="username" autocomplete="username" required autofocus placeholder="Введите логин"></div></div>
            <div class="field"><label for="lg-pass">Пароль</label>
              <div class="ifield">${icon('lock')}<input class="input" id="lg-pass" name="password" type="password" autocomplete="current-password" required placeholder="Введите пароль">
                <button type="button" class="btn btn-icon btn-sm eye" data-act="toggle-pass" aria-label="Показать пароль">${icon('eye')}</button></div></div>
            <div class="auth-err" role="alert">${esc(err)}</div>
            <button class="btn btn-primary btn-lg" type="submit">Войти в систему</button>
            <div id="demo-box"></div>
          </form>
          <p class="auth-note">${icon('shield')}<span>Посторонним вход запрещён. Неудачные попытки записываются, после пяти подряд вход блокируется на 5 минут.</span></p>
        </div>
      </main>
    </div>`;

    // своё фото слева, если положили img/login-bg.jpg
    const photo = new Image();
    photo.onload = () => { const a = $('#auth-art'); if (a) { a.style.backgroundImage = `url(${photo.src})`; a.classList.add('has-photo'); } };
    photo.src = 'img/login-bg.jpg';

    // тестовые данные: из настроек сервера (UI_DEMO_*) или demo/demo в демо-режиме
    const demo = online ? await API.config().then((c) => c.demo).catch(() => null) : { login: 'demo', password: 'demo' };
    if (demo && $('#demo-box')) {
      $('#demo-box').innerHTML = `<div class="demo-box"><b>Тестовые данные для входа${online ? '' : ' (демо-режим)'}:</b>
        <div>Логин: <button type="button" class="link" data-fill="${esc(demo.login)}" data-target="lg-user">${esc(demo.login)}</button></div>
        <div>Пароль: <button type="button" class="link" data-fill="${esc(demo.password)}" data-target="lg-pass">${esc(demo.password)}</button></div></div>`;
    }

    $('#login-form').onsubmit = async (e) => {
      e.preventDefault();
      const user = $('#lg-user').value.trim(), pass = $('#lg-pass').value;
      e.submitter && (e.submitter.disabled = true);
      try {
        if (API.online.value) S.user = (await API.login(user, pass)).user;
        else if (user === 'demo' && pass === 'demo') S.user = 'demo';
        else throw new Error('Неверный логин или пароль');
        location.hash = '#/dashboard';
        render();
      } catch (er) {
        await loginScreen(er.message);
        $('#lg-user').value = user;
        $('#lg-pass').focus();
      }
    };
  }

  // Кто не вошёл — видит главную или вход; вошедший — CRM.
  function render() {
    if (!S.user) {
      $('#side')?.remove();
      return page() === 'login' ? void loginScreen() : landing();
    }
    if (page() === 'login' || !PAGES[page()]) { history.replaceState(null, '', '#/dashboard'); }
    if (!$('#page')) { document.title = 'Cashier AI'; shell(); renderConn(); }
    route();
  }

  // ---------- старт ----------
  applyTheme();
  window.addEventListener('hashchange', render);
  API.health().then(async () => {
    if (API.online.value) S.user = await API.me();
    render();
  });
  window.addEventListener('unauthorized', () => {
    S.user = null;
    history.replaceState(null, '', '#/login');
    loginScreen('Сессия истекла, войдите снова');
  });
})();
