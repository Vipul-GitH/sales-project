document.addEventListener('DOMContentLoaded', () => {
  const visiblePrimary = document.createElement('style');
  visiblePrimary.textContent = '.table td a.btn-primary{color:#fff!important}';
  document.head.appendChild(visiblePrimary);
  const accountType = document.querySelector('#accountType');
  function leadFields(){ document.querySelectorAll('.lead-only').forEach(el=>el.classList.toggle('d-none', accountType && accountType.value !== 'New Lead')); }
  if(accountType){ accountType.addEventListener('change', leadFields); leadFields(); }
  document.querySelector('.add-contact')?.addEventListener('click', () => { document.querySelector('#contactRows').insertAdjacentHTML('beforeend','<div class="col-md-4"><input name="contact_name" class="form-control" placeholder="Contact name"></div><div class="col-md-4"><input name="designation" class="form-control" placeholder="Designation"></div><div class="col-md-4"><input name="mobile" class="form-control" placeholder="Mobile"></div>'); });
  const next = document.querySelector('.next-action'); function actionFields(){ const creates = ['Create follow-up task','Create visit task','Create quotation/rates task','Create another task'].includes(next?.value); document.querySelector('.next-task-fields')?.classList.toggle('d-none', !creates); document.querySelector('.action-reason')?.classList.toggle('d-none', !['No further action required','Lead lost','Lead placed on hold','Account made inactive'].includes(next?.value)); } next?.addEventListener('change', actionFields); if(next) actionFields();
  const recurrence = document.querySelector('.recurrence'); function recurrenceFields(){ const value=(recurrence?.value || '').toLowerCase(); document.querySelector('.recurrence-weekly')?.classList.toggle('d-none', value!=='weekly'); document.querySelector('.recurrence-monthly')?.classList.toggle('d-none', value!=='monthly'); document.querySelector('.recurrence-custom')?.classList.toggle('d-none', value!=='custom days'); } if(recurrence){recurrence.addEventListener('change',recurrenceFields);recurrenceFields();}
  document.querySelectorAll('form.needs-validation').forEach(f=>f.addEventListener('submit',e=>{if(!f.checkValidity()){e.preventDefault();e.stopPropagation();}f.classList.add('was-validated');}));
  document.querySelectorAll('form').forEach(form => form.addEventListener('submit', event => {
    if (!form.checkValidity() || event.defaultPrevented) return;
    const submitter = event.submitter;
    if (!submitter || submitter.dataset.submitting === 'true') return;
    submitter.dataset.submitting = 'true';
    submitter.setAttribute('aria-busy', 'true');
    setTimeout(() => { submitter.disabled = true; }, 0);
  }));
  const dueDate = document.querySelector('input[name="task_due_date"]');
  function syncFollowUpRequired(){ if(dueDate) dueDate.required = next?.value === 'Create follow-up task'; }
  next?.addEventListener('change', syncFollowUpRequired); syncFollowUpRequired();

  document.querySelectorAll('table.table').forEach(table => {
    table.classList.add('responsive-table');
    const labels = [...table.querySelectorAll('thead th')].map(th => th.textContent.trim());
    table.querySelectorAll('tbody tr').forEach(row => {
      [...row.children].forEach((cell, index) => {
        if (!cell.hasAttribute('colspan') && !cell.dataset.label && labels[index]) cell.dataset.label = labels[index];
      });
    });
  });

  const menuButton = document.querySelector('.mobile-menu-btn');
  const menuClose = document.querySelector('.mobile-nav-close');
  const menuOverlay = document.querySelector('.mobile-nav-overlay');
  const setMobileMenu = open => {
    document.body.classList.toggle('mobile-nav-open', open);
    menuButton?.setAttribute('aria-expanded', String(open));
  };
  menuButton?.addEventListener('click', () => setMobileMenu(true));
  menuClose?.addEventListener('click', () => setMobileMenu(false));
  menuOverlay?.addEventListener('click', () => setMobileMenu(false));
  const sidebarLinks = [...document.querySelectorAll('.sidebar .nav-link')];
  sidebarLinks.forEach(link => link.addEventListener('click', () => setMobileMenu(false)));
  const currentPath = window.location.pathname;
  sidebarLinks.forEach(link => {
    const linkPath = new URL(link.href, window.location.origin).pathname;
    const isDashboard = linkPath === '/dashboard' && currentPath === '/dashboard';
    const isSection = linkPath !== '/dashboard' && currentPath.startsWith(linkPath);
    link.classList.toggle('is-current', isDashboard || isSection);
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && document.body.classList.contains('mobile-nav-open')) setMobileMenu(false);
  });
  window.addEventListener('resize', () => {
    if (window.innerWidth > 767) setMobileMenu(false);
  });

  const combobox = document.querySelector('[data-user-combobox]');
  if (combobox) {
    const input = combobox.querySelector('input');
    const list = combobox.querySelector('.user-suggestions');
    const toggle = combobox.querySelector('.user-search-toggle');
    const options = [...combobox.querySelectorAll('.user-suggestion')];
    const empty = combobox.querySelector('.user-suggestion-empty');
    let visibleOptions = [];
    let activeIndex = -1;

    const setOpen = open => {
      list.hidden = !open;
      input.setAttribute('aria-expanded', String(open));
      toggle.querySelector('i').className = open ? 'bi bi-chevron-up' : 'bi bi-chevron-down';
      if (!open) {
        activeIndex = -1;
        options.forEach(option => option.classList.remove('is-active'));
      }
    };

    const filterUsers = () => {
      const query = input.value.trim().toLowerCase();
      visibleOptions = options.filter(option => option.dataset.search.includes(query));
      options.forEach(option => { option.hidden = !visibleOptions.includes(option); });
      empty.hidden = visibleOptions.length > 0;
      activeIndex = -1;
      setOpen(true);
    };

    const selectUser = option => {
      input.value = option.dataset.userName;
      input.focus();
      setOpen(false);
    };

    input.addEventListener('focus', filterUsers);
    input.addEventListener('input', filterUsers);
    toggle.addEventListener('click', () => list.hidden ? filterUsers() : setOpen(false));
    options.forEach(option => option.addEventListener('click', () => selectUser(option)));
    input.addEventListener('keydown', event => {
      if (event.key === 'Escape') { setOpen(false); return; }
      if (event.key === 'Enter' && !list.hidden && activeIndex >= 0) {
        event.preventDefault();
        selectUser(visibleOptions[activeIndex]);
        return;
      }
      if (!['ArrowDown', 'ArrowUp'].includes(event.key)) return;
      event.preventDefault();
      if (list.hidden) filterUsers();
      if (!visibleOptions.length) return;
      activeIndex = event.key === 'ArrowDown'
        ? (activeIndex + 1) % visibleOptions.length
        : (activeIndex - 1 + visibleOptions.length) % visibleOptions.length;
      visibleOptions.forEach((option, index) => option.classList.toggle('is-active', index === activeIndex));
      visibleOptions[activeIndex].scrollIntoView({ block: 'nearest' });
    });
    document.addEventListener('click', event => {
      if (!combobox.contains(event.target)) setOpen(false);
    });
  }

  document.querySelectorAll('[data-account-combobox]').forEach(combobox => {
    const input = combobox.querySelector('input[type="text"]');
    const hidden = combobox.querySelector('[data-account-id]');
    const list = combobox.querySelector('.account-suggestions');
    const clear = combobox.querySelector('.account-search-clear');
    const options = [...combobox.querySelectorAll('.account-suggestion')];
    const empty = combobox.querySelector('.account-suggestion-empty');
    let visible = [];
    let activeIndex = -1;

    const close = () => {
      list.hidden = true;
      input.setAttribute('aria-expanded', 'false');
      activeIndex = -1;
      options.forEach(option => option.classList.remove('is-active'));
    };
    const validate = () => input.setCustomValidity(hidden.value ? '' : 'Select an account from the suggestions.');
    const filter = () => {
      const query = input.value.trim().toLowerCase();
      hidden.value = '';
      clear.hidden = !query;
      validate();
      if (!query) { close(); return; }
      visible = options.filter(option => option.dataset.search.includes(query));
      options.forEach(option => { option.hidden = !visible.includes(option); });
      empty.hidden = visible.length > 0;
      list.hidden = false;
      input.setAttribute('aria-expanded', 'true');
      activeIndex = -1;
    };
    const select = option => {
      hidden.value = option.dataset.accountId;
      input.value = option.dataset.accountName;
      clear.hidden = false;
      validate();
      close();
      input.focus();
    };

    clear.hidden = !input.value;
    validate();
    input.addEventListener('input', filter);
    input.addEventListener('focus', () => { if (input.value && !hidden.value) filter(); });
    clear.addEventListener('click', () => { input.value = ''; hidden.value = ''; clear.hidden = true; validate(); close(); input.focus(); });
    options.forEach(option => option.addEventListener('click', () => select(option)));
    input.addEventListener('keydown', event => {
      if (event.key === 'Escape') { close(); return; }
      if (event.key === 'Enter' && !list.hidden && activeIndex >= 0) { event.preventDefault(); select(visible[activeIndex]); return; }
      if (!['ArrowDown', 'ArrowUp'].includes(event.key) || list.hidden || !visible.length) return;
      event.preventDefault();
      activeIndex = event.key === 'ArrowDown' ? (activeIndex + 1) % visible.length : (activeIndex - 1 + visible.length) % visible.length;
      visible.forEach((option, index) => option.classList.toggle('is-active', index === activeIndex));
      visible[activeIndex].scrollIntoView({ block: 'nearest' });
    });
    combobox.closest('form')?.addEventListener('submit', event => { validate(); if (!hidden.value) { event.preventDefault(); input.reportValidity(); input.focus(); } });
    document.addEventListener('click', event => { if (!combobox.contains(event.target)) close(); });
  });
});
