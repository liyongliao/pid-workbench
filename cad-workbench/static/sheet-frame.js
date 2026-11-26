// Paper-space border shared by the drawing viewport and print composition.
function cadSheetFrame(svg) {
  const box = svg.viewBox.baseVal;
  let left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
  for (const element of svg.querySelectorAll('[data-layer="BORD"]')) {
    const b = element.getBBox();
    left = Math.min(left, b.x);
    top = Math.min(top, b.y);
    right = Math.max(right, b.x + b.width);
    bottom = Math.max(bottom, b.y + b.height);
  }
  const width = right - left, height = bottom - top, aspect = width / height;
  return aspect > 1.2 && aspect < 1.8 && width > box.width * .2 && height > box.height * .5
    ? [left, top, width, height] : null;
}
