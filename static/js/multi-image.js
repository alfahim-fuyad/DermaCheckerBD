/* Multi-image upload feedback and client-side guards. */
(function () {
  'use strict';

  var form = document.getElementById('multiImageForm');
  var input = document.getElementById('imageInput');
  var submit = document.getElementById('compareSubmit');
  var status = document.getElementById('uploadStatus');
  var selectedFiles = document.getElementById('selectedFiles');
  var fileList = document.getElementById('selectedFileList');

  if (!form || !input || !submit || !status || !selectedFiles || !fileList) return;

  var maxImages = Number(input.getAttribute('data-max-images')) || 6;
  var maxBytes = 10 * 1024 * 1024;
  var allowedTypes = ['image/jpeg', 'image/png', 'image/webp'];

  function translate(key, fallback, params) {
    return window.DERMA && window.DERMA.t
      ? window.DERMA.t(key, fallback, params)
      : fallback;
  }

  function fileSize(file) {
    return file.size < 1024 * 1024
      ? Math.max(1, Math.round(file.size / 1024)) + ' KB'
      : (file.size / (1024 * 1024)).toFixed(1) + ' MB';
  }

  function renderSelection() {
    var files = Array.prototype.slice.call(input.files || []);
    fileList.textContent = '';
    selectedFiles.hidden = files.length === 0;
    status.hidden = files.length === 0;
    submit.disabled = true;

    if (!files.length) {
      status.textContent = '';
      return;
    }

    files.forEach(function (file) {
      var row = document.createElement('li');
      row.className = 'list-group-item d-flex justify-content-between gap-3';
      var name = document.createElement('span');
      name.textContent = file.name;
      var size = document.createElement('span');
      size.className = 'text-muted text-nowrap';
      size.textContent = fileSize(file);
      row.appendChild(name);
      row.appendChild(size);
      fileList.appendChild(row);
    });

    var error = '';
    if (files.length < 2) {
      error = translate('mi.choose_two', 'Choose at least 2 images to compare.');
    } else if (files.length > maxImages) {
      error = translate('mi.too_many', 'Choose no more than {{ max }} images at once.', { max: maxImages });
    } else if (files.some(function (file) { return allowedTypes.indexOf(file.type) === -1; })) {
      error = translate('mi.unsupported_file', 'Only JPG, PNG, or WEBP images are supported.');
    } else if (files.some(function (file) { return file.size > maxBytes; })) {
      error = translate('mi.file_too_large', 'Each image must be 10 MB or smaller.');
    }

    status.textContent = error || translate(
      'mi.files_selected',
      '{{ count }} images selected',
      { count: files.length }
    );
    status.classList.toggle('text-danger', !!error);
    status.classList.toggle('text-muted', !error);
    submit.disabled = !!error;
  }

  input.addEventListener('change', renderSelection);
  form.addEventListener('submit', function (event) {
    renderSelection();
    if (submit.disabled) event.preventDefault();
  });
})();
