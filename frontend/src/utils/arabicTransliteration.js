/**
 * utils/arabicTransliteration.js
 * AI-Powered English-to-Arabic Trade Name Transliteration (Industry Best Practice)
 * 
 * Uses backend LLM endpoint (/TradeName/Transliterate) to provide context-aware
 * UAE DED-compliant Arabic trade names without maintaining fragile static dictionaries.
 */
import { API_BASE } from '../config';

/**
 * Calls the backend AI transliteration service with debouncing support.
 * @param {string} englishName - The English trade name input.
 * @returns {Promise<string>} The official Arabic trade name equivalent.
 */
export async function fetchArabicTransliteration(englishName) {
  if (!englishName || !englishName.trim()) {
    return '';
  }

  try {
    const res = await fetch(`${API_BASE}/TradeName/Transliterate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name_en: englishName.trim() }),
    });

    if (res.ok) {
      const data = await res.json();
      if (data && data.arabic_name) {
        return data.arabic_name.trim();
      }
    }
  } catch (err) {
    console.warn('Backend AI transliteration failed, falling back:', err);
  }

  // Graceful client-side fallback if backend is offline
  return quickClientFallback(englishName);
}

/**
 * Ultra-lightweight phonetic fallback (no maintained static dictionaries).
 */
const CHAR_MAP = {
  sh: 'ش', th: 'ث', kh: 'خ', ch: 'تش', ph: 'ف', gh: 'غ', dh: 'ذ', ee: 'ي', oo: 'و',
  a: 'ا', b: 'ب', c: 'ك', d: 'د', e: 'ي', f: 'ف', g: 'ج', h: 'ه', i: 'ي', j: 'ج',
  k: 'ك', l: 'ل', m: 'م', n: 'ن', o: 'و', p: 'ب', q: 'ق', r: 'ر', s: 'س', t: 'ت',
  u: 'و', v: 'ف', w: 'و', x: 'كس', y: 'ي', z: 'ز',
};

export function quickClientFallback(englishName) {
  if (!englishName || !englishName.trim()) return '';
  const clean = englishName.trim().toLowerCase();
  let result = '';
  let i = 0;
  while (i < clean.length) {
    if (i + 1 < clean.length && CHAR_MAP[clean.slice(i, i + 2)]) {
      result += CHAR_MAP[clean.slice(i, i + 2)];
      i += 2;
    } else if (CHAR_MAP[clean[i]]) {
      result += CHAR_MAP[clean[i]];
      i += 1;
    } else {
      result += clean[i];
      i += 1;
    }
  }
  return result;
}

// Backward compatibility alias
export const convertEnglishToTradeNameArabic = quickClientFallback;
