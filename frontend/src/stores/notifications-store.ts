import { create } from "zustand"
import { persist } from "zustand/middleware"

interface NotificationsState {
  /** ISO timestamp of last time the user opened the notifications panel. */
  lastSeen: string | null
  markAllRead: () => void
}

export const useNotificationsStore = create<NotificationsState>()(
  persist(
    (set) => ({
      lastSeen: null,
      markAllRead: () => set({ lastSeen: new Date().toISOString() }),
    }),
    { name: "nord.notifications" },
  ),
)
