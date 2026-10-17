/* DermaCheckerBD — global frontend JS */

// Defined while the deferred scripts are loading so page-specific DOM-ready
// handlers can use translations regardless of their listener order.
window.DERMA = window.DERMA || {};
window.DERMA.t = function (key, fallback, params) {
  var translations = window.DERMA_TRANSLATIONS && window.DERMA_TRANSLATIONS.bn;
  var value = window.DERMA.language === 'bn' && translations && translations[key]
    ? translations[key]
    : (fallback || key);
  return value.replace(/\{\{\s*([a-z0-9_.-]+)\s*\}\}/gi, function (match, name) {
    var normalized = name.toLowerCase().replace(/[_.]/g, '-');
    return params && Object.prototype.hasOwnProperty.call(params, normalized)
      ? params[normalized]
      : match;
  });
};
window.DERMA.className = function (code, fallback) {
  return window.DERMA.t('class-name.' + String(code || '').toLowerCase(), fallback || code);
};
window.DERMA.category = function (category) {
  var normalized = String(category || '').toLowerCase();
  var labels = {
    'benign': ['category.benign', 'Benign'],
    'malignant': ['category.malignant', 'Malignant'],
    'pre malignant': ['category.pre_malignant', 'Pre-malignant'],
    'unknown': ['category.unknown', 'Unknown'],
  };
  return labels[normalized]
    ? window.DERMA.t(labels[normalized][0], labels[normalized][1])
    : category;
};

/**
 * Wrap every <input type="password"> inside an .auth-card (login, signup,
 * password change) with a show/hide toggle button. Works for any number of
 * password fields and survives Django's crispy-forms rendering.
 */
function initializePasswordToggles() {
  var inputs = document.querySelectorAll('.auth-card input[type="password"]');
  Array.prototype.forEach.call(inputs, function (input) {
    if (input.dataset.toggleReady === '1') { return; }
    input.dataset.toggleReady = '1';

    // Find the existing input wrapper (crispy-forms wraps each field in
    // .mb-3). If we cannot find one, create our own.
    var wrapper = input.closest('.mb-3') || input.parentElement;
    if (!wrapper.classList.contains('password-field')) {
      // Build a dedicated wrapper so the toggle can be absolutely positioned
      // relative to the input.
      var fieldWrapper = document.createElement('div');
      fieldWrapper.className = 'password-field';
      input.parentNode.insertBefore(fieldWrapper, input);
      fieldWrapper.appendChild(input);
      wrapper = fieldWrapper;
    }

    var toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'password-toggle';
    toggle.setAttribute('aria-label', 'Show password');
    toggle.setAttribute('aria-pressed', 'false');
    toggle.setAttribute('title', 'Show password');
    toggle.innerHTML =
      '<svg class="toggle-icon-eye" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
      'stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"></path>' +
      '<circle cx="12" cy="12" r="3"></circle>' +
      '</svg>' +
      '<svg class="toggle-icon-eye-off" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
      'stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-10-8-10-8a18.45 ' +
      '18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 10 8 10 8a18.5 ' +
      '18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>' +
      '<line x1="1" y1="1" x2="23" y2="23"></line>' +
      '</svg>';

    toggle.addEventListener('click', function () {
      var show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      toggle.setAttribute('aria-pressed', show ? 'true' : 'false');
      toggle.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
      toggle.setAttribute('title', show ? 'Hide password' : 'Show password');
      // Keep keyboard focus on the toggle (not the input) for screen readers.
      toggle.focus();
    });

    wrapper.appendChild(toggle);
  });
}

