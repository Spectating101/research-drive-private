import { useCallback, useState } from "react";

export function useToast() {
  const [toast, setToast] = useState(null);

  const show = useCallback((message, kind = "info") => {
    const text = String(message || "").trim();
    if (!text) return;
    setToast({ message: text, kind });
    window.clearTimeout(useToast._timer);
    useToast._timer = window.setTimeout(() => setToast(null), 4200);
  }, []);

  return { toast, show };
}

export function Toast({ toast }) {
  if (!toast) return null;
  return (
    <div className={`rd-v2-toast ${toast.kind}`} role="status">
      {toast.message}
    </div>
  );
}
