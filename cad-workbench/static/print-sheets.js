(() => {
  const status = document.querySelector('#status'), printButton = document.querySelector('#print');
  const retry = document.querySelector('#retry'), pages = document.querySelector('main');
  async function compose(row, version) {
    const asset = row.asset ? '?asset=' + encodeURIComponent(row.asset) : '';
    const response = await fetch('/output/' + encodeURIComponent(row.id) + '/' + version + '.svg' + asset);
    if (!response.ok) throw Error(response.status === 401 ? '登录已过期' : '无法读取矢量图纸');
    const svgURL = URL.createObjectURL(new Blob([await response.blob()],{type:'image/svg+xml'}));
    const frame = document.createElement('iframe');
    frame.className = 'measure'; frame.setAttribute('sandbox','allow-same-origin');
    frame.setAttribute('aria-hidden','true'); frame.tabIndex = -1;
    try {
      await new Promise((resolve,reject) => {
        frame.onload = resolve; frame.onerror = () => reject(Error('矢量图纸读取失败'));
        frame.src = svgURL; document.body.append(frame);
      });
      const svg = frame.contentDocument?.documentElement;
      if (svg?.localName !== 'svg') throw Error('矢量文件格式异常');
      const border = cadSheetFrame(svg);
      if (border) {
        const [x,y,w,h] = border, pad = Math.max(w,h) * .002;
        svg.setAttribute('viewBox',[x-pad,y-pad,w+2*pad,h+2*pad].join(' '));
      }
      const view = svg.viewBox.baseVal;
      if (!(view.width > 0 && view.height > 0)) throw Error('缺少图纸边界');
      const scale = 1600 / Math.max(view.width,view.height);
      svg.setAttribute('width',String(view.width * scale)); svg.setAttribute('height',String(view.height * scale));
      svg.setAttribute('preserveAspectRatio','xMidYMid meet');
      const source = new XMLSerializer().serializeToString(svg);
      const url = URL.createObjectURL(new Blob([source],{type:'image/svg+xml'}));
      const img = new Image(); img.alt = row.code + ' · ' + row.title;
      img.src = url;
      try { await img.decode(); }
      catch { URL.revokeObjectURL(url); throw Error('图纸预览生成失败'); }
      const page = document.createElement('article'); page.className = 'sheet';
      page.append(img); pages.append(page);
      // The image URL stays valid for repeated print jobs and is released on tab close.
    } finally { frame.remove(); URL.revokeObjectURL(svgURL); }
  }
  let completed = 0;
  async function prepare() {
    retry.hidden = true;
    try {
      const job = JSON.parse(sessionStorage.getItem(location.hash.slice(1)));
      if (!job?.rows?.length || !['original','chinese'].includes(job.version)) throw Error('请从 PID 联动工作区选择图纸后打开预览');
      document.title = job.rows.length === 1 ? job.rows[0].code + ' · 打印' : 'PID 图纸 · ' + job.rows.length + ' 张';
      for (;completed < job.rows.length;completed++) {
        const row = job.rows[completed];
        status.textContent = '正在准备 ' + (completed+1) + ' / ' + job.rows.length + ' · ' + row.code;
        try { await compose(row,job.version); } catch (error) { throw Error(row.code + ' · ' + error.message); }
      }
      status.textContent = (job.version === 'original' ? '原文图纸' : '中文图纸') + ' · 共 ' + completed + ' 张';
      document.body.classList.add('ready'); printButton.disabled = false;
      window.print();
    } catch (error) { status.textContent = error.message; retry.hidden = false; }
  }
  retry.onclick = prepare; printButton.onclick = () => window.print(); prepare();
})();
