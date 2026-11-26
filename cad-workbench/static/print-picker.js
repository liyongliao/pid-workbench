(() => {
  const dialog = $('#sheetPrintDialog'), manual = new Set();
  let matches = [], current, version, loadingError, requestNumber = 0;
  const scope = () => dialog.querySelector('input[name="printScope"]:checked').value;
  function selection() {
    if (scope() === 'manual') return S.catalog.filter(row => manual.has(row.id));
    return scope() === 'matches' ? matches : current ? [current] : [];
  }
  function update() {
    const rows = selection();
    $('#manualPrintPicker').hidden = scope() !== 'manual';
    $('#sheetPrintStatus').textContent = scope() === 'matches' && loadingError ? loadingError :
      (version === 'original' ? '原文图纸' : '中文图纸') + ' · ' + rows.length + ' 张';
    $('#preparePrint').disabled = !rows.length;
  }
  function showManual() {
    const q = $('#manualPrintQuery').value.trim().toLowerCase();
    const list = $('#manualPrintList'); list.replaceChildren();
    for (const row of S.catalog) {
      if (![row.code,row.title,row.platform].join(' ').toLowerCase().includes(q)) continue;
      const label = document.createElement('label'), input = document.createElement('input');
      input.type = 'checkbox'; input.value = row.id; input.checked = manual.has(row.id);
      label.append(input, shortCode(row.code) + ' · ' + row.title); list.append(label);
    }
    if (!list.childElementCount) list.textContent = '未找到匹配图纸';
  }
  async function open(initial) {
    const token = ++requestNumber, {query,platform,team,listFilter,preferences} = S;
    current = S.drawing; version = S.mode; manual.clear(); matches = []; loadingError = '';
    $('#currentPrintName').textContent = current ? shortCode(current.code) : '尚未打开';
    dialog.querySelector('[value="current"]').disabled = !current;
    dialog.querySelector('[value="'+initial+'"]').checked = true;
    $('#manualPrintQuery').value = ''; showManual(); update();
    $('#matchPrintCount').textContent = '正在读取…';
    (document.fullscreenElement || document.body).append(dialog); dialog.showModal();
    try {
      let rows = S.catalog;
      if (query) {
        const result = await api('/api/search?' + new URLSearchParams({q:query,platform,team:team||''}));
        if (result.total > result.drawings.length) throw Error('检索结果不完整，请重新载入工作台服务');
        rows = result.drawings;
      }
      if (token !== requestNumber) return;
      rows = rows.filter(r => (!platform || r.platform === platform) && (!team || r.team === team));
      matches = preferences ? preferences.select(rows,listFilter) : rows;
      $('#matchPrintCount').textContent = matches.length + ' 张';
    } catch (error) {
      if (token !== requestNumber) return;
      loadingError = error.message; $('#matchPrintCount').textContent = '读取失败';
    }
    update();
  }
  $('#printDrawings').onclick = () => open('current');
  $('#printResults').onclick = () => open('matches');
  $('#sheetPrintClose').onclick = () => dialog.close();
  dialog.querySelector('fieldset').onchange = update;
  $('#manualPrintQuery').oninput = showManual;
  $('#manualPrintList').onchange = ({target}) => {
    if (target.checked) manual.add(target.value); else manual.delete(target.value);
    update();
  };
  $('#preparePrint').onclick = () => {
    const rows = selection().map(r => ({id:r.id,code:shortCode(r.code),title:r.title,
      asset:r.id === current?.id ? current.assets?.[version] : r.assets?.[version]}));
    if (!rows.length) return;
    const key = 'pid-print-' + Array.from(crypto.getRandomValues(new Uint32Array(4))).join('-');
    try {
      // A new same-origin tab inherits a snapshot of sessionStorage when opened.
      sessionStorage.setItem(key,JSON.stringify({version,rows}));
      const preview = window.open('/print-sheets.html#' + key,'_blank');
      if (!preview) throw Error('请允许打开打印预览窗口，再点一次打印预览');
      preview.opener = null; dialog.close();
    } catch (error) { $('#sheetPrintStatus').textContent = error.message; }
    finally { sessionStorage.removeItem(key); }
  };
})();
