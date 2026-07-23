"use client";

import { CheckCircle2, X, XCircle } from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

type ToastTone = "success" | "error";
type ToastItem = { id: number; message: string; tone: ToastTone };
type ToastContextValue = {
  notify: (message: string, tone?: ToastTone) => void;
};

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

export function ToastProvider({ children }: Readonly<{ children: ReactNode }>) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const notify = useCallback((message: string, tone: ToastTone = "success") => {
    const id = Date.now();
    setItems((current) => {
      if (current.some((item) => item.message === message)) return current;
      return [...current.slice(-2), { id, message, tone }];
    });
    window.setTimeout(
      () => setItems((current) => current.filter((item) => item.id !== id)),
      4500,
    );
  }, []);
  const value = useMemo(() => ({ notify }), [notify]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-region" aria-live="polite" aria-atomic="true">
        {items.map((item) => (
          <div
            className={`toast toast-${item.tone}`}
            key={item.id}
            role="status"
          >
            {item.tone === "success" ? (
              <CheckCircle2 aria-hidden="true" size={19} />
            ) : (
              <XCircle aria-hidden="true" size={19} />
            )}
            <span>{item.message}</span>
            <button
              aria-label="Закрыть уведомление"
              onClick={() =>
                setItems((current) =>
                  current.filter((candidate) => candidate.id !== item.id),
                )
              }
              type="button"
            >
              <X size={16} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const value = useContext(ToastContext);
  if (!value) throw new Error("useToast must be used inside ToastProvider");
  return value;
}
