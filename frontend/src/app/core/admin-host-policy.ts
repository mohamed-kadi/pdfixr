const STORAGE_KEY = 'pdf_saas_admin_hosts';

type RuntimeWindow = Window & {
  PDF_SAAS_ADMIN_ALLOWED_HOSTS?: unknown;
};

function parseHosts(raw: string): string[] {
  return raw
    .split(',')
    .map((item) => item.trim().toLowerCase())
    .filter((item) => item.length > 0);
}

function configuredHosts(): string[] {
  if (typeof window === 'undefined') {
    return [];
  }

  const fromWindow = (window as RuntimeWindow).PDF_SAAS_ADMIN_ALLOWED_HOSTS;
  if (typeof fromWindow === 'string' && fromWindow.trim()) {
    return parseHosts(fromWindow);
  }

  try {
    const fromStorage = window.localStorage.getItem(STORAGE_KEY);
    if (fromStorage && fromStorage.trim()) {
      return parseHosts(fromStorage);
    }
  } catch {
    return [];
  }

  return [];
}

export function isAdminHostAllowed(): boolean {
  if (typeof window === 'undefined') {
    return true;
  }

  const hosts = configuredHosts();
  if (hosts.length === 0) {
    return true;
  }

  const currentHost = window.location.host.trim().toLowerCase();
  const currentHostname = window.location.hostname.trim().toLowerCase();
  return hosts.some((host) => host === currentHost || host === currentHostname);
}
