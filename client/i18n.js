const LANGUAGE_KEY = 'tmb-language';
const LANGUAGES = new Set(['ca', 'es', 'en']);
const TEXT_BATCH_SIZE = 50;
const DEPOT_PLACEHOLDER = 'ZXQDEPOTQXZ';
const textSources = new WeakMap();
const textTranslations = new WeakMap();
const attributeSources = new WeakMap();
const attributeTranslations = new WeakMap();
const cache = new Map();
const apiBaseUrl = localStorage.getItem('tmb_api_base_url') || location.origin;
const localToken = document.querySelector('meta[name="local-token"]').content;
let currentLanguage = 'ca';
let applying = false;
let observer;

function getLanguage() {
  return currentLanguage;
}

function setStatus(message) {
  document.querySelector('#languageStatus').textContent = message;
}

function ignored(element) {
  return element.closest('script,style,noscript,textarea,input,pre,[data-no-translate]');
}

function textNodes(root = document) {
  const nodes = [];
  if (root.nodeType === Node.TEXT_NODE) {
    nodes.push(root);
    return nodes;
  }
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) nodes.push(walker.currentNode);
  return nodes.filter(node => !ignored(node.parentElement));
}

function translatableAttributes(root = document) {
  const elements = [];
  if (root instanceof Element) elements.push(root);
  elements.push(...root.querySelectorAll?.('[title],[placeholder],[aria-label],[alt]') || []);
  return elements.flatMap(element => {
    if (ignored(element)) return [];
    return ['title', 'placeholder', 'aria-label', 'alt']
      .filter(name => element.hasAttribute(name))
      .map(name => ({ element, name }));
  });
}

function getTextSource(node) {
  if (!textSources.has(node)) textSources.set(node, node.data);
  else if (node.data !== textTranslations.get(node)) textSources.set(node, node.data);
  return textSources.get(node);
}

function getAttributeSource(element, name) {
  let sources = attributeSources.get(element);
  let translations = attributeTranslations.get(element);
  if (!sources) {
    sources = new Map();
    translations = new Map();
    attributeSources.set(element, sources);
    attributeTranslations.set(element, translations);
  }
  const value = element.getAttribute(name);
  if (!sources.has(name) || value !== translations.get(name)) sources.set(name, value);
  return sources.get(name);
}

