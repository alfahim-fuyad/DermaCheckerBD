/* DermaCheckerBD — image upload interaction */

window.setupImageUpload = function (opts) {
  // opts: { dropId, inputId, acceptTypes, onFile }
  var drop = document.getElementById(opts.dropId);
  var input = document.getElementById(opts.inputId);
  if (!drop || !input) return null;

  var currentFile = null;
  var preview = drop.querySelector('[data-upload-preview]');
  var emptyState = drop.querySelector('[data-upload-empty]');
  var selectedState = drop.querySelector('[data-upload-selected]');
  var filename = drop.querySelector('[data-upload-filename]');
  var status = drop.querySelector('[data-upload-status]');
  var error = drop.querySelector('[data-upload-error]');
  var previewUrl = null;
  var replaceInput = document.createElement('input');
  replaceInput.type = 'file';
  replaceInput.accept = input.accept;
  replaceInput.hidden = true;
  replaceInput.setAttribute('aria-hidden', 'true');
  drop.appendChild(replaceInput);

  function translate(key, fallback, params) {
    return window.DERMA && window.DERMA.t
      ? window.DERMA.t(key, fallback, params)
      : fallback;
  }

  function setInputFile(file) {
    if (!window.DataTransfer) {
      throw new Error('DataTransfer is unavailable in this browser.');
    }
    var transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
  }

  function clearSelection(notify) {
    currentFile = null;
    input.value = '';
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      previewUrl = null;
    }
    if (preview) {
      preview.removeAttribute('src');
      preview.alt = '';
    }
    if (emptyState) emptyState.hidden = false;
    if (selectedState) selectedState.hidden = true;
    if (filename) filename.textContent = '';
    if (status) status.textContent = '';
    drop.classList.remove('has-upload');
    clearError();
    if (notify !== false && opts.onFile) opts.onFile(null);
  }

  function setFile(file, preserveCurrent) {
    if (!file) return false;
    var keepCurrent = preserveCurrent && !!currentFile;
    // Validate type
    var allowed = (opts.acceptTypes || ['image/jpeg', 'image/png', 'image/webp']);
    if (allowed.indexOf(file.type) < 0) {
      if (!keepCurrent) clearSelection(false);
      showError(translate(
        'upload.error.file_type',
        'Unsupported file type: {{type}}. Use JPG, PNG, or WEBP.',
        { type: file.type || 'unknown' }
      ));
      if (opts.onFile) opts.onFile(currentFile);
      return false;
    }
    // Validate size (10 MB)
    if (file.size > 10 * 1024 * 1024) {
      if (!keepCurrent) clearSelection(false);
      showError(translate(
        'upload.error.file_size',
        'File is too large ({{size}} MB). Maximum is 10 MB.',
        { size: Math.round(file.size / 1024 / 1024) }
      ));
      if (opts.onFile) opts.onFile(currentFile);
      return false;
    }
    try {
      setInputFile(file);
    } catch (err) {
      if (!keepCurrent) clearSelection(false);
      showError(translate('upload.error.prepare', 'This browser could not prepare the selected image. Please choose it again.'));
      if (opts.onFile) opts.onFile(currentFile);
      return false;
    }

    currentFile = file;
    clearError();
    if (preview) {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = URL.createObjectURL(file);
      preview.src = previewUrl;
      preview.alt = file.name;
    }
    if (emptyState) emptyState.hidden = true;
    if (selectedState) selectedState.hidden = false;
    if (filename) filename.textContent = file.name;
    if (status) {
      var size = file.size < 1024 * 1024
        ? Math.max(1, Math.round(file.size / 1024)) + ' KB'
        : (file.size / (1024 * 1024)).toFixed(1) + ' MB';
      status.textContent = translate('upload.status_ready', 'Ready to upload') + ' · ' + size;
    }
    drop.classList.add('has-upload');
    if (opts.onFile) opts.onFile(file);
    return true;
  }

  function showError(msg) {
    if (error) {
      error.textContent = msg;
      error.hidden = false;
    }
  }

  function clearError() {
    if (error) {
      error.textContent = '';
      error.hidden = true;
    }
  }

  // Click and keyboard access to the drop zone; nested action buttons retain
  // their own behavior and do not open the file picker.
  drop.addEventListener('click', function (e) {
    if (e.target.tagName === 'INPUT' || e.target.closest('button')) return;
    input.click();
  });
  drop.addEventListener('keydown', function (e) {
    if (e.target === drop && (e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault();
      input.click();
    }
  });

  input.addEventListener('change', function () {
    if (input.files && input.files[0]) setFile(input.files[0]);
  });
  var replaceButton = drop.querySelector('[data-upload-replace]');
  if (replaceButton) {
    replaceButton.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      replaceInput.value = '';
      replaceInput.click();
    });
  }
  replaceInput.addEventListener('change', function () {
    if (replaceInput.files && replaceInput.files[0]) {
      setFile(replaceInput.files[0], true);
      replaceInput.value = '';
    }
  });
  var removeButton = drop.querySelector('[data-upload-remove]');
  if (removeButton) {
    removeButton.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      clearSelection();
    });
  }

  // Drag and drop
  ['dragenter', 'dragover'].forEach(function (evt) {
    drop.addEventListener(evt, function (e) {
      e.preventDefault();
      e.stopPropagation();
      drop.classList.add('drag-over');
    });
  });
  ['dragleave', 'drop'].forEach(function (evt) {
    drop.addEventListener(evt, function (e) {
      e.preventDefault();
      e.stopPropagation();
      drop.classList.remove('drag-over');
    });
  });
  drop.addEventListener('drop', function (e) {
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0], !!currentFile);
    }
  });

  return {
    getFile: function () { return currentFile; },
    setFile: setFile,
    clearError: clearError,
    showError: showError,
  };
};
