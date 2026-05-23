import { useEffect, useState } from 'react';
import { DownloadSimple, X } from '@phosphor-icons/react';

/**
 * "Add to home screen" banner.
 * - Android / desktop Chrome / Edge: catches the `beforeinstallprompt` event
 *   and triggers it on click.
 * - iOS Safari: shows manual instructions (no programmatic install API).
 * - Hidden when the app is already running as a PWA (standalone display) or
 *   the user dismissed it (stored in localStorage).
 */
const STORAGE_KEY = 'pwa_install_dismissed';

function isStandalone() {
  if (typeof window === 'undefined') return false;
  return (
    window.matchMedia?.('(display-mode: standalone)').matches ||
    window.navigator.standalone === true
  );
}

function isIos() {
  const ua = typeof navigator !== 'undefined' ? navigator.userAgent : '';
  return /iphone|ipad|ipod/i.test(ua) && !/crios|fxios/i.test(ua);
}

export default function InstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [visible, setVisible] = useState(false);
  const [showIosHint, setShowIosHint] = useState(false);

  useEffect(() => {
    if (isStandalone()) return;
    if (localStorage.getItem(STORAGE_KEY) === '1') return;

    // Android / Chrome / Edge: native install prompt
    const onBeforeInstall = (e) => {
      e.preventDefault();
      setDeferredPrompt(e);
      setVisible(true);
    };
    window.addEventListener('beforeinstallprompt', onBeforeInstall);

    // iOS Safari: no event, show manual hint after a short delay so it isn't
    // intrusive on first paint. Only on actual iOS, not desktop.
    if (isIos()) {
      const t = setTimeout(() => setVisible(true), 4000);
      return () => {
        clearTimeout(t);
        window.removeEventListener('beforeinstallprompt', onBeforeInstall);
      };
    }
    return () => window.removeEventListener('beforeinstallprompt', onBeforeInstall);
  }, []);

  if (!visible) return null;

  const dismiss = () => {
    setVisible(false);
    setShowIosHint(false);
    localStorage.setItem(STORAGE_KEY, '1');
  };

  const install = async () => {
    if (deferredPrompt) {
      deferredPrompt.prompt();
      const { outcome } = await deferredPrompt.userChoice;
      setDeferredPrompt(null);
      setVisible(false);
      if (outcome === 'accepted') {
        localStorage.setItem(STORAGE_KEY, '1');
      }
      return;
    }
    // iOS path: open instructions
    setShowIosHint(true);
  };

  return (
    <div
      className="fixed bottom-4 left-4 right-4 z-50 md:left-auto md:right-4 md:w-96 border border-[#050505] bg-[#002FA7] text-white shadow-[8px_8px_0_rgba(0,0,0,0.6)]"
      role="dialog"
      data-testid="install-prompt"
    >
      <div className="flex items-start gap-3 p-4">
        <div className="flex-shrink-0 w-12 h-12 bg-white text-[#002FA7] border border-[#050505] flex items-center justify-center font-black text-2xl" style={{ fontFamily: 'Cabinet Grotesk' }}>
          H
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-bold text-sm uppercase tracking-tight" style={{ fontFamily: 'Cabinet Grotesk' }}>
            APP INSTALLIEREN
          </p>
          <p className="text-xs mt-1 leading-snug opacity-90">
            Direkt vom Startbildschirm öffnen — schneller Zugriff & Push-Benachrichtigungen.
          </p>
          {showIosHint && (
            <div className="mt-3 bg-white text-[#050505] p-3 border border-[#050505] text-xs leading-relaxed">
              <p className="font-bold mb-1">iOS Safari:</p>
              <ol className="list-decimal pl-4 space-y-0.5">
                <li>Auf <span className="font-mono">Teilen</span>-Symbol tippen (↑)</li>
                <li><span className="font-mono">„Zum Home-Bildschirm“</span> auswählen</li>
                <li>Bestätigen mit <span className="font-mono">„Hinzufügen“</span></li>
              </ol>
            </div>
          )}
          <div className="flex gap-2 mt-3">
            {!showIosHint && (
              <button
                type="button"
                onClick={install}
                className="px-3 py-2 bg-[#FFCB05] text-[#050505] border border-[#050505] text-xs font-mono uppercase tracking-[0.18em] hover:bg-white transition-colors duration-150 flex items-center gap-1"
                data-testid="install-prompt-install"
              >
                <DownloadSimple weight="bold" size={14} />
                INSTALLIEREN
              </button>
            )}
            <button
              type="button"
              onClick={dismiss}
              className="px-3 py-2 bg-transparent text-white border border-white/40 text-xs font-mono uppercase tracking-[0.18em] hover:bg-white/10 transition-colors duration-150"
              data-testid="install-prompt-dismiss"
            >
              SPÄTER
            </button>
          </div>
        </div>
        <button
          type="button"
          onClick={dismiss}
          className="p-1 hover:bg-white/10 transition-colors duration-150 flex-shrink-0"
          aria-label="Schließen"
        >
          <X weight="bold" size={16} />
        </button>
      </div>
    </div>
  );
}
