(() => {
  const form = document.getElementById('food-discovery-form');
  form?.addEventListener('submit', (event) => {
    const activeCuisine = document.getElementById('food-current-cuisine');
    if (event.submitter?.name === 'cuisine' && activeCuisine) activeCuisine.disabled = true;
  });
  document.querySelectorAll('.food-veg-toggle input, .food-sort select').forEach((input) => {
    input.addEventListener('change', () => input.closest('form')?.requestSubmit());
  });
  document.querySelectorAll('.food-discovery-form, .food-menu-search, .food-option-form').forEach((currentForm) => {
    currentForm.addEventListener('submit', () => {
      currentForm.setAttribute('aria-busy', 'true');
    });
  });
  window.addEventListener('pageshow', () => {
    document.querySelectorAll('[aria-busy="true"]').forEach((element) => element.removeAttribute('aria-busy'));
  });
  const locationEditor = document.getElementById('delivery-location');
  document.querySelectorAll('a[href="#delivery-location"]').forEach((link) => {
    link.addEventListener('click', () => {
      if (locationEditor) { locationEditor.open = true; document.getElementById('food-pincode')?.focus(); }
    });
  });
})();
