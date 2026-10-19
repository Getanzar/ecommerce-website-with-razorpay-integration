(() => {
  document.querySelectorAll('[data-listing-assistant]').forEach(panel => {
    const form = panel.closest('form');
    if (!form) return;
    const mainPhoto = form.querySelector('#id_image');
    const backPhoto = form.querySelector('#id_back_image');
    const generate = panel.querySelector('[data-ai-generate]');
    const status = panel.querySelector('[data-ai-status]');
    const result = panel.querySelector('[data-ai-result]');
    const apply = panel.querySelector('[data-ai-apply]');
    let proposal = null;
    let changed = false;
    let busy = false;
    let generation = 0;
    const message = (text, error = false) => {
      status.textContent = text;
      status.className = `small mt-3 mb-0 ${error ? 'text-danger' : 'text-success'}`;
    };
    const invalidate = () => {
      generation++;
      proposal = null;
      result.hidden = true;
      if (busy) message('Photos or notes changed. Generate a new draft when ready.');
    };
    for (const input of [mainPhoto, backPhoto]) {
      input?.addEventListener('change', () => {
        invalidate();
        panel.querySelector('[data-ai-photo-name]').textContent = [mainPhoto, backPhoto].flatMap(field => Array.from(field?.files || []).map(file => file.name)).join(', ') || 'No photo selected';
      });
    }
    panel.querySelector('[data-ai-notes]').addEventListener('input', invalidate);
    form.addEventListener('input', event => { if (!panel.contains(event.target)) changed = true; });
    form.addEventListener('change', event => { if (!panel.contains(event.target)) changed = true; });
    panel.querySelector('[data-ai-pick]').onclick = () => mainPhoto?.click();
    generate.onclick = async () => {
      if (busy) return;
      const photos = [mainPhoto, backPhoto].flatMap(field => Array.from(field?.files || []));
      if (!photos.length) return message('Choose at least one product photo first.', true);
      if (photos.some(photo => photo.size > 8 * 1024 * 1024)) return message('Each photo must be 8 MB or smaller.', true);
      const current = ++generation;
      proposal = null;
      result.hidden = true;
      changed = false;
      const body = new FormData();
      body.append('kind', panel.dataset.kind);
      body.append('enhance_photo', 'true');
      body.append('notes', panel.querySelector('[data-ai-notes]').value.trim());
      photos.forEach(photo => body.append('photos', photo));
      busy = true;
      generate.disabled = true;
      message('Reading product photos and preparing your draft…');
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 115000);
      try {
        const response = await fetch(panel.dataset.endpoint, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': form.querySelector('[name=csrfmiddlewaretoken]').value }, body, signal: controller.signal });
        if (response.redirected) throw new Error('Your session expired. Sign in again, then retry.');
        const data = await response.json().catch(() => { throw new Error('The listing assistant could not respond. Your form is unchanged.'); });
        if (current !== generation) return;
        if (!response.ok) throw new Error(data.error || 'Could not generate a draft. Please try again.');
        proposal = data;
        const preview = panel.querySelector('[data-ai-image]');
        preview.hidden = !data.catalogue_image;
        if (data.catalogue_image) preview.src = `data:${data.catalogue_image.mime_type};base64,${data.catalogue_image.data}`;
        else preview.removeAttribute('src');
        panel.querySelector('[data-ai-image-warning]').textContent = data.image_warning || '';
        panel.querySelector('[data-ai-name]').textContent = data.draft.name;
        panel.querySelector('[data-ai-description]').textContent = data.draft.description;
        const details = panel.querySelector('[data-ai-details]');
        details.replaceChildren();
        const suggestions = [...data.draft.review_notes];
        if (data.suggested_category) suggestions.unshift(`${panel.dataset.kind === 'food' ? 'Menu section' : 'Category'}: ${data.suggested_category}`);
        for (const key of ['brand', 'unit', 'colours', 'keywords']) {
          const value = Array.isArray(data.draft[key]) ? data.draft[key].join(', ') : data.draft[key];
          if (value) suggestions.push(`${key}: ${value}`);
        }
        for (const text of suggestions) { const item = document.createElement('li'); item.textContent = text; details.appendChild(item); }
        result.hidden = false;
        apply.disabled = false;
        message(`Draft ready for review. ${data.remaining_today} generations remaining today.`);
      } catch (error) {
        if (current === generation) message(error.name === 'AbortError' ? 'The request timed out. Your form is unchanged; you can continue manually.' : error.message || 'Could not generate a draft.', true);
      } finally { clearTimeout(timeout); busy = false; generate.disabled = false; }
    };
    apply.onclick = () => {
      if (!proposal) return;
      const image = proposal.catalogue_image;
      let imageFiles;
      if (image && mainPhoto) {
        try {
          const bytes = Uint8Array.from(atob(image.data), char => char.charCodeAt(0));
          const transfer = new DataTransfer();
          transfer.items.add(new File([bytes], image.name, { type: image.mime_type }));
          imageFiles = transfer.files;
        } catch { return message('Could not apply the catalogue photo in this browser. Your form is unchanged.', true); }
      }
      const entries = Object.entries(proposal.fields).filter(([name]) => ['name', 'description', 'category', 'section', 'brand', 'unit'].includes(name));
      const overwrite = entries.some(([name, value]) => { const field = form.querySelector(`#id_${name}`); return field && field.value && field.value !== value; });
      if ((changed || overwrite) && !window.confirm('Apply this draft and replace the suggested fields? Your price, stock and other fields will be kept.')) return;
      for (const [name, value] of entries) {
        const field = form.querySelector(`#id_${name}`);
        if (!field || (field.tagName === 'SELECT' && !Array.from(field.options).some(option => option.value === String(value)))) continue;
        if (name === 'category' && field.value !== String(value)) {
          const subcategory = form.querySelector('#id_subcategory');
          if (subcategory) { subcategory.value = ''; subcategory.dispatchEvent(new Event('change', { bubbles: true })); }
        }
        field.value = value;
        field.dispatchEvent(new Event('input', { bubbles: true }));
        field.dispatchEvent(new Event('change', { bubbles: true }));
      }
      if (imageFiles) {
        mainPhoto.files = imageFiles;
        mainPhoto.dispatchEvent(new Event('change', { bubbles: true }));
        const clear = form.querySelector('[name="image-clear"]');
        if (clear) clear.checked = false;
      }
      proposal = null;
      apply.disabled = true;
      message('Draft applied. Check the form, enter price and stock, then save when ready.');
    };
    panel.querySelector('[data-ai-discard]').onclick = () => { invalidate(); message('Draft discarded. Your form is unchanged.'); };
  });
})();