function initializeScanSequence() {
  var panel = document.querySelector('[data-scan-sequence]');
  if (!panel || window.matchMedia('(prefers-reduced-motion: reduce)').matches) { return; }

  var line = panel.querySelector('[data-scan-line]');
  var images = Array.prototype.slice.call(panel.querySelectorAll('.scan-demo-image'));
  if (!line || images.length < 2) { return; }

  var activeIndex = images.findIndex(function (image) {
    return image.classList.contains('is-active');
  });
  if (activeIndex < 0) { activeIndex = 0; }
  images.forEach(function (image, index) {
    image.classList.toggle('is-active', index === activeIndex);
  });

  line.addEventListener('animationiteration', function (event) {
    if (event.animationName !== 'scanline-cycle') { return; }
    var nextIndex = (activeIndex + 1) % images.length;
    images[activeIndex].classList.remove('is-active');
    images[nextIndex].classList.add('is-active');
    activeIndex = nextIndex;
  });

  function loadAndDecode(image) {
    var loaded = image.complete ? Promise.resolve() : new Promise(function (resolve, reject) {
      image.addEventListener('load', resolve, { once: true });
      image.addEventListener('error', function () {
        reject(new Error('Failed to load scan demo image: ' + image.currentSrc));
      }, { once: true });
    });

    return loaded.then(function () {
      if (!image.naturalWidth) {
        throw new Error('Scan demo image has no decoded dimensions: ' + image.currentSrc);
      }
      return typeof image.decode === 'function' ? image.decode() : undefined;
    });
  }

  Promise.all(images.map(loadAndDecode)).then(function () {
    panel.classList.add('scan-sequence-ready');
  }).catch(function (error) {
    console.error('The scan animation could not preload all demo images.', error);
  });
}

// Initialize Bootstrap tooltips and Lucide icons on every page load.
document.addEventListener('DOMContentLoaded', function () {
  if (window.lucide && typeof window.lucide.createIcons === 'function') {
    window.lucide.createIcons();
  }
  // Auto-focus first input in any auth form (skip password fields so the
  // browser's own password manager / autofill behaves predictably).
  var firstInput = document.querySelector('.auth-card input[type=text], .auth-card input[type=email]');
  if (firstInput && !firstInput.value) { firstInput.focus(); }
  // Wire up the show/hide password toggles on auth pages.
  initializePasswordToggles();
  // Wire up the language toggle (EN ↔ বাং).
  initializeLanguageToggle();
  initializeScanSequence();
});

/**
 * Lightweight client-side language toggle with real text translation.
 *
 * Stores the user's preference in localStorage, applies a `.lang-bn`
 * class to <body> when Bengali is selected (which causes the Noto Sans
 * Bengali font fallback to take over), AND walks every `[data-i18n]`
 * element to swap its text with the Bangla translation from
 * static/js/translations.js.
 *
 * For elements that need to switch back to English, the original
 * English text is captured into `data-i18n-original` on first run
 * so we can restore it without re-reading the DOM.
 */
