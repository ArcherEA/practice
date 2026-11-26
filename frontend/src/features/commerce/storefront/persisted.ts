import { useSyncExternalStore } from "react"

/**
 * A small external store kept in `localStorage`, for the cart and the chosen currency.
 *
 * Every storage access is wrapped in try/catch: with blocked storage (private window,
 * site data blocked, quota) the store keeps working in memory for the page's lifetime
 * and nothing throws. Other tabs are followed through the `storage` event.
 */
export interface PersistedStore<T> {
  get: () => T
  set: (next: T) => void
  subscribe: (listener: () => void) => () => void
}

export function createPersistedStore<T>(
  key: string,
  parse: (raw: unknown) => T,
  empty: T,
): PersistedStore<T> {
  const listeners = new Set<() => void>()
  let state: T | undefined

  const read = (): T => {
    try {
      const text = window.localStorage.getItem(key)
      return text === null ? empty : parse(JSON.parse(text))
    } catch {
      return empty
    }
  }

  const notify = () => {
    for (const listener of listeners) listener()
  }

  let listening = false
  const onStorage = (event: StorageEvent) => {
    if (event.key !== null && event.key !== key) return
    state = read()
    notify()
  }

  return {
    get: () => {
      if (state === undefined) state = read()
      return state
    },
    set: (next) => {
      state = next
      try {
        window.localStorage.setItem(key, JSON.stringify(next))
      } catch {
        // Blocked or full storage: keep the value in memory only.
      }
      notify()
    },
    subscribe: (listener) => {
      listeners.add(listener)
      if (!listening) {
        window.addEventListener("storage", onStorage)
        listening = true
      }
      return () => {
        listeners.delete(listener)
        if (listeners.size === 0 && listening) {
          window.removeEventListener("storage", onStorage)
          listening = false
        }
      }
    },
  }
}

export function usePersistedStore<T>(store: PersistedStore<T>): T {
  // Server snapshot = the empty/initial read; the app is client-rendered only.
  return useSyncExternalStore(store.subscribe, store.get, store.get)
}
