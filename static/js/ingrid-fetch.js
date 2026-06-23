(function () {
    'use strict';

    if (window.ingridFetchCsrfReady || typeof window.fetch !== 'function') {
        return;
    }
    window.ingridFetchCsrfReady = true;

    function getCookie(name) {
        const cookiePrefix = `${encodeURIComponent(name)}=`;
        const cookies = document.cookie ? document.cookie.split(';') : [];

        for (const rawCookie of cookies) {
            const cookie = rawCookie.trim();
            if (cookie.startsWith(cookiePrefix)) {
                return decodeURIComponent(cookie.slice(cookiePrefix.length));
            }
        }
        return '';
    }

    function getCsrfToken() {
        // 요청 시점의 쿠키만 사용합니다. 캐시된 DOM 토큰은 사용하지 않습니다.
        return getCookie('csrftoken');
    }

    function isSameOrigin(url) {
        try {
            return new URL(url, window.location.href).origin === window.location.origin;
        } catch (error) {
            return false;
        }
    }

    function getRequestUrl(input) {
        return input instanceof Request ? input.url : String(input);
    }

    function getRequestMethod(input, options) {
        return String(
            (options && options.method)
            || (input instanceof Request && input.method)
            || 'GET'
        ).toUpperCase();
    }

    const originalFetch = window.fetch.bind(window);

    window.getIngridCookie = getCookie;
    window.getIngridCsrfToken = getCsrfToken;
    window.fetch = async function (input, options) {
        const requestOptions = Object.assign({}, options || {});
        const method = getRequestMethod(input, requestOptions);
        const url = getRequestUrl(input);
        const unsafeMethod = !['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method);

        if (unsafeMethod && isSameOrigin(url)) {
            const headers = new Headers(
                requestOptions.headers
                || (input instanceof Request ? input.headers : undefined)
            );
            const csrfToken = getCsrfToken();

            if (csrfToken) {
                headers.set('X-CSRFToken', csrfToken);
            }
            headers.set('X-Requested-With', 'XMLHttpRequest');
            requestOptions.headers = headers;
            requestOptions.credentials = requestOptions.credentials || 'same-origin';
        }

        const response = await originalFetch(input, requestOptions);
        const redirectedToLogin = response.redirected
            && new URL(response.url, window.location.href).pathname === '/accounts/login/';
        const sessionExpired = response.status === 401
            && response.headers.get('X-Session-Expired') === '1';

        if (
            (redirectedToLogin || sessionExpired)
            && window.location.pathname !== '/accounts/login/'
        ) {
            const next = `${window.location.pathname}${window.location.search}`;
            window.location.replace(`/accounts/login/?next=${encodeURIComponent(next)}`);
        }

        return response;
    };
})();
