// The Excel exporter preserves the Wingdings black circle as a lowercase "l".
const CauseMatrix = (() => {
  const isAction = mark => ['l','●','•','.'].includes(String(mark ?? '').trim());
  const labels = {HH:'高高',LL:'低低',H:'高',L:'低'};
  function shortTag(tag) {
    return String(tag || '').trim().toUpperCase().replace(/^(?:CEPD?|WHP[A-Z]|WP[A-Z]|PRP)-/,'');
  }
  function alarm(tag) {
    const match = /^([A-Z]+)([SA])(HH|LL|H|L)-?(\d+[A-Z]?)$/.exec(shortTag(tag));
    return match && {quantity:match[1],function:match[2],limit:match[3],loop:match[4]};
  }
  function signalName(cause) {
    const signal = alarm(cause.tag);
    return signal ? labels[signal.limit] + ' ' + signal.limit + ' · ' + cause.tag : cause.tag || cause.name;
  }
  function read(raw) {
    const counts = new Map();
    let actionCount = 0;
    for (const a of raw.actions) {
      if (!isAction(a.mark)) continue;
      counts.set(a.cause,(counts.get(a.cause) || 0) + 1);
      actionCount++;
    }
    return {...raw, actionCount, causes:raw.causes.map(c => ({...c,count:counts.get(c.id) || 0}))};
  }
  function related(rows, direct, tag, platform) {
    // Only extend an explicit transmitter match to a sibling alarm in its own loop.
    const ids = new Set(direct.map(c => c.id));
    const transmitter = /^([A-Z]+?)I?T-?(\d+[A-Z]?)$/.exec(shortTag(tag));
    if (transmitter) {
      const anchors = rows.filter(c => ids.has(c.id)).map(c => ({row:c,signal:alarm(c.tag)})).filter(({row,signal}) =>
        row.platform === platform && signal?.quantity === transmitter[1] && signal.loop === transmitter[2]);
      for (const c of rows) {
        const signal = alarm(c.tag);
        if (c.platform !== platform || !signal) continue;
        if (anchors.some(({row,signal:a}) => row.drawing === c.drawing && a.quantity === signal.quantity &&
          a.function === signal.function && a.loop === signal.loop &&
          (row.drawing || Math.abs(row.id-c.id) === 1))) ids.add(c.id);
      }
    }
    return rows.filter(c => ids.has(c.id));
  }
  return {read,related,signalName,isAction};
})();
if (typeof module !== 'undefined' && module.exports) module.exports = CauseMatrix;
