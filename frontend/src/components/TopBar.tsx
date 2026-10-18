import { Plane } from "lucide-react";
import { useEffect, useState } from "react";

import { checkHealth } from "../api/client";

type ApiStatus = "checking" | "online" | "offline";

const STATUS_LABEL: Record<ApiStatus, string> = {
  checking: "Connecting",
  online: "API online",
  offline: "API offline",
};

function useApiStatus(intervalMs = 30_000): ApiStatus {
  const [status, setStatus] = useState<ApiStatus>("checking");

  useEffect(() => {
    const controller = new AbortController();
    const probe = async () => {
      const healthy = await checkHealth(controller.signal);
      if (!controller.signal.aborted) setStatus(healthy ? "online" : "offline");
    };

    probe();
    const timer = setInterval(probe, intervalMs);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [intervalMs]);

  return status;
}

export function TopBar() {
  const status = useApiStatus();

  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-mark" aria-hidden>
          <Plane size={18} />
        </span>
        <span className="brand-name">TripMate AI</span>
        <span className="brand-tag">Multi-agent travel planner</span>
      </div>
      <span className={`api-status ${status}`} role="status">
        <span className="api-dot" aria-hidden />
        {STATUS_LABEL[status]}
      </span>
    </header>
  );
}
