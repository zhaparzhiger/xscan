// Слой данных. Если страница открыта с нашего FastAPI (/design), анализ видео идёт по-настоящему через /ui/*.
// Открыта как файл или сервер недоступен -> демо-режим: результат имитируется, кадры берутся из самого видео.
//
// Эндпоинты, которые фронт ждёт от бэкенда для агентов и обучения (пока НЕ реализованы, работает имитация):
//   GET  /ui/agents                    -> список агентов с метриками
//   PATCH /ui/agents/{id}              -> {enabled, threshold}
//   POST /ui/agents                    -> создать агента {name, kind, types[]}
//   POST /ui/agents/{id}/train         -> multipart zip (videos/*.mov + labels.csv) -> {training_id}
//   GET  /ui/trainings/{training_id}   -> {status, step, progress, log[], metrics}

window.API = (() => {
  const online = { value: false, info: null };

  async function health() {
    if (location.protocol === 'file:') return (online.value = false);
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 1500);
      const r = await fetch('/health', { signal: ctrl.signal });
      clearTimeout(t);
      online.info = r.ok ? await r.json() : null;
      online.value = r.ok;
    } catch { online.value = false; }
    return online.value;
  }

  function analyze(file, onProgress) {
    return new Promise((resolve, reject) => {
      const form = new FormData();
      form.append('file', file);
      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/ui/analyze');
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
      xhr.onload = () => {
        if (xhr.status === 200) return resolve(JSON.parse(xhr.responseText));
        if (xhr.status === 401) window.dispatchEvent(new Event('unauthorized'));
        reject(new Error(xhr.responseText));
      };
      xhr.onerror = () => reject(new Error('сеть недоступна'));
      xhr.send(form);
    });
  }

  async function job(id) {
    const r = await fetch(`/ui/jobs/${id}`, { credentials: 'same-origin' });
    if (r.status === 401) { window.dispatchEvent(new Event('unauthorized')); throw new Error('нужен вход'); }
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }

  async function jobsList() {
    const r = await fetch('/ui/jobs', { credentials: 'same-origin' });
    if (r.status === 401) { window.dispatchEvent(new Event('unauthorized')); throw new Error('нужен вход'); }
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return (await r.json()).jobs;
  }

  async function evalReport() {
    const r = await fetch('/ui/eval', { credentials: 'same-origin' });
    if (r.status === 401) { window.dispatchEvent(new Event('unauthorized')); throw new Error('нужен вход'); }
    if (!r.ok) throw new Error('Замер ещё не запускали');
    return r.json();
  }

  async function config() {
    const r = await fetch('/ui/config');
    return r.ok ? r.json() : {};
  }

  async function me() {
    try {
      const r = await fetch('/ui/me', { credentials: 'same-origin' });
      return r.ok ? (await r.json()).user : null;
    } catch { return null; }
  }

  async function login(user, password) {
    const r = await fetch('/ui/login', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ login: user, password }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Не удалось войти');
    return data;
  }

  async function logout() {
    if (online.value) await fetch('/ui/logout', { method: 'POST', credentials: 'same-origin' }).catch(() => {});
  }

  // ---------- демо-режим ----------
  function grab(video, t) {
    return new Promise((resolve) => {
      const done = () => {
        const c = document.createElement('canvas');
        const scale = 480 / Math.max(video.videoWidth, video.videoHeight);
        c.width = video.videoWidth * scale; c.height = video.videoHeight * scale;
        const ctx = c.getContext('2d');
        ctx.drawImage(video, 0, 0, c.width, c.height);
        ctx.fillStyle = 'rgba(0,0,0,.6)'; ctx.fillRect(0, 0, c.width, 26);
        ctx.fillStyle = '#fff'; ctx.font = '600 14px monospace'; ctx.fillText(fmt(t), 8, 18);
        resolve(c.toDataURL('image/jpeg', 0.82).split(',')[1]);
      };
      video.addEventListener('seeked', done, { once: true });
      video.currentTime = t;
    });
  }

  async function demoAnalyze(file, video, agents) {
    const dur = video.duration || 30;
    // детерминированно от размера файла, чтобы одно и то же видео давало один результат
    const seed = file.size % 997;
    const has = seed % 5 !== 0;
    const active = agents.filter((a) => a.enabled);
    const picks = has ? active.filter((_, i) => (seed + i) % 3 === 0).slice(0, 2) : [];
    if (has && !picks.length && active.length) picks.push(active[seed % active.length]);
    const violations = [];
    for (const [i, a] of picks.entries()) {
      const tc = Math.max(1, Math.min(dur - 1, dur * (0.25 + 0.4 * i) + (seed % 7)));
      const shots = [Math.max(0, tc - 1), tc, Math.min(dur - 0.1, tc + 1)];
      const frames = [];
      for (const t of shots) frames.push({ timestamp_sec: +t.toFixed(2), image_base64: await grab(video, t) });
      const rule = SEED.rules.find((r) => r.id === a.types[0]);
      violations.push({
        type: rule.title, type_id: rule.id, agent: a.id, timecode_sec: +tc.toFixed(2),
        confidence: 0.62 + ((seed + i * 13) % 30) / 100, interval_sec: [+(tc - 1.5).toFixed(2), +(tc + 2).toFixed(2)],
        description: `${fmt(tc)}: ${a.desc} Это может указывать на нарушение. Требуется проверка человеком.`,
        evidence_frames: frames,
        rule: { document: SEED.documents[rule.doc].title, clause: null, verified: false },
      });
    }
    const timeline = [];
    for (let t = 0; t <= dur; t += 0.5) {
      let s = 0.08 + 0.06 * Math.abs(Math.sin(t * 0.7 + seed));
      for (const v of violations) s = Math.max(s, 0.95 * Math.exp(-((t - v.timecode_sec) ** 2) / 3));
      timeline.push([t, +s.toFixed(3)]);
    }
    video.currentTime = 0;
    return {
      job_id: Math.random().toString(16).slice(2, 10), status: 'done', demo: true,
      verdict: violations.length ? 'violation' : 'no_violation', violations,
      duration_sec: dur, processing_sec: +(dur * 0.6).toFixed(1), score_timeline: timeline,
    };
  }

  return { online, health, analyze, job, me, config, login, logout, demoAnalyze, evalReport, jobsList };
})();

window.fmt = (sec) => {
  const m = Math.floor(sec / 60);
  const s = (sec % 60).toFixed(1).padStart(4, '0');
  return `${String(m).padStart(2, '0')}:${s}`;
};
