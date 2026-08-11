import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useIdleLogout } from "../hooks/useIdleLogout";

/** When signed in, revoke the session and return to login after 10 minutes idle. */
export default function IdleSessionGuard() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const onIdle = useCallback(async () => {
    try {
      await logout();
    } finally {
      navigate("/login", { replace: true });
    }
  }, [logout, navigate]);

  useIdleLogout(Boolean(user), onIdle);

  return null;
}