function initializeLanguageToggle() {
  var buttons = document.querySelectorAll('.lang-toggle-btn');
  if (!buttons.length) return;

  // Capture original English text on first run so we can restore later.
  // We do this lazily — only for elements that have data-i18n but not
  // yet data-i18n-original.
  function captureOriginals() {
    var els = document.querySelectorAll('[data-i18n]:not([data-i18n-original])');
    Array.prototype.forEach.call(els, function (el) {
      el.setAttribute('data-i18n-original', el.textContent);
      el.setAttribute('data-i18n-original-html', el.innerHTML);
    });
  }

  function interpolate(value, el) {
    return value.replace(/\{\{\s*([a-z0-9_.-]+)\s*\}\}/gi, function (match, name) {
      var attribute = 'data-i18n-param-' + name.toLowerCase().replace(/[_.]/g, '-');
      var parameter = el.getAttribute(attribute);
      return parameter === null ? match : parameter;
    });
  }

  function applyTranslations(lang) {
    var dict = (window.DERMA_TRANSLATIONS && window.DERMA_TRANSLATIONS[lang]) || {};
    captureOriginals();

    // 1. Text content (data-i18n)
    var els = document.querySelectorAll('[data-i18n]');
    Array.prototype.forEach.call(els, function (el) {
      var key = el.getAttribute('data-i18n');
      var translated = dict[key];
      if (lang === 'bn' && translated) {
        // Translation values are plain text. Use textContent so user-supplied
        // template values can never become markup.
        el.textContent = interpolate(translated, el);
      } else {
        var originalHtml = el.getAttribute('data-i18n-original-html');
        if (originalHtml !== null) {
          el.innerHTML = originalHtml;
        }
      }
    });

    // Category names are rendered by Python from persisted prediction data.
    // Translate the display text without changing the stored category/code.
    var categoryEls = document.querySelectorAll('[data-i18n-category]');
    Array.prototype.forEach.call(categoryEls, function (el) {
      if (!el.hasAttribute('data-i18n-category-original-html')) {
        el.setAttribute('data-i18n-category-original-html', el.innerHTML);
      }
      var category = (el.getAttribute('data-i18n-category') || '').toLowerCase();
      var categoryKey = 'category.' + category.replace(/\s+/g, '_');
      if (lang === 'bn' && dict[categoryKey]) {
        el.textContent = dict[categoryKey];
      } else {
        el.innerHTML = el.getAttribute('data-i18n-category-original-html');
      }
    });

    var classNameEls = document.querySelectorAll('[data-i18n-class]');
    Array.prototype.forEach.call(classNameEls, function (el) {
      if (!el.hasAttribute('data-i18n-class-original-html')) {
        el.setAttribute('data-i18n-class-original-html', el.innerHTML);
      }
      var code = (el.getAttribute('data-i18n-class') || '').toLowerCase();
      if (lang === 'bn' && dict['class-name.' + code]) {
        el.textContent = code.toUpperCase() + ' — ' + dict['class-name.' + code];
      } else {
        el.innerHTML = el.getAttribute('data-i18n-class-original-html');
      }
    });

    // Image-quality reports include measured values in their English backend
    // messages. Translate those generated messages while retaining the values.
    var qualityMessages = document.querySelectorAll('[data-quality-message]');
    Array.prototype.forEach.call(qualityMessages, function (el) {
      var raw = el.getAttribute('data-quality-message') || '';
      var name = el.getAttribute('data-quality-name') || '';
      el.textContent = lang === 'bn' ? translateQualityMessage(name, raw) : raw;
    });
    var qualitySuggestions = document.querySelectorAll('[data-quality-suggestion]');
    Array.prototype.forEach.call(qualitySuggestions, function (el) {
      var raw = el.getAttribute('data-quality-suggestion') || '';
      var name = el.getAttribute('data-quality-name') || '';
      el.textContent = lang === 'bn' ? translateQualitySuggestion(name, raw) : raw;
    });

    // Translate server-rendered feedback (Django messages and upload errors).
    var serverMessages = document.querySelectorAll('[data-i18n-server]');
    Array.prototype.forEach.call(serverMessages, function (el) {
      if (!el.hasAttribute('data-i18n-server-original')) {
        el.setAttribute('data-i18n-server-original', el.textContent.trim());
      }
      var raw = el.getAttribute('data-i18n-server-original');
      el.textContent = lang === 'bn' ? translateServerMessage(raw) : raw;
    });

    // 2. Placeholders (data-i18n-ph)
    var phEls = document.querySelectorAll('[data-i18n-ph]');
    Array.prototype.forEach.call(phEls, function (el) {
      var key = el.getAttribute('data-i18n-ph');
      var translated = dict[key];
      if (lang === 'bn' && translated) {
        if (!el.hasAttribute('data-i18n-ph-original')) {
          el.setAttribute('data-i18n-ph-original', el.getAttribute('placeholder') || '');
        }
        el.setAttribute('placeholder', translated);
      } else {
        var original = el.getAttribute('data-i18n-ph-original');
        if (original !== null) {
          el.setAttribute('placeholder', original);
        }
      }
    });

    // 3. Title attributes (data-i18n-title)
    var tEls = document.querySelectorAll('[data-i18n-title]');
    Array.prototype.forEach.call(tEls, function (el) {
      var key = el.getAttribute('data-i18n-title');
      var translated = dict[key];
      if (lang === 'bn' && translated) {
        if (!el.hasAttribute('data-i18n-title-original')) {
          el.setAttribute('data-i18n-title-original', el.getAttribute('title') || '');
        }
        el.setAttribute('title', interpolate(translated, el));
      } else {
        var original = el.getAttribute('data-i18n-title-original');
        if (original !== null) {
          el.setAttribute('title', original);
        }
      }
    });

    // 4. aria-label attributes (data-i18n-aria)
    var aEls = document.querySelectorAll('[data-i18n-aria]');
    Array.prototype.forEach.call(aEls, function (el) {
      var key = el.getAttribute('data-i18n-aria');
      var translated = dict[key];
      if (lang === 'bn' && translated) {
        if (!el.hasAttribute('data-i18n-aria-original')) {
          el.setAttribute('data-i18n-aria-original', el.getAttribute('aria-label') || '');
        }
        el.setAttribute('aria-label', interpolate(translated, el));
      } else {
        var original = el.getAttribute('data-i18n-aria-original');
        if (original !== null) {
          el.setAttribute('aria-label', original);
        }
      }
    });

    // Re-render Lucide icons in case any button content changed shape
    if (window.lucide) window.lucide.createIcons();
  }

  function translateQualityMessage(name, raw) {
    var match;
    if (name === 'resolution') {
      match = raw.match(/^Too small: ([\dx×]+)px \(need ≥?(\d+)px on (?:the )?short side\)\./);
      if (match) return window.DERMA.t('quality.too_small', raw, { size: match[1], min: match[2] });
      match = raw.match(/^Very large: ([\dx×]+)px/);
      if (match) return window.DERMA.t('quality.too_large', raw, { size: match[1] });
      match = raw.match(/^Adequate: ([\dx×]+)px/);
      if (match) return window.DERMA.t('quality.adequate', raw, { size: match[1] });
    }
    if (name === 'blur') {
      match = raw.match(/Laplacian variance = ([\d.]+) \(threshold ([\d.]+)\)\. (Sharp enough\.|Image looks blurry\.)/);
      if (match) return window.DERMA.t('quality.blur_detail', raw, {
        value: match[1], threshold: match[2],
        outcome: match[3].indexOf('Sharp enough') === 0
          ? window.DERMA.t('quality.sharp_enough', 'Sharp enough.')
          : window.DERMA.t('quality.blurry', 'Image looks blurry.'),
      });
    }
    if (name === 'brightness') {
      match = raw.match(/Mean intensity = ([\d.]+)\. (OK\.|Too dark\.|Too bright\.)/);
      if (match) {
        var brightnessResult = match[2] === 'OK.'
          ? window.DERMA.t('quality.brightness_ok', 'OK.')
          : window.DERMA.t(match[2] === 'Too dark.' ? 'quality.too_dark' : 'quality.too_bright', match[2]);
        return window.DERMA.t('quality.brightness_detail', raw, { value: match[1], outcome: brightnessResult });
      }
    }
    if (name === 'exposure') {
      match = raw.match(/Clipped pixels: ([\d.]+)% highlights, ([\d.]+)% shadows\.( OK\.| Some detail lost\.)/);
      if (match) return window.DERMA.t('quality.exposure_detail', raw, {
        highlights: match[1],
        shadows: match[2],
        outcome: window.DERMA.t(match[3].trim() === 'OK.' ? 'quality.exposure_ok' : 'quality.detail_lost', match[3].trim()),
      });
    }
    if (name === 'aspect') {
      match = raw.match(/Aspect ratio = ([\d.]+)\. (OK\.|Unusual cropping\.)/);
      if (match) return window.DERMA.t('quality.aspect_detail', raw, {
        value: match[1],
        outcome: window.DERMA.t(match[2] === 'OK.' ? 'quality.aspect_ok' : 'quality.unusual_cropping', match[2]),
      });
    }
    if (name === 'skin_plausibility') {
      match = raw.match(/Skin-tone pixels ≈ ([\d.]+)%. (Plausible\.|Doesn't look like a typical skin photo\.)/);
      if (match) return window.DERMA.t('quality.skin_detail', raw, {
        value: match[1],
        outcome: window.DERMA.t(match[2] === 'Plausible.' ? 'quality.plausible' : 'quality.not_typical_skin', match[2]),
      });
    }
    return raw;
  }

  function translateQualitySuggestion(name, raw) {
    var keyByName = {
      resolution: 'quality.suggest_resolution',
      blur: 'quality.suggest_blur',
      exposure: 'quality.suggest_exposure',
      aspect: 'quality.suggest_framing',
      skin_plausibility: 'quality.suggest_skin',
    };
    if (name === 'brightness') {
      keyByName.brightness = raw.indexOf('Increase ambient') === 0
        ? 'quality.suggest_brightness_low'
        : 'quality.suggest_brightness_high';
    }
    return window.DERMA.t(keyByName[name], raw);
  }

  function translateServerMessage(raw) {
    var known = {
      'Unsupported image type.': 'server.unsupported_image',
      'No image provided.': 'server.no_image',
      'Image too large. Max 10 MB.': 'server.image_too_large',
      'Photo added.': 'server.photo_added',
      'Lesion record deleted.': 'server.record_deleted',
      'Photo removed.': 'server.photo_removed',
      'No files were uploaded.': 'server.no_files',
      'Please upload at least 2 images to compare.': 'server.need_two_images',
      'No search performed yet.': 'docs.no_search',
      'Prediction could not be completed. Please try again later.': 'server.prediction_failed',
      'Please correct the errors below.': 'server.correct_errors',
    };
    if (known[raw]) return window.DERMA.t(known[raw], raw);
    var match = raw.match(/^Created lesion record ([A-Z0-9]+)\.$/);
    if (match) return window.DERMA.t('server.record_created', 'লেসন রেকর্ড {{id}} তৈরি হয়েছে।', { id: match[1] });
    match = raw.match(/^Too many files\. Max (\d+) images at once\.$/);
    if (match) return window.DERMA.t('server.too_many_files', 'একবারে সর্বোচ্চ {{max}}টি ছবি দেওয়া যাবে।', { max: match[1] });
    match = raw.match(/^File too large \((\d+) KB\)\. Maximum is 10 MB\.$/);
    if (match) return window.DERMA.t('server.file_too_large', 'ফাইলটি অনেক বড় ({{size}} KB)। সর্বোচ্চ ১০ MB হতে পারে।', { size: match[1] });
    match = raw.match(/^Unsupported file type ['"]?([^'"]+)['"]?\.? Use JPG, PNG, or WEBP\.$/);
    if (match) return window.DERMA.t('server.unsupported_type', 'এই ফাইলের ধরন সমর্থিত নয়: {{type}}। JPG, PNG বা WEBP ব্যবহার করুন।', { type: match[1] });
    match = raw.match(/^Image dimensions (\d+)x(\d+)px are outside the supported range\.$/);
    if (match) return window.DERMA.t('server.dimensions', 'ছবির মাপ {{width}}×{{height}} পিক্সেল, যা সমর্থিত সীমার বাইরে।', { width: match[1], height: match[2] });
    match = raw.match(/^Min supported side: (\d+)px\. Max supported side: (\d+)px\.$/);
    if (match) return window.DERMA.t('server.dimension_details', 'সর্বনিম্ন সমর্থিত বাহু: {{min}} পিক্সেল। সর্বোচ্চ: {{max}} পিক্সেল।', { min: match[1], max: match[2] });
    match = raw.match(/^Skin-tone pixel ratio: ([\d.]+)%. No automatic out-of-distribution detector is configured\.$/);
    if (match) return window.DERMA.t('server.skin_ratio', 'ত্বকের রঙের পিক্সেলের অনুপাত: {{ratio}}%। স্বয়ংক্রিয় সীমার-বাইরের ছবি শনাক্তকরণ চালু নেই।', { ratio: match[1] });
    match = raw.match(/^Could not (process image|assess image|run reliability check|compare images):\s*(.*)$/i);
    if (match) {
      var operation = {
        'process image': 'ছবি প্রক্রিয়া করা যায়নি',
        'assess image': 'ছবির মান যাচাই করা যায়নি',
        'run reliability check': 'নির্ভরযোগ্যতা যাচাই করা যায়নি',
        'compare images': 'ছবিগুলো তুলনা করা যায়নি'
      }[match[1].toLowerCase()];
      return operation + (match[2] ? ': ' + match[2] : '।');
    }
    if (raw.indexOf('Re-capture the photo') === 0) return window.DERMA.t('server.recapture', 'উপযুক্ত ফ্রেমে আবার ছবি তুলুন।');
    if (raw.indexOf('Upload a clear, well-lit close-up') === 0) return window.DERMA.t('server.clear_closeup', 'ত্বকের দাগের পরিষ্কার, ভালো আলোতে তোলা কাছের ছবি আপলোড করুন।');
    if (raw.indexOf('Avoid screenshots, diagrams') === 0) return window.DERMA.t('server.avoid_screenshot', 'স্ক্রিনশট, ডায়াগ্রাম বা ত্বক নয়—এমন বস্তুর ছবি এড়িয়ে চলুন।');
    if (raw.indexOf("This photo doesn't look like a typical skin lesion.") === 0) {
      return window.DERMA.t('server.not_skin', 'এই ছবিটি সাধারণ ত্বকের দাগের মতো দেখাচ্ছে না। মডেলের ফলাফল নির্ভরযোগ্য নাও হতে পারে।');
    }
    if (raw.indexOf('File is corrupt or not a valid image.') === 0) {
      return window.DERMA.t('server.corrupt_image', 'ফাইলটি নষ্ট অথবা বৈধ ছবি নয়।');
    }
    return raw;
  }

  function applyLang(lang) {
    lang = lang === 'bn' ? 'bn' : 'en';
    document.documentElement.lang = lang;
    document.body.classList.toggle('lang-bn', lang === 'bn');
    if (window.DERMA) window.DERMA.language = lang;
    buttons.forEach(function (b) {
      var isActive = b.dataset.lang === lang;
      b.setAttribute('aria-pressed', isActive ? 'true' : 'false');
      b.classList.toggle('active', isActive);
      b.classList.toggle('btn-secondary', isActive);
      b.classList.toggle('btn-outline-secondary', !isActive);
    });
    // Apply translations
    applyTranslations(lang);
    try { localStorage.setItem('derma_lang', lang); } catch (e) {}
    var cookie = 'derma_lang=' + lang + '; Path=/; Max-Age=31536000; SameSite=Lax';
    if (window.location.protocol === 'https:') cookie += '; Secure';
    document.cookie = cookie;
    document.dispatchEvent(new CustomEvent('derma:languagechange', { detail: { language: lang } }));
  }

  // Capture originals BEFORE applying any language (so English is the
  // captured baseline).
  captureOriginals();

  // A first-party cookie keeps Django and the chatbot in sync on later
  // requests. Keep the prior localStorage preference as a one-time fallback.
  var saved = null;
  var cookieMatch = document.cookie.match(/(?:^|;\s*)derma_lang=(bn|en)(?:;|$)/);
  if (cookieMatch) saved = cookieMatch[1];
  if (!saved) {
    try { saved = localStorage.getItem('derma_lang'); } catch (e) {}
  }
  saved = saved || (window.DERMA && window.DERMA.language) || 'en';
  applyLang(saved);

  buttons.forEach(function (b) {
    b.addEventListener('click', function () {
      applyLang(b.dataset.lang || 'en');
    });
  });

}

// Small helper: post JSON with CSRF header.
window.postJson = async function (url, data) {
  var resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': window.DERMA ? window.DERMA.csrf : '',
    },
    body: JSON.stringify(data),
    credentials: 'same-origin',
  });
  if (!resp.ok) {
    var txt = await resp.text();
    throw new Error('HTTP ' + resp.status + ': ' + txt);
  }
  return resp.json();
};
