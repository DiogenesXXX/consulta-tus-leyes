let csrf = null;
export const state = { user: null, meta: null };
export async function api(path, options = {}) {
  const method = options.method || 'GET';
  const response = await fetch(`/api${path}`, {
    method, credentials: 'same-origin',
    headers: { ...(options.body ? {'Content-Type':'application/json'} : {}), ...(csrf ? {'X-CSRF-Token':csrf} : {}) },
    ...(options.body ? {body:JSON.stringify(options.body)} : {}),
  });
  const data = await response.json();
  if (!response.ok) { const error = new Error(data.error || 'No pudimos completar la operación.'); error.status = response.status; throw error; }
  if ('csrf' in data) { csrf = data.csrf; state.user = data.user; }
  return data;
}
export async function logout() { await api('/logout', {method:'POST'}); csrf = null; state.user = null; }
