import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import PageHeader from "../components/ui/PageHeader";
import Button from "../components/ui/Button";
import { Card, CardBody } from "../components/ui/Card";
import Banner from "../components/ui/Banner";

export default function PendingAccessPage() {
  const { user, logout } = useAuth();

  return (
    <div className="min-w-0">
      <PageHeader
        eyebrow="Access"
        title="Waiting for role assignment"
        subtitle="Your account is signed in but does not have a business role yet."
      />
      <Card className="max-w-xl min-w-0">
        <CardBody className="space-y-4">
          <Banner tone="info">
            Signed in as <strong className="break-all">{user?.email}</strong>. Ask the owner to assign you a role on the
            Users page.
          </Banner>
          <p className="text-sm text-ink-muted">
            Until a role is assigned, inventory, bills, and other business features stay locked. You can sign out and try
            another account, or wait for the owner to grant access.
          </p>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:flex-wrap">
            <Button type="button" variant="secondary" onClick={() => logout()} className="min-h-11 w-full sm:w-auto">
              Sign out
            </Button>
            <Link to="/home" className="w-full sm:w-auto">
              <Button variant="ghost" className="min-h-11 w-full sm:w-auto">
                About
              </Button>
            </Link>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
