/**
 * PWA install support, which differs by platform in a way worth handling properly.
 *
 * Android/Chrome fires `beforeinstallprompt`, which can be stashed and replayed from
 * a button. iOS fires nothing and cannot install from Chrome at all — it must be
 * Safari's Share sheet. Showing an Android-style "Install" button on an iPhone gives
 * the user a control that cannot work, so the two cases are detected separately.
 */

type InstallPromptEvent = Event & {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

export type InstallState =
  | { kind: 'installed' }
  | { kind: 'prompt-ready' }
  | { kind: 'ios-safari' }
  | { kind: 'ios-other-browser' }
  | { kind: 'unsupported' }

let deferred: InstallPromptEvent | null = null

window.addEventListener('beforeinstallprompt', (event) => {
  event.preventDefault()
  deferred = event as InstallPromptEvent
})

const isStandalone = () =>
  window.matchMedia('(display-mode: standalone)').matches ||
  // iOS predates display-mode and reports this instead.
  (navigator as { standalone?: boolean }).standalone === true

export function installState(): InstallState {
  if (isStandalone()) return { kind: 'installed' }
  if (deferred) return { kind: 'prompt-ready' }

  const ua = navigator.userAgent
  // iPadOS reports as Macintosh; the touch-point count is what distinguishes it.
  const isIOS = /iPad|iPhone|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)
  if (isIOS) {
    // Every iOS browser embeds "Safari" in its UA; only the real one omits the
    // vendor tokens that Chrome (CriOS), Firefox (FxiOS) and Edge (EdgiOS) add.
    const isRealSafari = !/CriOS|FxiOS|EdgiOS|OPiOS/.test(ua)
    return { kind: isRealSafari ? 'ios-safari' : 'ios-other-browser' }
  }
  return { kind: 'unsupported' }
}

export async function promptInstall(): Promise<'accepted' | 'dismissed' | 'unavailable'> {
  if (!deferred) return 'unavailable'
  await deferred.prompt()
  const { outcome } = await deferred.userChoice
  // The event is single-use; Chrome will fire a fresh one if the user declines.
  deferred = null
  return outcome
}
