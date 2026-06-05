// app.js - HTMX event handlers and Alpine.js integration

document.addEventListener('htmx:configRequest', function(event) {
    event.detail.headers['X-CSRFToken'] = document.querySelector('meta[name="csrf-token"]').content;
});

// Toast notifications
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type} show`;
    toast.innerHTML = `
        <div class="flex items-center">
            <span class="${type === 'success' ? 'checkmark' : 'w-5 h-5 text-red-500 inline-flex items-center justify-center'}">${type === 'success' ? '✓' : '✗'}</span>
            <span class="ml-2">${message}</span>
        </div>
    `;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 5000);
}

// HTMX after swap handlers for toasts
document.body.addEventListener('htmx:afterSwap', function(event) {
    if (event.detail.xhr.responseJSON && event.detail.xhr.responseJSON.toast) {
        showToast(event.detail.xhr.responseJSON.toast.message, event.detail.xhr.responseJSON.toast.type);
    }
});

// Alpine.js for simple interactivity
const themeToggle = {
    isDark: false,
    toggle() {
        this.isDark = !this.isDark;
        if (this.isDark) {
            document.documentElement.classList.add('dark');
            localStorage.setItem('theme', 'dark');
        } else {
            document.documentElement.classList.remove('dark');
            localStorage.setItem('theme', 'light');
        }
    },
    init() {
        if (localStorage.getItem('theme') === 'dark') {
            this.isDark = true;
            document.documentElement.classList.add('dark');
        }
    }
};

// Initialize Alpine components after DOM content loaded
document.addEventListener('alpine:initialized', () => {
    Alpine.data('themeToggle', themeToggle);
});

// Htmx event handlers for dynamic forms
document.body.addEventListener('htmx:afterRequest', function(event) {
    if (event.detail.successful) {
        const response = event.detail.xhr.response;
        if (response.startsWith('toast:')) {
            try {
                const data = JSON.parse(response.substring(6));
                showToast(data.message, data.type);
            } catch (e) {}
        }
    }
});

// Handle file upload previews
document.body.addEventListener('change', function(e) {
    if (e.target.type === 'file' && e.target.hasAttribute('hx-preview')) {
        const preview = document.querySelector(e.target.getAttribute('hx-preview'));
        if (preview) {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function() {
                    preview.src = reader.result;
                    preview.classList.remove('hidden');
                };
                reader.readAsDataURL(file);
            }
        }
    }
});

// Initialize components on load
window.addEventListener('load', function() {
    const autosyncElements = document.querySelectorAll('[hx-get]');
    autosyncElements.forEach(el => {
        if (el.getAttribute('hx-trigger') === 'load') {
            htmx.trigger(el, 'request');
        }
    });
});

// Dark mode preference from system
document.addEventListener('DOMContentLoaded', function() {
    if (!localStorage.getItem('theme')) {
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        if (prefersDark) {
            document.documentElement.classList.add('dark');
            localStorage.setItem('theme', 'dark');
        } else {
            document.documentElement.classList.remove('dark');
            localStorage.setItem('theme', 'light');
        }
    }
});

// Initialize Alpine
Alpine.start();

// Theme switcher event handler (if the button exists)
document.getElementById('theme-toggle')?.addEventListener('click', function() {
    const html = document.documentElement;
    if (html.classList.contains('dark')) {
        html.classList.remove('dark');
        localStorage.setItem('theme', 'light');
    } else {
        html.classList.add('dark');
        localStorage.setItem('theme', 'dark');
    }
});

// HTMX toasts handling
document.addEventListener('htmx:afterSwap', function(event) {
    if (event.detail.target.dataset.toast) {
        const toastData = JSON.parse(event.detail.target.dataset.toast);
        showToast(toastData.message, toastData.type);
    }
});

// Handle validation errors
document.body.addEventListener('htmx:validationError', (event) => {
    const response = JSON.parse(event.detail.xhr.response);
    const errors = response.errors;
    for (const [field, message] of Object.entries(errors)) {
        const input = document.querySelector(`[name="${field}"]`);
        if (input) {
            let errorElement = input.nextElementSibling;
            if (!errorElement || !errorElement.classList.contains('text-red-500')) {
                errorElement = document.createElement('div');
                errorElement.className = "text-red-500 text-sm mt-1";
                input.parentNode.appendChild(errorElement);
            }
            errorElement.textContent = message;
        }
    }
});

// Htmx request for file upload
document.body.addEventListener('htmx:beforeRequest', function(event) {
    if (event.detail.elt.form?.enctype === 'multipart/form-data') {
        event.detail.headers['Content-Type'] = 'multipart/form-data';
    }
});