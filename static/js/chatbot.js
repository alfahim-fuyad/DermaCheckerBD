/* DermaCheckerBD — chatbot frontend */

(function () {
  'use strict';

  var fabBtn = document.getElementById('chatbotToggle');
  var fab = document.getElementById('chatbotFab');
  var panel = document.getElementById('chatbotPanel');
  var closeBtn = document.getElementById('chatbotClose');
  var clearBtn = document.getElementById('chatbotClear');
  var form = document.getElementById('chatbotForm');
  var input = document.getElementById('chatbotInput');
  var sendBtn = document.getElementById('chatbotSend');
  var messages = document.getElementById('chatbotMessages');

  if (!fabBtn || !panel || !form) return;

  var scope = panel.getAttribute('data-chat-scope') || 'public';
  var scopeType = panel.getAttribute('data-chat-role') || 'public';
  var historyKey = 'derma_chat_history_' + scope;
  var messageUrl = panel.getAttribute('data-message-url') || '/chatbot/message/';

  // Conversation held in JS only; lives for the current page session.
  // We persist in sessionStorage so it survives page navigations.
  var history = [];
  try {
    var saved = sessionStorage.getItem(historyKey);
    if (saved) history = JSON.parse(saved);
  } catch (e) { /* ignore */ }

  if (!Array.isArray(history)) history = [];
  history = history.filter(function (m) {
    return m && (m.role === 'user' || m.role === 'model') && typeof m.content === 'string';
  }).slice(-20);

  if (history && history.length) {
    // Re-render history (skip the welcome bubble already in DOM)
    history.forEach(function (m) {
      appendMessage(m.role, m.content, false);
    });
    messages.scrollTop = messages.scrollHeight;
  }

  function persist() {
    try { sessionStorage.setItem(historyKey, JSON.stringify(history)); } catch (e) {}
  }

  function welcomeMessage() {
    var key = scopeType === 'staff'
      ? 'chatbot.welcome_staff'
      : (scopeType === 'public' ? 'chatbot.welcome_public' : 'chatbot.welcome_private');
    var fallback = scopeType === 'staff'
      ? 'I can answer public site questions and provide anonymized site-wide totals. I cannot access usernames or individual records.'
      : (scopeType === 'public'
        ? 'I can answer general questions and questions about this site. Sign in to ask about your own dashboard. I don\'t diagnose.'
        : 'I can answer public site questions and summarize your own dashboard and history. I cannot access another user\'s records. I don\'t diagnose.');
    return window.DERMA.t(key, fallback);
  }

  function appendMessage(role, content, animate) {
    var wrap = document.createElement('div');
    wrap.className = 'chatbot-msg ' + (role === 'user' ? 'user' : 'chatbot-msg-bot');
    var bubble = document.createElement('div');
    bubble.className = 'chatbot-msg-bubble';
    // Never trust downstream content as raw HTML. The model's replies go
    // through a strict allowlist that strips every tag except <b>, <i>,
    // <em>, <strong>, <code>, <br> and a few inline formatting helpers.
    bubble.innerHTML = sanitizeChatHtml(content);
    wrap.appendChild(bubble);
    messages.appendChild(wrap);
    messages.scrollTop = messages.scrollHeight;
    return wrap;
  }

  function appendTyping() {
    var wrap = document.createElement('div');
    wrap.className = 'chatbot-msg chatbot-msg-bot';
    var bubble = document.createElement('div');
    bubble.className = 'chatbot-msg-bubble';
    bubble.innerHTML = '<div class="chatbot-typing"><span></span><span></span><span></span></div>';
    wrap.appendChild(bubble);
    messages.appendChild(wrap);
    messages.scrollTop = messages.scrollHeight;
    return wrap;
  }

  function openPanel() {
    panel.hidden = false;
    panel.setAttribute('aria-modal', 'true');
    fabBtn.setAttribute('aria-expanded', 'true');
    // Remember the element that had focus so we can restore it on close.
    lastFocusedEl = document.activeElement;
    setTimeout(function () { input.focus(); }, 100);
    document.addEventListener('focus', trapFocus, true);
  }
  function closePanel() {
    panel.hidden = true;
    panel.setAttribute('aria-modal', 'false');
    fabBtn.setAttribute('aria-expanded', 'false');
    document.removeEventListener('focus', trapFocus, true);
    if (lastFocusedEl && typeof lastFocusedEl.focus === 'function') {
      lastFocusedEl.focus();
    }
  }

  // Minimal focus trap: keep Tab cycling inside the panel while it is open.
  var lastFocusedEl = null;
  var FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
  function trapFocus(e) {
    if (panel.hidden) return;
    if (!panel.contains(e.target)) {
      e.stopPropagation();
      input.focus();
      return;
    }
    if (e.key === 'Tab') { return; } // Tab handled below
  }
  panel.addEventListener('keydown', function (e) {
    if (e.key !== 'Tab' || panel.hidden) return;
    var f = Array.prototype.filter.call(
      panel.querySelectorAll(FOCUSABLE),
      function (el) { return el.offsetParent !== null && !el.disabled; }
    );
    if (!f.length) return;
    var first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault(); last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault(); first.focus();
    }
  });

  fabBtn.addEventListener('click', function () {
    if (panel.hidden) openPanel(); else closePanel();
  });
  if (closeBtn) closeBtn.addEventListener('click', closePanel);

  if (clearBtn) {
    clearBtn.addEventListener('click', function () {
      history = [];
      persist();
      // Reset to welcome
      messages.innerHTML = '';
      appendMessage('model', welcomeMessage(), false);
    });
  }

  // Esc to close
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !panel.hidden) closePanel();
  });

  // Send message
  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text) return;

    appendMessage('user', text, true);
    history.push({ role: 'user', content: text });
    history = history.slice(-20);
    persist();

    input.value = '';
    input.disabled = true;
    sendBtn.disabled = true;

    var typing = appendTyping();

    try {
      var resp = await fetch(messageUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': document.getElementById('chatbotCsrf').value,
        },
        body: JSON.stringify({
          message: text,
          language: (window.DERMA && window.DERMA.language) || 'en',
          history: history.slice(0, -1),
        }),
        credentials: 'same-origin',
      });

      if (!resp.ok) {
        throw new Error('HTTP ' + resp.status);
      }
      var data = await resp.json();

      // Replace typing bubble with reply
      typing.remove();
      appendMessage('model', data.reply || window.DERMA.t('chatbot.no_reply', '(no reply)'), true);
      history.push({ role: 'model', content: data.reply || '' });
      history = history.slice(-20);
      persist();
    } catch (err) {
      typing.remove();
      var msg = window.DERMA.t(
        'chatbot.error.network',
        'Sorry, I couldn\'t reach the assistant right now. Please try again in a moment. For urgent concerns, consult a dermatologist.'
      );
      appendMessage('model', msg, true);
      history.push({ role: 'model', content: msg });
      persist();
    } finally {
      input.disabled = false;
      sendBtn.disabled = false;
      input.focus();
    }
  });

  function escapeHtml(s) {
    return s
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /**
   * Strict allowlist-based HTML sanitiser for chatbot replies.
   * Allows only <b>, <i>, <em>, <strong>, <code>, <br>, <ul>, <ol>, <li>,
   * <p>. Strips every attribute (no onclick, no href, no style). Any other
   * tag is escaped — its text content is preserved but the tag itself is
   * neutralised. Defends against stored XSS via sessionStorage replay.
   */
  function sanitizeChatHtml(input) {
    if (input == null) return '';
    var s = String(input);
    // First escape everything to a known-good baseline.
    s = escapeHtml(s);
    // Then selectively re-enable the allowed tags by un-escaping them.
    var allow = ['b', 'i', 'em', 'strong', 'code', 'br', 'ul', 'ol', 'li', 'p'];
    allow.forEach(function (tag) {
      // Opening tags (no attributes permitted)
      s = s.replace(new RegExp('&lt;' + tag + '(\\s[^&]*)?&gt;', 'gi'), '<' + tag + '>');
      // Closing tags
      s = s.replace(new RegExp('&lt;/' + tag + '&gt;', 'gi'), '</' + tag + '>');
      // Self-closing variant (mainly for <br>)
      s = s.replace(new RegExp('&lt;' + tag + '\\s*/?&gt;', 'gi'), '<' + tag + '>');
    });
    return s;
  }
})();
