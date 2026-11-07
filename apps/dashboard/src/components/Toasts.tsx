import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

interface ToastItem {
  id: number;
  text: string;
  detail?: string;
  tone: "success" | "error" | "plain";
}
const Ctx = createContext<(t: Omit<ToastItem, "id">) => void>(() => undefined);
export const useToast = () => useContext(Ctx);

let seq = 1;
export function ToastHost({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const push = useCallback((t: Omit<ToastItem, "id">) => {
    const id = seq++;
    setItems((x) => [...x.slice(-2), { ...t, id }]);
    window.setTimeout(() => setItems((x) => x.filter((i) => i.id !== id)), t.tone === "error" ? 9000 : 5000);
  }, []);
  return (
    <Ctx.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite" aria-atomic="false">
        {items.map((t) => (
          <div key={t.id} className={`toast toast--${t.tone}`} role={t.tone === "error" ? "alert" : "status"}>
            <span className="toast__dot" aria-hidden="true" />
            <span className="toast__text">
              {t.text}
              {t.detail && <span>{t.detail}</span>}
            </span>
            <button type="button" className="toast__action" onClick={() => setItems((x) => x.filter((i) => i.id !== t.id))}>
              Close
            </button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
