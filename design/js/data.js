// Демо-данные прототипа. Метрики и история здесь ВЫДУМАННЫЕ (для вёрстки) — в интерфейсе помечены «демо».
// Реальные данные придут из API (см. api.js), когда бэкенд получит эндпоинты агентов и обучения.

window.SEED = {
  // Типы нарушений и нормативы — зеркало app/rules/violations.yaml (пункты ещё не проверены).
  rules: [
    { id: 'unauthorized_person', title: 'Посторонний в кассовом помещении', doc: 'security_rules', clause: null },
    { id: 'cashier_left_workplace', title: 'Кассир оставил ценности без присмотра', doc: 'cash_rules', clause: null },
    { id: 'safe_left_open', title: 'Сейф оставлен открытым', doc: 'security_rules', clause: null },
    { id: 'improper_handover', title: 'Нарушение порядка передачи ценностей (инкассация)', doc: 'cash_rules', clause: null },
    { id: 'door_open', title: 'Дверь кассы открыта при работе с ценностями', doc: 'security_rules', clause: null },
    { id: 'generic', title: 'Признаки возможного нарушения кассовой дисциплины', doc: 'cash_rules', clause: null },
  ],
  documents: {
    security_rules: {
      title: 'Правила организации охраны и устройства помещений банков второго уровня',
      req: 'пост. Правления НБРК № 14 от 24.02.2020 (изм. № 88 от 24.12.2024)',
      url: null, verified: false,
    },
    cash_rules: {
      title: 'Правила ведения кассовых операций в БВУ',
      req: 'действующая редакция — уточняется на adilet.zan.kz',
      url: null, verified: false,
    },
  },

  agents: [
    { id: 'anomaly', name: 'Общая аномалия', icon: 'sparkles', kind: 'trained', role: 'detector',
      desc: 'CLIP + классификатор: ловит любое нетипичное действие в кассовой зоне, в том числе незнакомые типы.',
      types: ['generic'], enabled: true, version: 'v0.3', model: 'CLIP ViT-B/32 + LogReg',
      m: { p: 0.81, r: 1.0, ms: 34 }, alerts: 41, trained: '17.10, 14:20' },
    { id: 'stranger', name: 'Посторонний у кассы', icon: 'users', kind: 'rule', role: 'detector',
      desc: 'Считает людей за кассовой стойкой: больше одного человека в зоне кассира дольше 2 секунд.',
      types: ['unauthorized_person'], enabled: true, version: 'v0.2', model: 'детектор людей + зоны',
      m: { p: 0.88, r: 0.93, ms: 21 }, alerts: 17, trained: '17.10, 13:05' },
    { id: 'unattended', name: 'Деньги без присмотра', icon: 'wallet', kind: 'rule', role: 'detector',
      desc: 'Кассир ушёл из зоны стола, а на столе остались ценности или открытый ящик.',
      types: ['cashier_left_workplace'], enabled: true, version: 'v0.1', model: 'трекинг + состояние стола',
      m: { p: 0.79, r: 0.9, ms: 18 }, alerts: 12, trained: '17.10, 12:48' },
    { id: 'handover', name: 'Инкассация: протокол', icon: 'bag', kind: 'trained', role: 'detector',
      desc: 'Передача сумки с ценностями вне установленного порядка: через дверь, без проверки, вне зоны.',
      types: ['improper_handover'], enabled: true, version: 'v0.1', model: 'CLIP-окно + LogReg',
      m: { p: 0.74, r: 0.86, ms: 29 }, alerts: 9, trained: '17.10, 15:02' },
    { id: 'safe', name: 'Сейф и дверь', icon: 'safe', kind: 'trained', role: 'detector',
      desc: 'Открытая дверца сейфа или дверь кассового помещения во время работы с наличными.',
      types: ['safe_left_open', 'door_open'], enabled: true, version: 'v0.1', model: 'CLIP zero-shot',
      m: { p: 0.7, r: 0.8, ms: 12 }, alerts: 6, trained: '—' },
    { id: 'pocket', name: 'Рука в карман / под стол', icon: 'hand', kind: 'rule', role: 'detector',
      desc: 'Поза кассира: рука с купюрами уходит ниже столешницы или к карману, а затем пустая.',
      types: ['generic'], enabled: false, version: 'draft', model: 'поза (keypoints)',
      m: null, alerts: 0, trained: 'не обучен' },
    { id: 'vlm', name: 'VLM-аномалия', icon: 'eye', kind: 'vlm', role: 'detector',
      desc: 'Локальная мультимодальная модель смотрит только спорные фрагменты, которые не покрыл ни один агент.',
      types: ['generic'], enabled: false, version: 'draft', model: 'локальная VLM (CPU)',
      m: null, alerts: 0, trained: 'не обучен' },
  ],

  // Служебные агенты конвейера — всегда включены
  service: [
    { id: 'skeptic', name: 'Скептик', icon: 'shield', desc: 'Ищет безобидное объяснение и снижает уверенность. Не удаляет тревогу: пропуск хуже ложного срабатывания.' },
    { id: 'lawyer', name: 'Юрист', icon: 'scale', desc: 'Подбирает норматив только из проверенной базы. Ссылки не генерирует.' },
    { id: 'aggregator', name: 'Агрегатор', icon: 'layers', desc: 'Склеивает дубли, выносит вердикт, собирает JSON по схеме ТЗ.' },
  ],

  history: [
    { id: '3f2a9c1e', file: 'video_017.mov', when: 'сегодня, 15:42', dur: 44, verdict: 'violation', n: 2, sec: 38, types: ['unauthorized_person', 'improper_handover'] },
    { id: '8b1e44d0', file: 'cam2_1530.mov', when: 'сегодня, 15:30', dur: 87, verdict: 'no_violation', n: 0, sec: 61, types: [] },
    { id: 'c04f9a71', file: 'X-13.mov', when: 'сегодня, 14:58', dur: 62, verdict: 'violation', n: 1, sec: 47, types: ['cashier_left_workplace'] },
    { id: '5d7710ab', file: 'X-21.mov', when: 'сегодня, 14:41', dur: 31, verdict: 'no_violation', n: 0, sec: 22, types: [] },
    { id: 'e9a3c215', file: 'X-47.mov', when: 'сегодня, 14:12', dur: 145, verdict: 'violation', n: 1, sec: 109, types: ['improper_handover'] },
    { id: '1a6b0f9e', file: 'kassa3_am.mov', when: 'вчера, 18:03', dur: 73, verdict: 'violation', n: 1, sec: 55, types: ['safe_left_open'] },
    { id: '7cc2e810', file: 'X-35.mov', when: 'вчера, 17:20', dur: 26, verdict: 'no_violation', n: 0, sec: 19, types: [] },
    { id: '2be95d44', file: 'X-4.mov', when: 'вчера, 16:55', dur: 66, verdict: 'violation', n: 1, sec: 51, types: ['unauthorized_person'] },
  ],

  week: [ // проверки по дням: [с нарушением, без]
    ['Пн', 6, 9], ['Вт', 4, 11], ['Ср', 8, 7], ['Чт', 5, 12], ['Пт', 9, 10], ['Сб', 3, 4], ['Вс', 7, 6],
  ],

  trainings: [
    { id: 'tr-104', agent: 'Инкассация: протокол', file: 'handover_v1.zip', videos: 14, started: '17.10, 14:51', status: 'done', p: 0.74, r: 0.86 },
    { id: 'tr-103', agent: 'Общая аномалия', file: 'open_dataset.zip', videos: 42, started: '17.10, 14:02', status: 'done', p: 0.81, r: 1.0 },
    { id: 'tr-102', agent: 'Рука в карман / под стол', file: 'pocket_raw.zip', videos: 6, started: '17.10, 13:40', status: 'failed', err: 'labels.csv не найден' },
  ],
};
