/* Local navigation preferences store IDs only, isolated by library and role. */
class LibraryPreferences {
  constructor(storage, key) { this.storage = storage; this.key = key; this.reload(); }
  clean(value, limit) {
    if (!Array.isArray(value)) return [];
    return [...new Set(value.filter(id => typeof id === 'string' && /^[A-Za-z0-9_-]{1,80}$/.test(id)))].slice(0, limit);
  }
  reload() {
    try { const data = JSON.parse(this.storage.getItem(this.key) || '{}'); this.favorites = this.clean(data?.favorites, 100); this.recent = this.clean(data?.recent, 20); }
    catch { this.favorites = []; this.recent = []; }
  }
  save() {
    try { this.storage.setItem(this.key, JSON.stringify({version: 1, favorites: this.favorites, recent: this.recent})); return true; }
    catch { return false; }
  }
  has(id) { return this.favorites.includes(id); }
  toggle(id) {
    if (!this.clean([id], 1).length) return false;
    if (this.has(id)) this.favorites = this.favorites.filter(item => item !== id);
    else this.favorites = [id, ...this.favorites].slice(0, 100);
    this.save(); return this.has(id);
  }
  opened(id) { this.recent = this.clean([id, ...this.recent], 20); this.save(); }
  select(rows, filter) {
    if (filter === 'favorites') return rows.filter(row => this.has(row.id));
    if (filter === 'recent') { const map = new Map(rows.map(row => [row.id, row])); return this.recent.flatMap(id => map.has(id) ? [map.get(id)] : []); }
    return rows;
  }
}
if (typeof module !== 'undefined' && module.exports) module.exports = LibraryPreferences;
