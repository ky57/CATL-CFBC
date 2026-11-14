/* CATL-CFBC 故障信息收集系统 — 前端逻辑（无第三方依赖） */
(() => {
  'use strict';

  const state = {
    today: '',
    date: '',
    lines: ['L1', 'L2', 'L3', 'L4', 'L5', 'L6'],
    items: ['功率板', 'ACDC', 'DCDC', '中位机'],
    stats: null,
    records: [],
    dates: [],
    qty: 0,
    editQty: 1,
    qtyItem: '',
    qtyMode: 'form',
    summary: null,
    submitting: false,
    loading: false,
    editingId: null,
    summaryBusy: false,
  };

  const $ = (id) => document.getElementById(id);
  const els = {
    form: $('record-form'),
    reason: $('fault-reason'),
    charCount: $('char-count'),
    submitBtn: $('submit-btn'),
    submitText: $('submit-text'),
    resetBtn: $('reset-btn'),
    formAlert: $('form-alert'),
    lineFieldset: $('line-fieldset'),
    itemFieldset: $('item-fieldset'),
    lineError: $('line-error'),
    itemError: $('item-error'),
    reasonError: $('reason-error'),
    lineState: $('line-state'),
    itemState: $('item-state'),
    itemGrid: $('item-grid'),
    itemAdd: $('item-add'),
    itemAddBtn: $('item-add-btn'),
    itemAddInput: $('item-add-input'),
    itemAddSave: $('item-add-save'),
    editItemGrid: $('edit-item-grid'),
    overviewTitle: $('overview-title'),
    overviewDate: $('overview-date'),
    totalCount: $('total-count'),
    countRing: $('count-ring'),
    lineBars: $('line-bars'),
    itemBars: $('item-bars'),
    lineTotal: $('line-total'),
    itemTotal: $('item-total'),
    recordList: $('record-list'),
    recordsCount: $('records-count'),
    emptyState: $('empty-state'),
    updatedAt: $('updated-at'),
    refreshBtn: $('refresh-btn'),
    summaryBox: $('summary-box'),
    summaryText: $('summary-text'),
    summaryMeta: $('summary-meta'),
    summaryEmpty: $('summary-empty'),
    summaryGenerate: $('summary-generate'),
    summaryCopy: $('summary-copy'),
    editDialog: $('edit-dialog'),
    editForm: $('edit-form'),
    editMeta: $('edit-meta'),
    editReason: $('edit-reason'),
    editError: $('edit-error'),
    editSave: $('edit-save'),
    editCancel: $('edit-cancel'),
    editClose: $('edit-close'),
    datePicker: $('date-picker'),
    dateLoad: $('date-load'),
    dateToday: $('date-today'),
    historyOpen: $('history-open'),
    historyToday: $('history-today'),
    historyDialog: $('history-dialog'),
    historyList: $('history-list'),
    historyEmpty: $('history-empty'),
    historyClose: $('history-close'),
    statChart: $('stat-chart'),
    qtyDialog: $('qty-dialog'),
    qtyForm: $('qty-form'),
    qtyTitle: $('qty-title'),
    qtyItemName: $('qty-item-name'),
    qtyPresets: $('qty-presets'),
    qtyCustom: $('qty-custom'),
    qtyError: $('qty-error'),
    qtyClose: $('qty-close'),
    downloadCsv: $('download-csv'),
    downloadMd: $('download-md'),
    copyDigest: $('copy-digest'),
    lastArchive: $('last-archive'),
    headerDate: $('header-date'),
    headerTime: $('header-time'),
    footerClock: $('footer-clock'),
    liveDot: $('live-dot'),
    liveText: $('live-text'),
    toastRegion: $('toast-region'),
  };

  const weekdays = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'];

  // ------------------------------------------------------------------
  // 通用
  // ------------------------------------------------------------------
  async function api(path, options = {}) {
    const response = await fetch(path, {
      cache: 'no-store',
      headers: {
        Accept: 'application/json',
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(options.headers || {}),
      },
      ...options,
    });
    let payload = null;
    try {
      payload = await response.json();
    } catch (error) {
      throw new Error('服务器返回了无法解析的数据');
    }
    if (!response.ok || payload.ok === false) {
      throw new Error(payload.error || `请求失败（${response.status}）`);
    }
    return payload;
  }

  function setLive(online) {
    els.liveDot.classList.toggle('is-offline', !online);
    els.liveText.textContent = online ? '在线' : '连不上';
  }

  function pad2(value) {
    return String(value).padStart(2, '0');
  }

  function tickClock() {
    const now = new Date();
    const clock = `${pad2(now.getHours())}:${pad2(now.getMinutes())}:${pad2(now.getSeconds())}`;
    els.headerTime.textContent = clock;
    els.footerClock.textContent = clock;
    els.headerDate.textContent =
      `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日${weekdays[now.getDay()]}`;
  }

  function dateLabel(iso) {
    if (!iso) return '—';
    const parts = iso.split('-');
    if (parts.length !== 3) return iso;
    return `${Number(parts[0])}年${Number(parts[1])}月${Number(parts[2])}日`;
  }

  function timeLabel(iso) {
    if (!iso) return '—';
    const parsed = new Date(iso);
    if (Number.isNaN(parsed.getTime())) return iso.slice(11, 16);
    return `${pad2(parsed.getHours())}:${pad2(parsed.getMinutes())}`;
  }

  function showToast(title, detail = '', isError = false) {
    const toast = document.createElement('div');
    toast.className = `toast${isError ? ' is-error' : ''}`;
    const icon = document.createElement('span');
    icon.className = 'toast-icon';
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = isError ? '!' : '✓';
    const copy = document.createElement('div');
    copy.className = 'toast-copy';
    const strong = document.createElement('strong');
    strong.textContent = title;
    const span = document.createElement('span');
    span.textContent = detail;
    copy.append(strong, span);
    toast.append(icon, copy);
    els.toastRegion.append(toast);
    window.setTimeout(() => {
      toast.classList.add('is-leaving');
      window.setTimeout(() => toast.remove(), 220);
    }, isError ? 4200 : 3200);
  }

  function showFormAlert(message) {
    els.formAlert.textContent = message;
    els.formAlert.hidden = false;
  }

  function clearFormAlert() {
    els.formAlert.textContent = '';
    els.formAlert.hidden = true;
  }

  // ------------------------------------------------------------------
  // 选择项状态
  // ------------------------------------------------------------------
  function selectedValue(name) {
    const checked = els.form.querySelector(`input[name="${name}"]:checked`);
    return checked ? checked.value : '';
  }

  const ITEM_MARK = {
    '功率板': '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="5" width="24" height="22" rx="3"/><path d="M9 10h6v5H9zM20 10h3M20 14h3M9 21h14M9 25h9"/><path d="M4 10H1M4 16H1M4 22H1M28 10h3M28 16h3M28 22h3"/></svg>',
    'ACDC': '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="6" width="24" height="20" rx="3"/><path d="M8 16c1.7-3 3.3-3 5 0s3.3 3 5 0 3.3-3 5 0"/><path d="M10 11h3M10 21h3"/></svg>',
    'DCDC': '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="6" width="24" height="20" rx="3"/><path d="M9 12h8v8H9z"/><path d="M21 12h4M23 10l2 2-2 2M25 20h-4M23 18l-2 2 2 2"/></svg>',
    '中位机': '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="8" width="22" height="16" rx="3"/><rect x="11" y="13" width="10" height="6" rx="1.5"/><path d="M9 4v4M16 4v4M23 4v4M9 24v4M16 24v4M23 24v4"/></svg>',
  };
  const ITEM_MARK_PLAIN = '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><rect x="6" y="6" width="20" height="20" rx="4"/><path d="M11 16h10M16 11v10"/></svg>';

  function itemChoice(name, inputName, selected) {
    const label = document.createElement('label');
    label.className = 'choice item-choice';
    const input = document.createElement('input');
    input.type = 'radio';
    input.name = inputName;
    input.value = name;
    if (inputName === 'item') input.required = true;
    input.checked = name === selected;
    const icon = document.createElement('span');
    icon.className = 'item-icon';
    icon.setAttribute('aria-hidden', 'true');
    icon.innerHTML = ITEM_MARK[name] || ITEM_MARK_PLAIN;
    const copy = document.createElement('span');
    copy.className = 'item-copy';
    const title = document.createElement('span');
    title.className = 'item-name';
    title.textContent = name;
    copy.append(title);
    const chosenQty = inputName === 'item' ? state.qty : state.editQty;
    if (name === selected && chosenQty > 0) {
      const qty = document.createElement('span');
      qty.className = 'item-qty';
      qty.textContent = `×${chosenQty}`;
      copy.append(qty);
    }
    const mark = document.createElement('span');
    mark.className = 'choice-check';
    mark.setAttribute('aria-hidden', 'true');
    label.append(input, icon, copy, mark);
    return label;
  }

  function renderItemChoices() {
    const selected = selectedValue('item');
    els.itemGrid.replaceChildren(
      ...state.items.map((name) => itemChoice(name, 'item', selected))
    );
    updateSectionStates();
    syncCheckedClasses();
  }

  function renderEditItems(selected) {
    els.editItemGrid.replaceChildren(
      ...state.items.map((name) => itemChoice(name, 'edit-item', selected))
    );
  }

  function updateSectionStates() {
    const line = selectedValue('line');
    const item = selectedValue('item');
    els.lineState.textContent = line || '未选择';
    els.lineState.classList.toggle('is-set', Boolean(line));
    els.itemState.textContent = item
      ? (state.qty > 0 ? `${item} ×${state.qty}` : item)
      : '未选择';
    els.itemState.classList.toggle('is-set', Boolean(item));
  }

  function syncCheckedClasses() {
    els.form.querySelectorAll('.choice').forEach((choice) => {
      const input = choice.querySelector('input');
      choice.classList.toggle('is-selected', Boolean(input && input.checked));
    });
  }

  function clearFieldError(field) {
    if (field === 'line') {
      els.lineFieldset.classList.remove('has-error');
      els.lineError.hidden = true;
    } else if (field === 'item') {
      els.itemFieldset.classList.remove('has-error');
      els.itemError.hidden = true;
    } else if (field === 'reason') {
      els.reasonError.hidden = true;
      els.reason.closest('.form-section').classList.remove('has-error');
      els.reason.setAttribute('aria-invalid', 'false');
    }
  }

  function showFieldError(field, message) {
    if (field === 'line') {
      els.lineFieldset.classList.add('has-error');
      els.lineError.textContent = message;
      els.lineError.hidden = false;
    } else if (field === 'item') {
      els.itemFieldset.classList.add('has-error');
      els.itemError.textContent = message;
      els.itemError.hidden = false;
    } else if (field === 'reason') {
      els.reason.closest('.form-section').classList.add('has-error');
      els.reasonError.textContent = message;
      els.reasonError.hidden = false;
      els.reason.setAttribute('aria-invalid', 'true');
    }
  }

  // ------------------------------------------------------------------
  // 渲染
  // ------------------------------------------------------------------
  function setBarList(container, keys, counts, total, isItem = false) {
    const fragment = document.createDocumentFragment();
    keys.forEach((key) => {
      const count = Number(counts[key] || 0);
      const row = document.createElement('div');
      row.className = `bar-row${isItem ? ' is-item-row' : ''}`;
      const label = document.createElement('span');
      label.textContent = key;
      const track = document.createElement('span');
      track.className = 'bar-track';
      const fill = document.createElement('i');
      fill.className = `bar-fill${isItem ? ' is-item' : ''}`;
      const width = total > 0 && count > 0 ? Math.max(8, Math.round((count / total) * 100)) : 0;
      fill.style.width = `${width}%`;
      track.append(fill);
      const value = document.createElement('b');
      value.textContent = String(count);
      row.append(label, track, value);
      fragment.append(row);
    });
    container.replaceChildren(fragment);
  }

  function renderStats() {
    const stats = state.stats || { total: 0, by_line: {}, by_item: {}, last_updated: '' };
    const total = Number(stats.total || 0);
    els.totalCount.textContent = String(total);
    els.lineTotal.textContent = String(total);
    els.itemTotal.textContent = String(total);

    const maxScale = Math.max(12, total);
    const ring = total > 0 ? Math.max(18, Math.round((total / maxScale) * 360)) : 0;
    els.countRing.style.setProperty('--ring', `${ring}deg`);

    els.overviewTitle.textContent = state.date === state.today ? '今日记录' : '历史记录';
    els.overviewDate.textContent =
      dateLabel(state.date);

    setBarList(els.lineBars, state.lines, stats.by_line || {}, total);
    setBarList(els.itemBars, state.items, stats.by_item || {}, total, true);

    els.recordsCount.textContent = String(total);
    if (stats.last_updated) {
      els.updatedAt.textContent = `更新 ${timeLabel(stats.last_updated)}`;
      els.lastArchive.textContent = `${state.date} ${timeLabel(stats.last_updated)}`;
    } else {
      els.updatedAt.textContent = '暂无更新';
      els.lastArchive.textContent = '当日暂无记录';
    }

    els.downloadCsv.href = `/api/daily/${state.date}.csv`;
    els.downloadMd.href = `/api/daily/${state.date}.md`;
    els.datePicker.value = state.date;
    els.datePicker.max = state.today;
    els.historyToday.hidden = state.date === state.today;
  }

  function isoShift(iso, days) {
    const parts = iso.split('-').map(Number);
    const date = new Date(parts[0], parts[1] - 1, parts[2]);
    date.setDate(date.getDate() + days);
    return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
  }

  function renderChart() {
    const end = state.today || state.date;
    if (!end || !els.statChart) return;
    const counts = new Map((state.dates || []).map((row) => [row.date, Number(row.count || 0)]));
    const days = [];
    for (let offset = 13; offset >= 0; offset -= 1) {
      const date = isoShift(end, -offset);
      days.push({ date, count: counts.get(date) || 0 });
    }
    const max = days.reduce((peak, day) => Math.max(peak, day.count), 0);
    els.statChart.replaceChildren();
    if (max === 0) {
      const empty = document.createElement('p');
      empty.className = 'stat-chart-empty';
      empty.textContent = '近 14 天还没有记录';
      els.statChart.append(empty);
      return;
    }
    const fragment = document.createDocumentFragment();
    days.forEach((day) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'stat-col';
      if (day.date === state.date) button.classList.add('is-current');
      button.title = `${day.date} · ${day.count} 条`;
      button.setAttribute('aria-label', `${day.date}，${day.count} 条`);

      const value = document.createElement('span');
      value.className = 'stat-value';
      value.textContent = day.count > 0 ? String(day.count) : '';

      const bar = document.createElement('span');
      bar.className = 'stat-bar';
      const height = day.count > 0 ? Math.max(8, Math.round((day.count / max) * 78)) : 4;
      bar.style.height = `${height}px`;

      const label = document.createElement('span');
      label.className = 'stat-label';
      label.textContent = day.date.slice(5);

      button.append(value, bar, label);
      button.addEventListener('click', () => loadDay(day.date));
      fragment.append(button);
    });
    els.statChart.append(fragment);
  }

  function renderHistoryList() {
    const dates = state.dates || [];
    els.historyList.replaceChildren();
    els.historyEmpty.hidden = dates.length > 0;
    const fragment = document.createDocumentFragment();
    dates.forEach((row) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'history-row';
      if (row.date === state.date) button.classList.add('is-current');
      const label = document.createElement('span');
      label.textContent = dateLabel(row.date);
      const count = document.createElement('b');
      count.textContent = `${row.count} 条`;
      button.append(label, count);
      button.addEventListener('click', () => {
        if (els.historyDialog.open) els.historyDialog.close();
        loadDay(row.date);
      });
      fragment.append(button);
    });
    els.historyList.append(fragment);
  }

  async function openHistory() {
    try {
      const data = await api('/api/dates');
      state.dates = data.dates || [];
      renderChart();
    } catch (error) {
      showToast('读取失败', error.message, true);
    }
    renderHistoryList();
    if (els.historyDialog.open) els.historyDialog.close();
    els.historyDialog.showModal();
  }

  function renderRecords() {
    const records = state.records || [];
    els.recordList.replaceChildren();
    els.recordList.hidden = records.length === 0;
    els.emptyState.hidden = records.length > 0;

    if (!records.length) {
      const isToday = state.date === state.today;
      const title = els.emptyState.querySelector('p');
      const hint = els.emptyState.querySelector('span');
      if (title) title.textContent = isToday ? '还没有记录' : '该日期暂无记录';
      if (hint) {
        hint.textContent = isToday
          ? '提交第一条故障信息后会显示在这里'
          : '点「回到今天」看当天记录';
      }
      return;
    }

    const fragment = document.createDocumentFragment();
    records.forEach((record, index) => {
      const item = document.createElement('li');
      item.className = 'record-item';
      if (index === 0) item.classList.add('is-new');
      item.dataset.id = String(record.id);
      item.title = record.fault_reason;

      const top = document.createElement('div');
      top.className = 'record-top';

      const line = document.createElement('span');
      line.className = 'line-badge';
      line.textContent = record.line;

      const kind = document.createElement('span');
      kind.className = 'item-badge';
      const qty = Number(record.qty) > 0 ? Number(record.qty) : 1;
      kind.textContent = `${record.item} ×${qty}`;

      const time = document.createElement('time');
      time.className = 'record-time';
      time.dateTime = record.created_at;
      time.textContent = timeLabel(record.created_at);

      top.append(line, kind, time);

      const reason = document.createElement('p');
      reason.className = 'record-reason';
      reason.textContent = record.fault_reason;

      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'record-toggle';
      toggle.textContent = '展开';

      const actions = document.createElement('div');
      actions.className = 'record-actions';

      const editBtn = document.createElement('button');
      editBtn.type = 'button';
      editBtn.className = 'record-action';
      editBtn.textContent = '修改';
      editBtn.addEventListener('click', () => openEdit(record));

      const deleteBtn = document.createElement('button');
      deleteBtn.type = 'button';
      deleteBtn.className = 'record-action is-danger';
      deleteBtn.textContent = '删除';
      deleteBtn.addEventListener('click', () => removeRecord(record));

      actions.append(editBtn, deleteBtn);
      item.append(top, reason, actions);
      fragment.append(item);

      // 在挂载后判断是否被截断，被截断的记录提供展开按钮
      window.requestAnimationFrame(() => {
        if (reason.scrollHeight > reason.clientHeight + 2) {
          item.insertBefore(toggle, actions);
          toggle.addEventListener('click', (event) => {
            event.stopPropagation();
            const expanded = item.classList.toggle('is-expanded');
            toggle.textContent = expanded ? '收起' : '展开';
          });
        }
      });
    });
    els.recordList.append(fragment);
  }

  function renderSummary() {
    const summary = state.summary;
    const total = state.stats ? Number(state.stats.total || 0) : 0;

    if (summary && summary.summary) {
      els.summaryBox.hidden = false;
      els.summaryEmpty.hidden = true;
      els.summaryText.textContent = summary.summary;
      const kind = summary.auto ? '自动汇总' : '手动汇总';
      const updated = (summary.updated_at || '').slice(0, 16).replace('T', ' ');
      els.summaryMeta.textContent = `${kind} · 更新于 ${updated} · 共 ${summary.total} 条`;
      els.summaryCopy.disabled = false;
      els.summaryGenerate.textContent = '重新汇总';
    } else {
      els.summaryBox.hidden = true;
      els.summaryEmpty.hidden = false;
      els.summaryEmpty.textContent = total > 0
        ? '还没汇总。有记录就可以点「立即汇总」。'
        : '这天没有记录。';
      els.summaryCopy.disabled = true;
      els.summaryGenerate.textContent = '立即汇总';
    }

    els.summaryGenerate.disabled = total <= 0 || state.summaryBusy;
  }

  function renderAll() {
    renderStats();
    renderChart();
    renderRecords();
    renderSummary();
    updateSectionStates();
    syncCheckedClasses();
  }

  // ------------------------------------------------------------------
  // 修改 / 删除 / 汇总
  // ------------------------------------------------------------------
  function showEditError(message) {
    els.editError.textContent = message;
    els.editError.hidden = false;
  }

  function closeEdit() {
    if (els.editDialog.open) els.editDialog.close();
    state.editingId = null;
  }

  function openEdit(record) {
    state.editingId = record.id;

    els.editForm.querySelectorAll('input[name="edit-line"]').forEach((input) => {
      input.checked = input.value === record.line;
    });
    state.editQty = Number(record.qty) > 0 ? Number(record.qty) : 1;
    renderEditItems(record.item);
    els.editReason.value = record.fault_reason;
    els.editMeta.textContent = `${dateLabel(record.work_date)} · ${record.time} · 记录 #${record.id}`;
    els.editError.hidden = true;
    els.editError.textContent = '';

    if (els.editDialog.open) els.editDialog.close();
    els.editDialog.showModal();
    window.setTimeout(() => els.editReason.focus(), 40);
  }

  async function submitEdit(event) {
    event.preventDefault();
    const recordId = state.editingId;
    if (!recordId) return;

    const lineInput = els.editForm.querySelector('input[name="edit-line"]:checked');
    const itemInput = els.editForm.querySelector('input[name="edit-item"]:checked');
    const line = lineInput ? lineInput.value : '';
    const item = itemInput ? itemInput.value : '';
    const reason = els.editReason.value.trim();

    if (!line || !item || !state.editQty || !reason) {
      showEditError(
        !line ? '请选择 Line' : !item ? '请选择维修物品' : !state.editQty ? '请选择数量' : '请填写故障原因'
      );
      return;
    }

    els.editSave.disabled = true;
    els.editSave.textContent = '保存中…';
    els.editError.hidden = true;

    try {
      const data = await api(`/api/records/${recordId}/update`, {
        method: 'POST',
        body: JSON.stringify({ line, item, qty: state.editQty, fault_reason: reason }),
      });
      closeEdit();
      await loadDay(state.date, { silent: true });
      showToast('记录已修改', `#${data.record.id} · ${data.record.line} / ${data.record.item}`);
    } catch (error) {
      showEditError(error.message);
    } finally {
      els.editSave.disabled = false;
      els.editSave.textContent = '保存修改';
    }
  }

  async function removeRecord(record) {
    const ok = window.confirm(
      `确定删除这条记录吗？\n\n${record.line} / ${record.item}\n${record.fault_reason}`
    );
    if (!ok) return;
    try {
      await api(`/api/records/${record.id}/delete`, { method: 'POST' });
      await loadDay(state.date, { silent: true });
      showToast('记录已删除', `#${record.id} · ${record.line} / ${record.item}`);
    } catch (error) {
      showToast('删除失败', error.message, true);
    }
  }

  async function generateSummary() {
    if (state.summaryBusy) return;
    state.summaryBusy = true;
    els.summaryGenerate.disabled = true;
    els.summaryGenerate.textContent = '生成中…';
    try {
      const data = await api('/api/summary', {
        method: 'POST',
        body: JSON.stringify({ date: state.date }),
      });
      state.summary = data.summary;
      renderSummary();
      showToast('汇总好了', `${state.date} · ${data.summary.total} 条`);
    } catch (error) {
      showToast('汇总失败', error.message, true);
    } finally {
      state.summaryBusy = false;
      renderSummary();
    }
  }

  async function copySummary() {
    const text = state.summary && state.summary.summary;
    if (!text) return;
    let copied = false;
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(text);
        copied = true;
      } catch (error) {
        copied = fallbackCopy(text);
      }
    } else {
      copied = fallbackCopy(text);
    }
    if (copied) {
      showToast('已复制', '贴到日报里就行');
    } else {
      showToast('复制失败', '请手动选择汇总文本复制', true);
    }
  }

  // ------------------------------------------------------------------
  // 数据加载
  // ------------------------------------------------------------------
  async function loadDay(workDate, options = {}) {
    if (state.loading) return;
    state.loading = true;
    els.refreshBtn.classList.add('is-loading');
    try {
      const target = workDate || state.date || state.today;
      const previousToday = state.today;
      const wasViewingToday = state.date === state.today;
      const data = await api(`/api/records?date=${encodeURIComponent(target)}&limit=200`);
      state.today = data.today;
      state.date = data.date;
      state.stats = data.stats;
      state.records = data.records;
      state.summary = data.summary || null;
      if (Array.isArray(data.dates)) {
        state.dates = data.dates;
      } else {
        try {
          const datesData = await api('/api/dates');
          state.dates = datesData.dates || state.dates;
        } catch (error) {
          // 旧进程没有 dates 字段时，统计图沿用上一次的日期列表
        }
      }
      // 跨过零点时，原本停留在“今天”的页面自动切到新的一天；
      // 用户主动查看历史日期时不做跳转。
      if (wasViewingToday && target === previousToday && data.date !== data.today) {
        state.loading = false;
        return loadDay(data.today, options);
      }
      renderAll();
      setLive(true);
      if (!options.silent) clearFormAlert();
    } catch (error) {
      setLive(false);
      if (!options.silent) {
        showToast('读取失败', error.message, true);
      }
    } finally {
      state.loading = false;
      els.refreshBtn.classList.remove('is-loading');
    }
  }

  async function bootstrap() {
    try {
      const data = await api('/api/bootstrap');
      state.today = data.today;
      state.date = data.date;
      state.lines = data.lines || state.lines;
      state.items = data.items || state.items;
      renderItemChoices();
      state.stats = data.stats;
      state.records = data.records;
      state.dates = data.dates || [];
      state.summary = data.summary || null;
      renderAll();
      setLive(true);
      els.datePicker.min = '2020-01-01';
      els.datePicker.max = state.today;
    } catch (error) {
      setLive(false);
      els.emptyState.querySelector('p').textContent = '暂时无法连接服务器';
      showToast('无法加载数据', error.message, true);
      window.setTimeout(bootstrap, 4000);
    }
  }

  // ------------------------------------------------------------------
  // 提交
  // ------------------------------------------------------------------
  async function submitRecord(event) {
    event.preventDefault();
    if (state.submitting) return;
    clearFormAlert();

    const line = selectedValue('line');
    const item = selectedValue('item');
    const reason = els.reason.value.trim();
    let valid = true;

    ['line', 'item', 'reason'].forEach(clearFieldError);

    if (!line) {
      showFieldError('line', '请选择一条 Line');
      valid = false;
    }
    if (!item || !state.qty) {
      showFieldError('item', item ? '请选择数量' : '请选择维修物品');
      valid = false;
    }
    if (!reason) {
      showFieldError('reason', '请填写故障原因');
      valid = false;
    }

    if (!valid) {
      if (!line) {
        els.form.querySelector('input[name="line"]').focus();
      } else if (!item) {
        els.form.querySelector('input[name="item"]').focus();
      } else {
        els.reason.focus();
      }
      showFormAlert('还有必填项未完成，请检查后再保存。');
      return;
    }

    state.submitting = true;
    els.submitBtn.disabled = true;
    els.submitText.textContent = '保存中…';

    try {
      const data = await api('/api/records', {
        method: 'POST',
        body: JSON.stringify({ line, item, qty: state.qty, fault_reason: reason }),
      });
      state.date = data.today;
      state.today = data.today;
      state.stats = data.stats;
      els.reason.value = '';
      els.reason.dispatchEvent(new Event('input'));
      await loadDay(data.today, { silent: true });
      showToast(
        '记录已保存',
        `${data.record.line} / ${data.record.item} ×${data.record.qty || state.qty} · 今日第 ${data.stats.total} 条`
      );
      els.reason.focus();
    } catch (error) {
      showFormAlert(error.message);
      showToast('保存失败', error.message, true);
    } finally {
      state.submitting = false;
      els.submitBtn.disabled = false;
      els.submitText.textContent = '保存记录';
    }
  }

  function closeQty() {
    if (els.qtyDialog.open) els.qtyDialog.close();
  }

  function paintQty(value) {
    const current = Number(value);
    els.qtyPresets.querySelectorAll('button').forEach((button) => {
      button.classList.toggle('is-selected', Number(button.dataset.qty) === current);
    });
  }

  function showQtyError(message) {
    els.qtyError.textContent = message;
    els.qtyError.hidden = false;
  }

  function openQty(name, mode) {
    state.qtyItem = name;
    state.qtyMode = mode;
    els.qtyItemName.textContent = name;
    const current = mode === 'edit'
      ? (els.editForm.querySelector('input[name="edit-item"]:checked')?.value === name ? state.editQty : 0)
      : (selectedValue('item') === name ? state.qty : 0);
    els.qtyCustom.value = current > 5 ? String(current) : '';
    paintQty(current >= 1 && current <= 5 ? current : 0);
    els.qtyError.hidden = true;
    if (!els.qtyDialog.open) els.qtyDialog.showModal();
    if (current > 5) els.qtyCustom.focus();
  }

  function applyQty(raw) {
    const text = String(raw ?? '').trim();
    if (!/^\d{1,3}$/.test(text)) {
      showQtyError('数量请填 1 到 999 的整数');
      els.qtyCustom.focus();
      return;
    }
    const qty = Number(text);
    if (qty < 1 || qty > 999) {
      showQtyError('数量请填 1 到 999 的整数');
      return;
    }
    const name = state.qtyItem;
    if (state.qtyMode === 'edit') {
      state.editQty = qty;
      const input = els.editForm.querySelector(
        `input[name="edit-item"][value="${CSS.escape(name)}"]`
      );
      if (input) input.checked = true;
      renderEditItems(name);
    } else {
      state.qty = qty;
      const input = els.form.querySelector(
        `input[name="item"][value="${CSS.escape(name)}"]`
      );
      if (input) input.checked = true;
      clearFieldError('item');
      renderItemChoices();
      syncCheckedClasses();
    }
    closeQty();
  }

  function bindItemQty(container, inputName, mode) {
    container.addEventListener('click', (event) => {
      const label = event.target.closest('.item-choice');
      if (!label || !container.contains(label)) return;
      const input = label.querySelector(`input[name="${inputName}"]`);
      if (!input) return;
      event.preventDefault();
      openQty(input.value, mode);
    });
  }

  function resetForm() {
    els.form.reset();
    state.qty = 0;
    ['line', 'item', 'reason'].forEach(clearFieldError);
    renderItemChoices();
    clearFormAlert();
    els.charCount.textContent = '0 / 1000';
    updateSectionStates();
    syncCheckedClasses();
    els.form.querySelector('input[name="line"]').focus({ preventScroll: true });
  }

  // ------------------------------------------------------------------
  // 复制每日摘要
  // ------------------------------------------------------------------
  function fallbackCopy(text) {
    const helper = document.createElement('textarea');
    helper.value = text;
    helper.setAttribute('readonly', '');
    helper.style.position = 'fixed';
    helper.style.top = '-1000px';
    helper.style.opacity = '0';
    document.body.append(helper);
    helper.select();
    let copied = false;
    try {
      copied = document.execCommand('copy');
    } catch (error) {
      copied = false;
    }
    helper.remove();
    return copied;
  }

  async function copyDigest() {
    const original = els.copyDigest.innerHTML;
    els.copyDigest.disabled = true;
    try {
      const response = await fetch(`/api/daily/${encodeURIComponent(state.date)}.md`, {
        cache: 'no-store',
      });
      if (!response.ok) throw new Error('摘要生成失败');
      const text = await response.text();
      let copied = false;
      if (navigator.clipboard && window.isSecureContext) {
        try {
          await navigator.clipboard.writeText(text);
          copied = true;
        } catch (error) {
          copied = fallbackCopy(text);
        }
      } else {
        copied = fallbackCopy(text);
      }
      if (copied) {
        showToast('已复制', state.date);
      } else {
        window.open(`/api/daily/${encodeURIComponent(state.date)}.md`, '_blank', 'noopener');
        showToast('已打开摘要文件', '浏览器未允许自动复制，请手动复制', true);
      }
    } catch (error) {
      showToast('复制失败', error.message, true);
    } finally {
      els.copyDigest.innerHTML = original;
      els.copyDigest.disabled = false;
    }
  }

  // ------------------------------------------------------------------
  // 事件绑定
  // ------------------------------------------------------------------
  function bindEvents() {
    els.form.addEventListener('submit', submitRecord);
    els.resetBtn.addEventListener('click', resetForm);

    els.form.querySelectorAll('input[name="line"]').forEach((input) => {
      input.addEventListener('change', () => {
        clearFieldError('line');
        updateSectionStates();
        syncCheckedClasses();
        clearFormAlert();
      });
    });
    for (let qty = 1; qty <= 5; qty += 1) {
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.qty = String(qty);
      button.textContent = String(qty);
      button.addEventListener('click', () => applyQty(qty));
      els.qtyPresets.append(button);
    }
    bindItemQty(els.itemFieldset, 'item', 'form');
    bindItemQty(els.editItemGrid, 'edit-item', 'edit');
    els.qtyForm.addEventListener('submit', (event) => {
      event.preventDefault();
      applyQty(els.qtyCustom.value);
    });
    els.qtyCustom.addEventListener('input', () => {
      els.qtyCustom.value = els.qtyCustom.value.replace(/\D/g, '').slice(0, 3);
      paintQty(els.qtyCustom.value);
      els.qtyError.hidden = true;
    });
    els.qtyClose.addEventListener('click', closeQty);
    els.qtyDialog.addEventListener('click', (event) => {
      if (event.target === els.qtyDialog) closeQty();
    });

    els.itemFieldset.addEventListener('change', (event) => {
      if (event.target.name !== 'item') return;
      clearFieldError('item');
      updateSectionStates();
      syncCheckedClasses();
      clearFormAlert();
    });

    els.itemAddBtn.addEventListener('click', () => {
      els.itemAdd.hidden = !els.itemAdd.hidden;
      if (!els.itemAdd.hidden) els.itemAddInput.focus();
    });

    async function saveCustomItem() {
      const name = els.itemAddInput.value.trim();
      if (!name) {
        els.itemAddInput.focus();
        return;
      }
      els.itemAddSave.disabled = true;
      try {
        const data = await api('/api/items', {
          method: 'POST',
          body: JSON.stringify({ name }),
        });
        state.items = data.items;
        renderItemChoices();
        const picked = els.form.querySelector(`input[name="item"][value="${CSS.escape(data.name)}"]`);
        if (picked) picked.checked = true;
        updateSectionStates();
        syncCheckedClasses();
        els.itemAddInput.value = '';
        els.itemAdd.hidden = true;
        showToast('已添加', data.name);
      } catch (error) {
        showToast('没加上', error.message, true);
      } finally {
        els.itemAddSave.disabled = false;
      }
    }

    els.itemAddSave.addEventListener('click', saveCustomItem);
    els.itemAddInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        saveCustomItem();
      }
    });

    els.reason.addEventListener('input', () => {
      const length = els.reason.value.length;
      els.charCount.textContent = `${length} / 1000`;
      clearFieldError('reason');
      clearFormAlert();
    });

    els.reason.addEventListener('keydown', (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
        event.preventDefault();
        els.form.requestSubmit();
      }
    });

    els.form.querySelectorAll('.choice').forEach((choice) => {
      const input = choice.querySelector('input');
      input.addEventListener('focus', () => choice.classList.add('is-focus'));
      input.addEventListener('blur', () => choice.classList.remove('is-focus'));
    });

    els.refreshBtn.addEventListener('click', () => loadDay(state.date));
    els.dateLoad.addEventListener('click', () => {
      const value = els.datePicker.value;
      if (!value) {
        showToast('请选择日期', '先选择要查看的日期', true);
        return;
      }
      loadDay(value);
    });
    els.datePicker.addEventListener('change', () => {
      if (els.datePicker.value) loadDay(els.datePicker.value);
    });
    els.dateToday.addEventListener('click', () => loadDay(state.today));
    els.historyOpen.addEventListener('click', openHistory);
    els.historyToday.addEventListener('click', () => loadDay(state.today));
    els.historyClose.addEventListener('click', () => {
      if (els.historyDialog.open) els.historyDialog.close();
    });
    els.historyDialog.addEventListener('click', (event) => {
      if (event.target === els.historyDialog && els.historyDialog.open) {
        els.historyDialog.close();
      }
    });
    els.copyDigest.addEventListener('click', copyDigest);
    els.summaryGenerate.addEventListener('click', generateSummary);
    els.summaryCopy.addEventListener('click', copySummary);
    els.editForm.addEventListener('submit', submitEdit);
    els.editCancel.addEventListener('click', closeEdit);
    els.editClose.addEventListener('click', closeEdit);
    els.editDialog.addEventListener('close', () => {
      state.editingId = null;
    });
    els.editDialog.addEventListener('click', (event) => {
      if (event.target === els.editDialog) closeEdit();
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') clearFormAlert();
    });

    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible' && state.date === state.today) {
        loadDay(state.today, { silent: true });
      }
    });
  }

  // ------------------------------------------------------------------
  // 启动
  // ------------------------------------------------------------------
  function startAutoRefresh() {
    window.setInterval(() => {
      if (document.visibilityState !== 'visible') return;
      if (state.submitting || state.loading) return;
      if (state.date !== state.today) return;
      loadDay(state.today, { silent: true });
    }, 60000);
  }

  let clockTimer = 0;
  const scheduleClock = () => {
    tickClock();
    clockTimer = window.setTimeout(scheduleClock, 1000 - (Date.now() % 1000));
  };
  scheduleClock();
  document.addEventListener('visibilitychange', () => {
    window.clearTimeout(clockTimer);
    if (!document.hidden) scheduleClock();
  });
  bindEvents();
  bootstrap();
  startAutoRefresh();
})();