async function translateBatch(texts, source, target) {
  if (source === target) return texts;
  const keyFor = text => `${source}\u0000${target}\u0000${text}`;
  const missing = [...new Set(texts)].filter(text => !cache.has(keyFor(text)));
  for (let offset = 0; offset < missing.length; offset += TEXT_BATCH_SIZE) {
    const batch = missing.slice(offset, offset + TEXT_BATCH_SIZE);
    const glossary = batch.map(() => []);
    const translatedTexts = batch.map((text, index) => source === 'ca'
      ? text.replace(/\bcotxer(?:a|es)\b/gi, match => {
        const plural = match.toLowerCase().endsWith('es');
        const term = target === 'es' ? 'cochera' : 'depot';
        const localizedTerm = `${term}${plural ? 's' : ''}`;
        glossary[index].push({
          term: match === match.toUpperCase()
            ? localizedTerm.toUpperCase()
            : match[0] === match[0].toUpperCase()
              ? `${localizedTerm[0].toUpperCase()}${localizedTerm.slice(1)}`
              : localizedTerm
        });
        return DEPOT_PLACEHOLDER;
      })
      : text);
    const response = await fetch(`${apiBaseUrl.replace(/\/$/, '')}/api/translate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Local-Token': localToken },
      body: JSON.stringify({ texts: translatedTexts, source, target })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `Error de traducció (${response.status}).`);
    if (!Array.isArray(result.translations) || result.translations.length !== translatedTexts.length ||
        result.translations.some(value => typeof value !== 'string' || !value.trim())) {
      throw new Error('El servidor no ha traduït tots els textos.');
    }
    batch.forEach((text, index) => {
      let translated = result.translations[index];
      if (glossary[index].length && !translated.includes(DEPOT_PLACEHOLDER)) {
        throw new Error('No s’ha pogut conservar el terme «cotxera» durant la traducció.');
      }
      for (const { term } of glossary[index]) {
        translated = translated.replace(DEPOT_PLACEHOLDER, term);
      }
      cache.set(keyFor(text), translated);
    });
  }
  return texts.map(text => cache.get(keyFor(text)));
}

async function translateEntries(entries, language) {
  if (!entries.length) return;
  if (language === 'ca') {
    applying = true;
    try {
      entries.forEach(({ set, source }) => set(source));
    } finally {
      applying = false;
    }
    return;
  }
  const translated = await translateBatch(entries.map(entry => entry.source), 'ca', language);
  applying = true;
  try {
    entries.forEach((entry, index) => entry.set(translated[index]));
  } finally {
    applying = false;
  }
}

function collectEntries(root = document) {
  const entries = textNodes(root).flatMap(node => {
    const source = getTextSource(node);
    if (!source.trim()) return [];
    return [{
      source,
      set(value) {
        node.data = value;
        textTranslations.set(node, value);
      }
    }];
  });
  for (const { element, name } of translatableAttributes(root)) {
    const source = getAttributeSource(element, name);
    if (!source?.trim()) continue;
    entries.push({
      source,
      set(value) {
        element.setAttribute(name, value);
        attributeTranslations.get(element).set(name, value);
      }
    });
  }
  return entries;
}

async function applyLanguage(language, { persist = true } = {}) {
  if (!LANGUAGES.has(language)) throw new Error('Idioma no admès.');
  const previousLanguage = currentLanguage;
  document.querySelector('#languageSelect').disabled = true;
  setStatus('');
  currentLanguage = language;
  try {
    await translateEntries(collectEntries(), language);
    document.documentElement.lang = language;
    document.querySelector('#languageSelect').value = language;
    if (persist) localStorage.setItem(LANGUAGE_KEY, language);
  } catch (error) {
    currentLanguage = previousLanguage;
    document.querySelector('#languageSelect').value = previousLanguage;
    setStatus(`No s’ha pogut traduir la interfície: ${error.message}`);
    throw error;
  } finally {
    document.querySelector('#languageSelect').disabled = false;
  }
}

async function translateText(text, source = currentLanguage, target = 'en') {
  if (!text || source === target) return text;
  return (await translateBatch([text], source, target))[0];
}

async function initializeLocalization() {
  const select = document.querySelector('#languageSelect');
  observer = new MutationObserver(records => {
    if (applying || !currentLanguage) return;
    const nodes = new Set();
    const attributes = new Set();
    for (const record of records) {
      if (record.type === 'characterData' && record.target.data !== textTranslations.get(record.target)) {
        nodes.add(record.target);
      }
      if (record.type === 'attributes') {
        const translations = attributeTranslations.get(record.target);
        if (record.target.getAttribute(record.attributeName) !== translations?.get(record.attributeName)) {
          attributes.add(record.target);
        }
      }
      record.addedNodes.forEach(node => {
        textNodes(node).forEach(item => nodes.add(item));
        translatableAttributes(node).forEach(({ element }) => attributes.add(element));
      });
    }
    const targets = [...nodes].filter(node => node.isConnected);
    const entries = targets.flatMap(node => collectEntries(node));
    for (const element of attributes) {
      if (element.isConnected) entries.push(...collectEntries(element).filter(entry =>
        entry.set && ['title', 'placeholder', 'aria-label', 'alt'].some(name => element.hasAttribute(name))
      ));
    }
    translateEntries(entries, currentLanguage).catch(error => {
      setStatus(`No s’ha pogut traduir el text nou: ${error.message}`);
    });
  });
  observer.observe(document.body, {
    subtree: true,
    childList: true,
    characterData: true,
    attributes: true,
    attributeFilter: ['title', 'placeholder', 'aria-label', 'alt']
  });
  select.addEventListener('change', () => {
    applyLanguage(select.value).catch(() => {});
  });
  const savedLanguage = localStorage.getItem(LANGUAGE_KEY);
  if (savedLanguage && LANGUAGES.has(savedLanguage)) {
    try {
      await applyLanguage(savedLanguage, { persist: false });
    } catch {
      localStorage.removeItem(LANGUAGE_KEY);
      await applyLanguage('ca', { persist: false });
    }
  } else {
    select.value = 'ca';
    currentLanguage = 'ca';
  }
}

export { getLanguage, initializeLocalization, translateText };
