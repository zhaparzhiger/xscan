const $ = (id) => document.getElementById(id);
const drop = $("drop"), input = $("file"), statusEl = $("status"), player = $("player");
let timeline = [], duration = 0, violations = [];

drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => {
  e.preventDefault(); drop.classList.remove("over");
  if (e.dataTransfer.files[0]) start(e.dataTransfer.files[0]);
});
input.addEventListener("change", () => input.files[0] && start(input.files[0]));

function fmt(sec) {
  const m = Math.floor(sec / 60), s = (sec % 60).toFixed(1).padStart(4, "0");
  return `${String(m).padStart(2, "0")}:${s}`;
}

function start(file) {
  $("result").hidden = true;
  player.src = URL.createObjectURL(file);
  const form = new FormData();
  form.append("file", file);
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/ui/analyze");
  $("progress").hidden = false;
  xhr.upload.onprogress = (e) => { $("bar").style.width = `${(100 * e.loaded / e.total).toFixed(0)}%`; };
  statusEl.textContent = "Загрузка видео…";
  xhr.onload = () => {
    if (xhr.status !== 200) { statusEl.textContent = "Ошибка загрузки: " + xhr.responseText; return; }
    poll(JSON.parse(xhr.responseText).job_id, Date.now());
  };
  xhr.onerror = () => { statusEl.textContent = "Сетевая ошибка при загрузке"; };
  xhr.send(form);
}

async function poll(jobId, t0) {
  const r = await fetch(`/ui/jobs/${jobId}`);
  const job = await r.json();
  if (job.status === "processing") {
    statusEl.textContent = `Анализ видео… ${Math.round((Date.now() - t0) / 1000)} с`;
    setTimeout(() => poll(jobId, t0), 1500);
    return;
  }
  if (job.status === "failed") { statusEl.textContent = "Ошибка обработки: " + (job.error || ""); return; }
  statusEl.textContent = `Готово за ${job.processing_sec ?? "?"} с · задача ${jobId}`;
  render(job);
}

function render(job) {
  $("result").hidden = false;
  const v = $("verdict");
  violations = job.violations || [];
  timeline = job.score_timeline || [];
  duration = job.duration_sec || (timeline.length ? timeline[timeline.length - 1][0] : 0);
  if (job.verdict === "violation") {
    v.className = "card bad";
    v.textContent = `Обнаружены признаки возможных нарушений: ${violations.length}`;
  } else {
    v.className = "card good";
    v.textContent = "Нарушение не обнаружено";
  }
  const list = $("violations");
  list.innerHTML = "";
  violations.forEach((x, i) => {
    const card = document.createElement("div");
    card.className = "card v";
    const rule = x.rule || {};
    card.innerHTML = `
      <h3>${i + 1}. ${esc(x.type)}</h3>
      <button class="tc">${fmt(x.timecode_sec)}</button>
      <span class="muted small">уверенность ${(100 * (x.confidence ?? 0)).toFixed(0)}%</span>
      <div class="frames">${x.evidence_frames.map((f) =>
        `<img src="data:image/jpeg;base64,${f.image_base64}" title="${fmt(f.timestamp_sec)}" data-t="${f.timestamp_sec}">`).join("")}</div>
      <p>${esc(x.description)}</p>
      <div class="rule">Источник: ${esc(rule.document || "—")}${rule.clause ? ", " + esc(rule.clause) : ""}
        ${rule.url ? ` · <a href="${rule.url}" target="_blank" rel="noopener">adilet.zan.kz</a>` : ""}</div>`;
    card.querySelector(".tc").onclick = () => seek(x.timecode_sec);
    card.querySelectorAll("img").forEach((img) => (img.onclick = () => seek(+img.dataset.t)));
    list.appendChild(card);
  });
  drawTimeline();
}

function seek(t) { player.currentTime = t; player.pause(); player.scrollIntoView({ behavior: "smooth", block: "center" }); }

function drawTimeline() {
  const c = $("timeline"), ctx = c.getContext("2d");
  c.width = c.clientWidth * devicePixelRatio; c.height = 60 * devicePixelRatio;
  const W = c.width, H = c.height;
  ctx.clearRect(0, 0, W, H);
  if (!timeline.length || !duration) return;
  ctx.strokeStyle = "#a6192e"; ctx.lineWidth = 2 * devicePixelRatio; ctx.beginPath();
  timeline.forEach(([t, s], i) => { const x = (t / duration) * W, y = H - s * (H - 4) - 2; i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
  ctx.stroke();
  ctx.fillStyle = "rgba(166,25,46,.25)";
  violations.forEach((x) => { const [a, b] = x.interval_sec || [x.timecode_sec, x.timecode_sec];
    ctx.fillRect((a / duration) * W, 0, Math.max(3, ((b - a) / duration) * W), H); });
  c.onclick = (e) => seek((e.offsetX / c.clientWidth) * duration);
}
window.addEventListener("resize", drawTimeline);

function esc(s) { return String(s ?? "").replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch])); }
