let current = "et";
window.__metoodikaLang = current;

export function getLang() {
  return current;
}

export function setLang(next) {
  current = next;
  window.__metoodikaLang = next;
  document.documentElement.lang = next;
}
