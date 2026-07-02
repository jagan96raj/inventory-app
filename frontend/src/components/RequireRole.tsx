import { Link, Navigate, Outlet } from "react-router-dom";
import { usePermissions, type Permission } from "../lib/permissions";
import EmptyState from "./ui/EmptyState";
import Button from "./ui/Button";
import Banner from "./ui/Banner";

type Props = {
  permission?: Permission;
  anyOf?: Permission[];
  ownerOnly?: boolean;
};

export default function RequireRole({ permission, anyOf, ownerOnly }: Props) {
  const { hasRole, can, isOwner } = usePermissions();

  if (!hasRole) {
    return <Navigate to="/pending-access" replace />;
  }

  if (ownerOnly && !isOwner) {
    return <AccessDenied message="This page is only available to the owner role." />;
  }

  if (permission && !can(permission)) {
    return <AccessDenied />;
  }

  if (anyOf && !anyOf.some((p) => can(p))) {
    return <AccessDenied />;
  }

  return <Outlet />;
}

function AccessDenied({ message = "You do not have permission to view this page." }: { message?: string }) {
  return (
    <div className="mx-auto max-w-lg py-10">
      <Banner tone="warning" className="mb-4">
        {message}
      </Banner>
      <EmptyState
        title="Access denied"
        description={message}
        action={
          <Link to="/dashboard">
            <Button variant="secondary">Back to dashboard</Button>
          </Link>
        }
      />
    </div>
  );
}
